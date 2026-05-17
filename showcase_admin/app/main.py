from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Body, status, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
import os
import uuid
import httpx
import logging
from datetime import datetime, timezone

from showcase_admin.app import config, database, auth, k8s_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    raise HTTPException(status_code=404, detail="index.html file not found.")

# Mount static assets
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# ----------------------------------------------------------------------
# SERVE DEDICATED MODULAR PLAYROOM UIs
# ----------------------------------------------------------------------
@app.get("/sandbox/", response_class=HTMLResponse, dependencies=api_dependencies)
async def serve_sandbox_playroom():
    sandbox_html = os.path.join(frontend_dir, 'features', 'agent-sandbox', 'index.html')
    if os.path.exists(sandbox_html):
        return FileResponse(sandbox_html)
    raise HTTPException(status_code=404, detail="Sandbox playroom file not found.")

@app.get("/inference/", response_class=HTMLResponse, dependencies=api_dependencies)
async def serve_inference_playroom():
    inference_html = os.path.join(frontend_dir, 'features', 'gpu-inference', 'index.html')
    if os.path.exists(inference_html):
        return FileResponse(inference_html)
    raise HTTPException(status_code=404, detail="Inference playroom file not found.")

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

def get_feature_namespace(db: Session, feature_name: str) -> str:
    showcase = db.query(database.ShowcaseModel).filter_by(name=feature_name).first()
    return showcase.namespace if showcase and showcase.namespace else f"gke-showcase-{feature_name}"

# ----------------------------------------------------------------------
# CORE BACKEND ADMINISTRATIVE APIs
# ----------------------------------------------------------------------
@app.get("/api/showcases", dependencies=api_dependencies)
async def list_showcases(db: Session = Depends(database.get_db)):
    db_showcases = db.query(database.ShowcaseModel).all()
    status_map = {item.name: item for item in db_showcases}
    
    result = []
    for name, meta in AVAILABLE_SHOWCASES.items():
        db_item = status_map.get(name)
        
        # Dynamically resolve reach out URL pointing to localhost or external Gateway IP
        reach_out_url = None
        if db_item and db_item.status == "ACTIVE":
            # Redirect to dedicated served frontend routes
            reach_out_url = f"/sandbox/" if name == "agent-sandbox" else f"/inference/"
            
        result.append({
            "name": name,
            "title": meta["title"],
            "description": meta["description"],
            "gke_features": meta["gke_features"],
            "status": db_item.status if db_item else "DORMANT",
            "namespace": db_item.namespace if db_item else None,
            "reach_out_url": reach_out_url,
            "installed_at": db_item.installed_at if db_item else None
        })
    return result

@app.post("/api/showcases/{name}/deploy", dependencies=api_dependencies)
async def deploy_feature(
    name: str, 
    background_tasks: BackgroundTasks,
    body: dict = Body(default={"namespace": ""}), 
    db: Session = Depends(database.get_db)
):
    if name not in AVAILABLE_SHOWCASES:
        raise HTTPException(status_code=404, detail=f"Showcase '{name}' not supported.")
        
    namespace_override = body.get("namespace", "").strip()
    target_ns = namespace_override if namespace_override else f"gke-showcase-{name}"
    
    # Immediately commit DEPLOYING status and release the request thread
    showcase = db.query(database.ShowcaseModel).filter_by(name=name).first()
    if not showcase:
        showcase = database.ShowcaseModel(name=name)
        db.add(showcase)
    showcase.namespace = target_ns
    showcase.status = "DEPLOYING"
    showcase.reach_out_url = None
    showcase.installed_at = database.get_utc_now()
    db.commit()
    
    # Dispatch actual GKE deployment in the background
    background_tasks.add_task(
        k8s_client.deploy_showcase,
        name=name,
        namespace=target_ns,
        SessionLocal=database.SessionLocal
    )
    
    return {
        "name": name,
        "status": "DEPLOYING",
        "namespace": target_ns,
        "message": f"Showcase deployment for '{AVAILABLE_SHOWCASES[name]['title']}' successfully initiated in the background."
    }

