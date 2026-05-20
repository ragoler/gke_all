import asyncio
import os
import sys
import pytest
from unittest import mock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.k8s_client import deploy_showcase, teardown_showcase
from showcase_admin.app.database import Base, ShowcaseModel

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="resilience_db_session")
def fixture_resilience_db_session():
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "MOCK")
@mock.patch("asyncio.sleep", new_callable=mock.AsyncMock)
async def test_repeated_deploy_teardown_resilience(mock_sleep, resilience_db_session):
    """Simulate 10 repeated deploy/teardown cycles across multiple concurrent showcase models in SQLite memory DB."""
    showcases = [("agent-sandbox", "ns-sandbox"), ("gpu-inference", "ns-inference")]
    
    for cycle in range(10):
        # 1. Concurrent Deploy
        deploy_tasks = [
            deploy_showcase(name=name, namespace=ns, db_session=resilience_db_session)
            for name, ns in showcases
        ]
        deployed_models = await asyncio.gather(*deploy_tasks)
        
        for model in deployed_models:
            assert model.status == "ACTIVE"
            assert model.reach_out_url is not None
            
        # 2. Verify in DB
        for name, ns in showcases:
            fetched = resilience_db_session.query(ShowcaseModel).filter_by(name=name).first()
            assert fetched is not None
            assert fetched.status == "ACTIVE"
            assert fetched.namespace == ns
            
        # 3. Concurrent Teardown
        teardown_tasks = [
            teardown_showcase(name=name, namespace=ns, db_session=resilience_db_session)
            for name, ns in showcases
        ]
        teardown_models = await asyncio.gather(*teardown_tasks)
        
        for model in teardown_models:
            assert model.status == "DORMANT"
            assert model.reach_out_url is None
            assert model.namespace is None
            
        # 4. Verify in DB
        for name, _ in showcases:
            fetched = resilience_db_session.query(ShowcaseModel).filter_by(name=name).first()
            assert fetched is not None
            assert fetched.status == "DORMANT"
