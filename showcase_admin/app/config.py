import os

# Helper to load .env file if present
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    # Strip optional surrounding quotes
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val

# Load on module import
load_env_file()

# Core settings exposed as variables
MODE = os.getenv("MODE", "MOCK").upper()
ADMIN_AUTHENTICATION_ENABLED = os.getenv("ADMIN_AUTHENTICATION_ENABLED", "FALSE").upper() == "TRUE"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin-password")

PROJECT_NAME = os.getenv("PROJECT_NAME", "your-gcp-project-id")
REGION = os.getenv("REGION", "us-west1")
CLUSTER_NAME = os.getenv("CLUSTER_NAME", "gke-showcase-cluster")
CLUSTER_VERSION = os.getenv("CLUSTER_VERSION", "1.35.2-gke.1269000")
NODE_POOL_NAME = os.getenv("NODE_POOL_NAME", "showcase-node-pool")
MACHINE_TYPE = os.getenv("MACHINE_TYPE", "e2-standard-2")
ARTIFACT_REGISTRY_REPO = os.getenv("ARTIFACT_REGISTRY_REPO", "gke-showcase-repo")

GATEWAY_NAME = os.getenv("GATEWAY_NAME", "external-http-gateway")

GOOGLE_GENAI_USE_VERTEXAI = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").upper() == "TRUE"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MODEL_NAME = os.getenv("MODEL_NAME", "gemma-2b-it")
GCS_MODEL_BUCKET = os.getenv("GCS_MODEL_BUCKET", "")
