import os
import sys
import pytest
from fastapi.testclient import TestClient
from unittest import mock

# Ensure showcase_admin is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import app configurations
from showcase_admin.app.main import app
from showcase_admin.app.database import Base, engine

@pytest.fixture(autouse=True, name="mock_db")
def fixture_mock_db():
    engine.dispose()
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def fixture_client():
    # Clear any background tasks loop during standard synchronous testclient queries
    return TestClient(app)

def test_api_unauthorized_access(client):
    # Mock auth enabled
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True):
        response = client.get("/api/showcases")
        assert response.status_code == 401

def test_api_authorized_get_showcases(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "pass"), \
         mock.patch("showcase_admin.app.config.JWT_SECRET_KEY", "super-secret-jwt-signing-key-32-bytes"):
        
        login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        response = client.get("/api/showcases", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        names = {s["name"] for s in data}
        assert {"agent-sandbox", "gpu-inference", "inference-gateway", "ray"} <= names
        assert data[0]["name"] == "agent-sandbox"
        assert data[0]["status"] == "DORMANT"

def test_api_deploy_feature(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "pass"), \
         mock.patch("showcase_admin.app.config.JWT_SECRET_KEY", "super-secret-jwt-signing-key-32-bytes"):
        
        login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        response = client.post(
            "/api/showcases/agent-sandbox/deploy",
            json={"namespace": "my-test-sandbox"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "agent-sandbox"
        # In synchronous mock deployer inside client execution, status updates immediately to ACTIVE
        assert data["status"] in ["ACTIVE", "DEPLOYING"]
        assert data["namespace"] == "my-test-sandbox"


def test_api_teardown_feature(client):
    # Override dependency to bypass auth header check entirely
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        # First deploy to establish state
        client.post("/api/showcases/gpu-inference/deploy", json={"namespace": "inference-ns"})
        
        # Then tear down
        response = client.delete("/api/showcases/gpu-inference/teardown")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "gpu-inference"
        assert data["status"] == "TERMINATING"
    finally:
        # Clear overrides
        app.dependency_overrides.clear()

def test_api_get_logs(client):
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        response = client.get("/api/showcases/agent-sandbox/logs")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "agent-sandbox"
        assert "Initializing namespace" in data["logs"]
    finally:
        app.dependency_overrides.clear()

def test_api_html_playrooms(client):
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        resp_root = client.get("/")
        assert resp_root.status_code == 200
        
        resp_sb = client.get("/sandbox/")
        assert resp_sb.status_code == 200
        
        resp_inf = client.get("/inference/")
        assert resp_inf.status_code == 200

        resp_ray = client.get("/ray/")
        assert resp_ray.status_code == 200
    finally:
        app.dependency_overrides.clear()

def test_api_cluster_stats(client):
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "MOCK"
    finally:
        app.dependency_overrides.clear()

def test_api_sandbox_claims(client):
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        # 1. Create claim
        create_resp = client.post("/api/features/agent-sandbox/sandboxes")
        assert create_resp.status_code == 200
        claim_data = create_resp.json()
        claim_id = claim_data["id"]
        
        # 2. List claims
        list_resp = client.get("/api/features/agent-sandbox/sandboxes")
        assert list_resp.status_code == 200
        assert any(item["id"] == claim_id for item in list_resp.json())
        
        # 3. Message claim
        msg_resp = client.post(f"/api/features/agent-sandbox/sandboxes/{claim_id}/message", json={"message": "hello test", "provider": "vertex"})
        assert msg_resp.status_code == 200
        assert "Recieved your prompt 'hello test'" in msg_resp.json()["reply"]
        
        # 4. Quote claim
        quote_resp = client.post(f"/api/features/agent-sandbox/sandboxes/{claim_id}/quote", json={"provider": "vertex"})
        assert quote_resp.status_code == 200
        assert "predict the future" in quote_resp.json()["quote"]
        
        # 5. Delete claim
        del_resp = client.delete(f"/api/features/agent-sandbox/sandboxes/{claim_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["id"] == claim_id
    finally:
        app.dependency_overrides.clear()

def test_api_inference_chat(client):
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        resp = client.post("/api/features/gpu-inference/chat", json={"prompt": "What is AI?"})
        assert resp.status_code == 200
        assert "MOCK INFERENCE" in resp.json()["reply"]
    finally:
        app.dependency_overrides.clear()

def test_api_ray_render(client):
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        # 1. Config reports MOCK (no cluster).
        cfg = client.get("/api/features/ray/config")
        assert cfg.status_code == 200
        assert cfg.json()["mode"] == "MOCK"

        # 2. Presets are served.
        presets = client.get("/api/features/ray/presets")
        assert presets.status_code == 200
        assert "seahorse" in presets.json()

        # 3. Plan a small render job.
        render = client.post("/api/features/ray/render", json={"resolution": 128})
        assert render.status_code == 200
        job_id = render.json()["job_id"]
        assert job_id

        # 4. Stream the job: a 1-tile render yields meta + tile + done.
        stream = client.get(f"/api/features/ray/render/{job_id}/stream")
        assert stream.status_code == 200
        body = stream.text
        assert '"type": "meta"' in body
        assert '"type": "tile"' in body
        assert '"type": "done"' in body

        # 5. Workers reflect the synthetic autoscaling (head + at least one worker).
        workers = client.get("/api/features/ray/workers")
        assert workers.status_code == 200
        pods = workers.json()["pods"]
        assert any(p["node_type"] == "worker" for p in pods)
    finally:
        app.dependency_overrides.clear()
