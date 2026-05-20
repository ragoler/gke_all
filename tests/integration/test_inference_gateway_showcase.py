import os
import sys
import pytest
from unittest import mock
from fastapi.testclient import TestClient

# Ensure showcase_admin is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app import k8s_client, config, database
from showcase_admin.app.main import app
from showcase_admin.app.database import Base, engine, ShowcaseModel

@pytest.fixture(autouse=True, name="mock_db")
def fixture_mock_db():
    engine.dispose()
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def fixture_client():
    return TestClient(app)

@pytest.mark.anyio
async def test_mock_inference_gateway_ip_fallback():
    """Verify fallback IP resolution for inference-gateway in mock mode."""
    original_mode = config.MODE
    config.MODE = "MOCK"
    try:
        ip_gw = await k8s_client.get_gateway_ip("gke-showcase-inference-gateway", "inference-gateway")
        assert "inference-gateway-svc" in ip_gw, f"Expected inference-gateway-svc fallback, got {ip_gw}"
    finally:
        config.MODE = original_mode

@pytest.mark.anyio
async def test_mock_query_inference_gateway():
    """Verify query_inference_gateway mock response format and priority."""
    original_mode = config.MODE
    config.MODE = "MOCK"
    try:
        reply = await k8s_client.query_inference_gateway("gke-showcase-inference-gateway", "Test AI prompt", "critical")
        assert "MOCK INFERENCE GATEWAY" in reply
        assert "Test AI prompt" in reply
        assert "CRITICAL" in reply
    finally:
        config.MODE = original_mode

@pytest.mark.anyio
async def test_deploy_inference_gateway_showcase():
    """Verify deployment and manifest parsing of CRDs for inference-gateway."""
    original_mode = config.MODE
    config.MODE = "MOCK"
    try:
        db = database.SessionLocal()
        try:
            showcase = await k8s_client.deploy_showcase(
                name="inference-gateway", 
                namespace="gke-showcase-inference-gateway", 
                db_session=db
            )
            assert showcase is not None
            assert showcase.name == "inference-gateway"
            assert showcase.status == "ACTIVE"
            assert showcase.reach_out_url == "/gateway/"
        finally:
            db.close()
    finally:
        config.MODE = original_mode

def test_api_gateway_playroom_routes(client):
    """Verify FastAPI endpoints for serving UI and handling priority queue requests."""
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        # Test HTML Playroom UI endpoint
        resp_ui = client.get("/gateway/")
        assert resp_ui.status_code == 200
        assert "GKE Advanced Inference Gateway Console" in resp_ui.text

        # Test POST request API
        resp_req = client.post("/api/gateway/request", json={"prompt": "Simulate L7 queueing", "priority": "critical"})
        assert resp_req.status_code == 200
        data = resp_req.json()
        assert "MOCK INFERENCE GATEWAY" in data["reply"]
        assert "CRITICAL" in data["reply"]
    finally:
        app.dependency_overrides.clear()
