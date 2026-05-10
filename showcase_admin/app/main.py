from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Body, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
import os

from showcase_admin.app import config, database, auth, k8s_client

# Initialize database table structures on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield

app = FastAPI(
    title="GKE Feature Showcase Hub",
    description="Administrative control panel and show-and-tell playground for advanced GKE capabilities.",
    lifespan=lifespan
)

# Global Basic Auth Dependency
# All API routes require verification if authentication is enabled
api_dependencies = []
if config.ADMIN_AUTHENTICATION_ENABLED:
    api_dependencies = [Depends(auth.verify_admin_credentials)]

# Static and frontend folders mapping
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend')
os.makedirs(frontend_dir, exist_ok=True)

# Serve Frontend SPA UI
@app.get("/", response_class=HTMLResponse, dependencies=api_dependencies)
async def read_root():
    index_path = os.path.join(frontend_dir, 'index.html')
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return """
    <html>
        <head><title>Showcase Hub</title></head>
        <body>
            <h2>GKE Feature Showcase Hub Dashboard</h2>
            <p>Frontend UI is currently being implemented. Check backend APIs under <a href='/docs'>/docs</a></p>
        </body>
    </html>
    """

# Mount Static Frontend Assets (CSS, JS, Images) if the folder contains files
# To avoid startup failures if empty, we do this optionally
if os.path.exists(os.path.join(frontend_dir, 'style.css')):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# Available Features Metadata
AVAILABLE_SHOWCASES = {
    "agent-sandbox": {
        "name": "agent-sandbox",
        "title": "GKE Agent Sandbox",
        "description": "Orchestrate secure, sub-second isolated gVisor agent environments executing dynamic untrusted user instructions safely mapped via GKE Workload Identity.",
        "gke_features": ["gVisor Isolation Runtime", "SandboxTemplate Custom Resources", "Workload Identity Federation", "SandboxWarmPool Probes"]
    },
    "gpu-inference": {
        "name": "gpu-inference",
        "title": "vLLM GPU Model Inference",
        "description": "Serve self-hosted open-source Large Language Models (e.g., Gemma 2B) leveraging GKE Spot Nvidia L4 GPUs and GCSFuse volume mapping to mount bucket checkpoints.",
        "gke_features": ["Nvidia L4 Spot GPU Pools", "GCS FUSE CSI Storage Driver", "Gateway Ingress API routing", "Dynamic GPU cluster scaling"]
    }
}

# Backend Administrative APIs
@app.get("/api/showcases", dependencies=api_dependencies)
async def list_showcases(db: Session = Depends(database.get_db)):
    # Fetch all database records
    db_showcases = db.query(database.ShowcaseModel).all()
    status_map = {item.name: item for item in db_showcases}
    
    result = []
    for name, meta in AVAILABLE_SHOWCASES.items():
        db_item = status_map.get(name)
        result.append({
            "name": name,
            "title": meta["title"],
            "description": meta["description"],
            "gke_features": meta["gke_features"],
            "status": db_item.status if db_item else "DORMANT",
            "namespace": db_item.namespace if db_item else None,
            "reach_out_url": db_item.reach_out_url if db_item else None,
            "installed_at": db_item.installed_at if db_item else None
        })
    return result

@app.post("/api/showcases/{name}/deploy", dependencies=api_dependencies)
async def deploy_feature(
    name: str, 
    body: dict = Body(default={"namespace": ""}), 
    db: Session = Depends(database.get_db)
):
    if name not in AVAILABLE_SHOWCASES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Showcase '{name}' not supported.")
        
    namespace_override = body.get("namespace", "").strip()
    # Invoke dynamic async deployer
    showcase = await k8s_client.deploy_showcase(
        name=name,
        namespace=namespace_override,
        db_session=db,
        SessionLocal=database.SessionLocal # Pass factory for mock background task
    )
    return {
        "name": showcase.name,
        "status": showcase.status,
        "namespace": showcase.namespace,
        "message": f"Showcase '{AVAILABLE_SHOWCASES[name]['title']}' successfully initiated in namespace '{showcase.namespace}'."
    }

@app.delete("/api/showcases/{name}/teardown", dependencies=api_dependencies)
async def teardown_feature(name: str, db: Session = Depends(database.get_db)):
    if name not in AVAILABLE_SHOWCASES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Showcase '{name}' not supported.")
        
    showcase = db.query(database.ShowcaseModel).filter_by(name=name).first()
    if not showcase or showcase.status == "DORMANT":
        return {"name": name, "status": "DORMANT", "message": "Showcase is already in dormant state."}
        
    # Invoke dynamic teardown
    await k8s_client.teardown_showcase(name=name, namespace=showcase.namespace, db_session=db)
    return {
        "name": name,
        "status": "DORMANT",
        "message": f"Showcase '{AVAILABLE_SHOWCASES[name]['title']}' namespace and GKE resources successfully torn down."
    }

@app.get("/api/showcases/{name}/logs", dependencies=api_dependencies)
async def get_logs(name: str, db: Session = Depends(database.get_db)):
    if name not in AVAILABLE_SHOWCASES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Showcase '{name}' not supported.")
        
    showcase = db.query(database.ShowcaseModel).filter_by(name=name).first()
    target_namespace = showcase.namespace if showcase and showcase.namespace else f"gke-showcase-{name}"
    
    logs = await k8s_client.get_showcase_logs(name=name, namespace=target_namespace)
    return {"name": name, "namespace": target_namespace, "logs": logs}
