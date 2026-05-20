import os
import sys
import pytest
from fastapi.testclient import TestClient
from unittest import mock

# Ensure showcase_admin is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.main import app
from showcase_admin.app import k8s_client
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
    return TestClient(app)

def test_telemetry_api_unauthorized(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True):
        response = client.get("/api/stats")
        assert response.status_code == 401

@pytest.mark.anyio
async def test_telemetry_mock_aggregation():
    with mock.patch("showcase_admin.app.config.MODE", "MOCK"):
        data = await k8s_client.get_cluster_stats()
        assert data["mode"] == "MOCK"
        assert data["nodes"]["total"] == 2
        assert data["nodes"]["ready"] == 2
        assert data["namespaces"]["total"] == 5
        assert data["pods"]["total"] == 14
        assert data["pods"]["running"] == 12
        assert data["accelerators"]["nvidia_l4"] == 1
        assert data["accelerators"]["gvisor"] == 2

def test_telemetry_api_authorized(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "pass"), \
         mock.patch("showcase_admin.app.config.JWT_SECRET_KEY", "super-secret-jwt-signing-key-32-bytes"), \
         mock.patch("showcase_admin.app.config.MODE", "MOCK"):
        
        login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        response = client.get("/api/stats", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "MOCK"
        assert data["nodes"]["total"] == 2
        assert data["namespaces"]["total"] == 5
        assert data["pods"]["running"] == 12
        assert data["accelerators"]["nvidia_l4"] == 1
        assert data["accelerators"]["gvisor"] == 2
