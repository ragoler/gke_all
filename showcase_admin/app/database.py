import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from showcase_admin.app import config

# Relational Base class
Base = declarative_base()

# SQLite database URL determination
# Detect if running inside GKE / Docker Container
is_container = os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount") or "KUBERNETES_SERVICE_HOST" in os.environ

if is_container:
    # GKE PVC Mount path (always writable inside GKE pod container)
    os.makedirs("/data", exist_ok=True)
    DATABASE_URL = "sqlite:////data/showcase.db"
else:
    # Local development (macOS / Linux)
    db_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data'))
    os.makedirs(db_dir, exist_ok=True)
    DATABASE_URL = f"sqlite:///{os.path.join(db_dir, 'showcase.db')}"

# Setup SQLAlchemy engine and session
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class ShowcaseModel(Base):
    __tablename__ = "showcases"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False) # e.g., "agent-sandbox", "gpu-inference"
    namespace = Column(String, unique=True, nullable=True)        # custom or default deployed namespace
    status = Column(String, default="DORMANT", nullable=False)     # DORMANT, DEPLOYING, ACTIVE, ERROR
    reach_out_url = Column(String, nullable=True)                 # reach out routing gateway URL
    installed_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def init_db():
    # Create tables if they don't exist in the target engine
    Base.metadata.create_all(engine)

def get_db():
    # Ensure tables are initialized and exist on every session request
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
