import os
import sys
import pytest

try:
    import jwt
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--index-url", "https://pypi.org/simple", "pyjwt>=2.8.0"])


# Ensure workspace directory is in the Python search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Global defaults for test authentication
os.environ["ADMIN_AUTHENTICATION_ENABLED"] = "TRUE"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "mock-pass"

def pytest_addoption(parser):
    parser.addoption(
        "--run-live-gke", action="store_true", default=False, help="run live GKE cluster integration tests"
    )

def pytest_configure(config):
    config.addinivalue_line("markers", "gke: mark test to run against live GKE cluster")
    config.addinivalue_line("markers", "asyncio: mark test as an async coroutine")

def pytest_collection_modifyitems(config, items):
    from showcase_admin.app import config as app_config
    # By default, maintain MOCK mode for local offline unit testing
    os.environ["MODE"] = "MOCK"
    app_config.MODE = "MOCK"
    
    if not config.getoption("--run-live-gke"):
        skip_gke = pytest.mark.skip(reason="need --run-live-gke CLI option to run live cloud tests")
        for item in items:
            if "gke" in item.keywords:
                item.add_marker(skip_gke)

