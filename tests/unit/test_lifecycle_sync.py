import os
import sys
import asyncio
import pytest
from unittest import mock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from showcase_admin.app.main import app
from showcase_admin.app import database, k8s_client

test_db_path = "/tmp/test_sync_isolated.db"
if os.path.exists(test_db_path):
    try:
        os.remove(test_db_path)
    except:
        pass

test_engine = create_engine(f"sqlite:///{test_db_path}", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True, name="isolated_test_db")
def fixture_isolated_test_db():
    test_engine.dispose()
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except:
            pass
    database.Base.metadata.create_all(bind=test_engine)
    yield
    test_engine.dispose()
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except:
            pass

@pytest.fixture(name="client")
def fixture_client():
    app.dependency_overrides[database.get_db] = override_get_db
    with mock.patch("showcase_admin.app.database.SessionLocal", TestSessionLocal):
        yield TestClient(app)
    app.dependency_overrides.clear()

def test_teardown_lifecycle_state_sync(client):
    from showcase_admin.app.auth import verify_admin_credentials
    app.dependency_overrides[verify_admin_credentials] = lambda: True
    try:
        res = client.post("/api/showcases/agent-sandbox/deploy", json={"namespace": "sync-ns"})
        assert res.status_code == 200
        
        db = TestSessionLocal()
        showcase = db.query(database.ShowcaseModel).filter_by(name="agent-sandbox").first()
        assert showcase.status in ["ACTIVE", "DEPLOYING"]
        assert showcase.namespace == "sync-ns"
        db.close()
        
        res = client.delete("/api/showcases/agent-sandbox/teardown")
        assert res.status_code == 200
        data = res.json()
        
        assert data["name"] == "agent-sandbox"
        assert data["status"] == "TERMINATING"
        
        db = TestSessionLocal()
        showcase = db.query(database.ShowcaseModel).filter_by(name="agent-sandbox").first()
        assert showcase.status == "DORMANT"
        assert showcase.namespace is None
        db.close()
    finally:
        app.dependency_overrides.clear()

@pytest.mark.anyio
async def test_async_teardown_polling_completion():
    with mock.patch("showcase_admin.app.database.SessionLocal", TestSessionLocal):
        db = TestSessionLocal()
        showcase = database.ShowcaseModel(name="gpu-inference", namespace="gpu-ns", status="ACTIVE")
        db.add(showcase)
        db.commit()
        db.close()
        
        await k8s_client.teardown_showcase("gpu-inference", "gpu-ns", SessionLocal=TestSessionLocal)
        
        db = TestSessionLocal()
        showcase = db.query(database.ShowcaseModel).filter_by(name="gpu-inference").first()
        assert showcase.status == "DORMANT"
        assert showcase.namespace is None
        assert showcase.reach_out_url is None
        db.close()