@app.delete("/api/showcases/{name}/teardown", dependencies=api_dependencies)
async def teardown_feature(
    name: str, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db)
):
    if name not in AVAILABLE_SHOWCASES:
        raise HTTPException(status_code=404, detail=f"Showcase '{name}' not supported.")
        
    showcase = db.query(database.ShowcaseModel).filter_by(name=name).first()
    if not showcase or showcase.status == "DORMANT":
        return {"name": name, "status": "DORMANT", "message": "Showcase already dormant or terminating."}
        
    # Immediately commit TERMINATING status
    target_ns = showcase.namespace
    showcase.status = "TERMINATING"
    showcase.reach_out_url = None
    db.commit()
    
    # Dispatch GKE teardown in the background
    background_tasks.add_task(
        k8s_client.teardown_showcase,
        name=name,
        namespace=target_ns,
        SessionLocal=database.SessionLocal
    )
    
    return {
        "name": name,
        "status": "TERMINATING",
        "message": "Showcase dynamic teardown initiated successfully."
    }

@app.get("/api/showcases/{name}/logs", dependencies=api_dependencies)
async def get_logs(name: str, db: Session = Depends(database.get_db)):
    if name not in AVAILABLE_SHOWCASES:
        raise HTTPException(status_code=404, detail=f"Showcase '{name}' not supported.")
        
    showcase = db.query(database.ShowcaseModel).filter_by(name=name).first()
    target_namespace = showcase.namespace if showcase and showcase.namespace else f"gke-showcase-{name}"
    
    logs = await k8s_client.get_showcase_logs(name=name, namespace=target_namespace)
    return {"name": name, "namespace": target_namespace, "logs": logs}

# ----------------------------------------------------------------------
# DEDICATED SHOWCASE DYNAMIC PLAYROOM REST APIs
# ----------------------------------------------------------------------

# --- FEATURE 1: AGENT SANDBOX CLAIMS MANAGEMENT ---
@app.get("/api/sandboxes", dependencies=api_dependencies)
async def list_sandbox_claims(db: Session = Depends(database.get_db)):
    ns = get_feature_namespace(db, "agent-sandbox")
    claims = await k8s_client.list_sandbox_claims(ns)
    return claims

@app.post("/api/sandboxes", dependencies=api_dependencies)
async def create_sandbox_claim(db: Session = Depends(database.get_db)):
    ns = get_feature_namespace(db, "agent-sandbox")
    claim_id = f"sb-{uuid.uuid4().hex[:8]}"
    claim = await k8s_client.create_sandbox_claim(ns, claim_id)
    return claim

@app.delete("/api/sandboxes/{claim_id}", dependencies=api_dependencies)
async def delete_sandbox_claim(claim_id: str, db: Session = Depends(database.get_db)):
    ns = get_feature_namespace(db, "agent-sandbox")
    await k8s_client.delete_sandbox_claim(ns, claim_id)
    return {"status": "released", "id": claim_id}

@app.post("/api/sandboxes/{claim_id}/message", dependencies=api_dependencies)
async def message_sandbox(
    claim_id: str,
    body: dict = Body(...),
    db: Session = Depends(database.get_db)
):
    ns = get_feature_namespace(db, "agent-sandbox")
    prompt = body.get("message", "")
    provider = body.get("provider", "vertex") # 'vertex' or 'vllm'
    
    vllm_ns = get_feature_namespace(db, "gpu-inference")
    
    reply = await k8s_client.message_sandbox_claim(
        namespace=ns,
        claim_id=claim_id,
        message=prompt,
        provider=provider,
        vllm_namespace=vllm_ns
    )
    return {"reply": reply}

@app.post("/api/sandboxes/{claim_id}/quote", dependencies=api_dependencies)
async def quote_sandbox(
    claim_id: str,
    body: dict = Body(default={"provider": "vertex"}),
    db: Session = Depends(database.get_db)
):
    ns = get_feature_namespace(db, "agent-sandbox")
    provider = body.get("provider", "vertex")
    vllm_ns = get_feature_namespace(db, "gpu-inference")
    
    quote = await k8s_client.quote_sandbox_claim(
        namespace=ns,
        claim_id=claim_id,
        provider=provider,
        vllm_namespace=vllm_ns
    )
    return {"quote": quote}

# --- FEATURE 2: GPU INFERENCE MODEL PLAYS ---
@app.post("/api/inference/chat", dependencies=api_dependencies)
async def model_garden_inference(
    body: dict = Body(...),
    db: Session = Depends(database.get_db)
):
    prompt = body.get("prompt", "")
    ns = get_feature_namespace(db, "gpu-inference")
    
    reply = await k8s_client.query_gpu_inference_server(ns, prompt)
    return {"reply": reply}
