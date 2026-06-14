from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Body, status, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
import os
import logging
from datetime import timedelta
from pydantic import BaseModel
import secrets

from showcase_admin.app import config, database, auth, k8s_client, features as feature_registry

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

# Mirror each feature's playroom UI (features/<name>/<frontend_dir>/) into the served
# static root. Runs at import so dev, tests, and the container image stay consistent
# and submodule features' UIs are served with no manual copy step.
feature_registry.aggregate_frontends(os.path.join(frontend_dir, 'features'))

# Serve Frontend SPA UI
@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_path = os.path.join(frontend_dir, 'index.html')
    if os.path.exists(index_path):
        response = FileResponse(index_path)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    raise HTTPException(status_code=404, detail="index.html file not found.")


# Mount static assets
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# ----------------------------------------------------------------------
# SERVE DEDICATED MODULAR PLAYROOM UIs
# ----------------------------------------------------------------------
# Playroom routes are registered dynamically from each feature's feature.yaml
# descriptor (paths.playroom_slug), so adding a feature needs no Hub code change.
def _make_playroom_handler(feature_name: str):
    """Build a FastAPI handler serving the playroom index.html for one feature."""
    async def serve_playroom() -> FileResponse:
        playroom_html = os.path.join(frontend_dir, 'features', feature_name, 'index.html')
        if os.path.exists(playroom_html):
            response = FileResponse(playroom_html)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
        raise HTTPException(status_code=404, detail=f"Playroom for '{feature_name}' not found.")
    return serve_playroom

for _slug, _feature_name in feature_registry.playroom_routes():
    app.add_api_route(
        f"/{_slug}/",
        _make_playroom_handler(_feature_name),
        methods=["GET"],
        response_class=HTMLResponse,
        name=f"serve_{_feature_name}_playroom",
    )

# Available Features Metadata (derived from features/*/feature.yaml — see feature.md)
AVAILABLE_SHOWCASES = feature_registry.available_showcases()

# ----------------------------------------------------------------------
# CORE BACKEND ADMINISTRATIVE APIs
# ----------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
async def login(credentials: LoginRequest):
    correct_username = secrets.compare_digest(credentials.username, config.ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, config.ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
        
    expires_in = 86400
    token = auth.create_access_token(
        data={"sub": credentials.username},
        expires_delta=timedelta(seconds=expires_in)
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in
    }

@app.get("/api/showcases", dependencies=api_dependencies)
async def list_showcases(background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    db_showcases = db.query(database.ShowcaseModel).all()
    status_map = {item.name: item for item in db_showcases}
    
    result = []
    for name, meta in AVAILABLE_SHOWCASES.items():
        db_item = status_map.get(name)
        
        # Dynamically resolve reach out URL pointing to localhost or external Gateway IP
        reach_out_url = None
        if db_item and db_item.status == "ACTIVE":
            reach_out_url = k8s_client.FEATURE_URL_MAP.get(name)
            
        if db_item and db_item.status in ("DEPLOYING", "PROVISIONING"):
            background_tasks.add_task(k8s_client.check_and_update_showcase_status, name, db_item.namespace)
            
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

@app.get("/api/stats", dependencies=api_dependencies)
async def get_cluster_stats():
    return await k8s_client.get_cluster_stats()

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
    llm_provider = body.get("llm_provider", "vertex")
    llm_service_endpoint = body.get("llm_service_endpoint", "")
    
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
        llm_provider=llm_provider,
        llm_service_endpoint=llm_service_endpoint,
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
    if not showcase or showcase.status in ["DORMANT", "TERMINATING"]:
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
# PER-FEATURE DATA-PLANE ROUTERS (each feature owns its own proxy)
# ----------------------------------------------------------------------
# Every feature ships its own FastAPI router (declared via hub_router in
# feature.yaml). The Hub mounts each one under /api/features/<name>, so a feature's
# data-plane API is fully independent — added/removed with the feature, namespaced
# so features can never collide, and requiring zero edits to this file.
for _feature_name, _feature_router in feature_registry.load_routers().items():
    app.include_router(
        _feature_router,
        prefix=f"/api/features/{_feature_name}",
        tags=[_feature_name],
        dependencies=api_dependencies,
    )
