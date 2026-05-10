import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure showcase_admin is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.database import Base, ShowcaseModel

# In-memory SQLite database for fast, isolated unit testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_create_and_query_showcase(db_session):
    # Insert a showcase
    showcase = ShowcaseModel(
        name="agent-sandbox",
        namespace="custom-sandbox",
        status="DEPLOYING",
        reach_out_url=None
    )
    db_session.add(showcase)
    db_session.commit()
    
    # Query showcase
    fetched = db_session.query(ShowcaseModel).filter_by(name="agent-sandbox").first()
    assert fetched is not None
    assert fetched.namespace == "custom-sandbox"
    assert fetched.status == "DEPLOYING"
    assert fetched.reach_out_url is None

def test_update_showcase_status(db_session):
    showcase = ShowcaseModel(name="gpu-inference", status="DORMANT")
    db_session.add(showcase)
    db_session.commit()
    
    # Update state
    fetched = db_session.query(ShowcaseModel).filter_by(name="gpu-inference").first()
    fetched.status = "ACTIVE"
    fetched.reach_out_url = "http://localhost/inference"
    db_session.commit()
    
    updated = db_session.query(ShowcaseModel).filter_by(name="gpu-inference").first()
    assert updated.status == "ACTIVE"
    assert updated.reach_out_url == "http://localhost/inference"

def test_duplicate_showcase_name_fails(db_session):
    from sqlalchemy.exc import IntegrityError
    
    showcase1 = ShowcaseModel(name="agent-sandbox")
    showcase2 = ShowcaseModel(name="agent-sandbox")
    
    db_session.add(showcase1)
    db_session.commit()
    
    db_session.add(showcase2)
    with pytest.raises(IntegrityError):
        db_session.commit()
