import asyncio
from datetime import datetime
from showcase_admin.app import config
from showcase_admin.app.database import ShowcaseModel

# Mock database state updates in background tasks
async def simulate_mock_deployment(name: str, namespace: str, SessionLocal):
    await asyncio.sleep(2)
    db = SessionLocal()
    try:
        showcase = db.query(ShowcaseModel).filter_by(name=name).first()
        if showcase and showcase.status == "DEPLOYING":
            showcase.status = "ACTIVE"
            if name == "agent-sandbox":
                showcase.reach_out_url = "/sandbox/"
            elif name == "gpu-inference":
                showcase.reach_out_url = "/inference/"
            db.commit()
    finally:
        db.close()

async def deploy_showcase(name: str, namespace: str, db_session, SessionLocal=None):
    # Normalize namespace
    target_ns = namespace.strip() if namespace else f"gke-showcase-{name}"
    
    # Fetch or create record
    showcase = db_session.query(ShowcaseModel).filter_by(name=name).first()
    if not showcase:
        showcase = ShowcaseModel(name=name)
        db_session.add(showcase)
        
    showcase.namespace = target_ns
    showcase.status = "DEPLOYING"
    showcase.reach_out_url = None
    showcase.installed_at = datetime.utcnow()
    db_session.commit()
    
    if config.MODE == "MOCK":
        # Spin up background simulated activation
        if SessionLocal:
            asyncio.create_task(simulate_mock_deployment(name, target_ns, SessionLocal))
        else:
            # Fallback synchronous simulated delay if session factory not supplied
            showcase.status = "ACTIVE"
            showcase.reach_out_url = "/sandbox/" if name == "agent-sandbox" else "/inference/"
            db_session.commit()
    else:
        # TODO: Real GKE kubernetes_asyncio client implementation (Milestone 3)
        pass
    return showcase

async def teardown_showcase(name: str, namespace: str, db_session):
    showcase = db_session.query(ShowcaseModel).filter_by(name=name).first()
    if showcase:
        showcase.status = "DORMANT"
        showcase.reach_out_url = None
        showcase.namespace = None
        db_session.commit()
        
    if config.MODE == "MOCK":
        # Instant simulated teardown
        pass
    else:
        # TODO: Real GKE kubernetes_asyncio client teardown (Milestone 3)
        pass
    return showcase

async def get_showcase_logs(name: str, namespace: str) -> str:
    if config.MODE == "MOCK":
        return (
            f"[SYSTEM - {datetime.utcnow().isoformat()}] Initializing namespace: {namespace}\n"
            f"[SYSTEM] Validating Pod Security Standards (PSA: restricted)\n"
            f"[DOCKER] Pulling image: showcase-repo/{name}:latest\n"
            f"[DOCKER] Image successfully resolved from Artifact Registry\n"
            f"[KUBERNETES] Creating deployment service resources...\n"
            f"[APP] Running migrations & binding web frameworks...\n"
            f"[SYSTEM] Dynamic GKE routes updated. Ready for connections."
        )
    else:
        # TODO: Real GKE log capture (Milestone 3)
        return "Real GKE logging not configured yet."
