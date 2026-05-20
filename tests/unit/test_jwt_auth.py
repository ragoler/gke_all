import os
import sys
from unittest import mock
import pytest
from datetime import timedelta
import jwt
from fastapi.testclient import TestClient

# Ensure showcase_admin is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.main import app
from showcase_admin.app.auth import create_access_token, verify_admin_credentials
from showcase_admin.app import config
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


def test_token_generation_and_validation():
    data = {"sub": "admin"}
    token = create_access_token(data, expires_delta=timedelta(minutes=15))
    assert isinstance(token, str)
    assert len(token) > 0
    
    # Decode token directly
    payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
    assert payload.get("sub") == "admin"
    assert "exp" in payload

def test_token_expiration():
    # Create an expired token
    token = create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-10))
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])

def test_login_success(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "pass"):
        
        response = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 86400

def test_login_failure(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "pass"):
        
        response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

def test_protected_api_access_without_token(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True):
        response = client.get("/api/showcases")
        assert response.status_code == 401

def test_protected_api_access_with_valid_token(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True), \
         mock.patch("showcase_admin.app.config.ADMIN_USERNAME", "admin"), \
         mock.patch("showcase_admin.app.config.ADMIN_PASSWORD", "pass"), \
         mock.patch("showcase_admin.app.config.JWT_SECRET_KEY", "super-secret-jwt-signing-key-32-bytes"):
        
        # Get token
        login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "pass"})
        token = login_resp.json()["access_token"]
        
        # Access protected route
        response = client.get("/api/showcases", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

def test_root_unauthenticated_access(client):
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
