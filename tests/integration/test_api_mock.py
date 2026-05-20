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
        assert len(data) == 2
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
