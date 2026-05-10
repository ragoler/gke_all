import os
import sys
from unittest import mock

# Ensure showcase-admin is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

def test_config_defaults():
    # Mock env and prevent loading the filesystem .env file
    with mock.patch.dict(os.environ, {}, clear=True), \
         mock.patch("os.path.exists", return_value=False):
        # Reload config inside mock context
        import importlib
        import showcase_admin.app.config as config
        importlib.reload(config)
        
        assert config.MODE == "MOCK"
        assert config.ADMIN_AUTHENTICATION_ENABLED is False
        assert config.REGION == "us-west1"
        assert config.CLUSTER_NAME == "gke-showcase-cluster"

def test_config_overrides():
    custom_env = {
        "MODE": "REAL",
        "ADMIN_AUTHENTICATION_ENABLED": "TRUE",
        "ADMIN_USERNAME": "super-admin",
        "ADMIN_PASSWORD": "super-password",
        "CLUSTER_NAME": "my-custom-cluster"
    }
    # Mock env and prevent loading the filesystem .env file
    with mock.patch.dict(os.environ, custom_env, clear=True), \
         mock.patch("os.path.exists", return_value=False):
        import importlib
        import showcase_admin.app.config as config
        importlib.reload(config)
        
        assert config.MODE == "REAL"
        assert config.ADMIN_AUTHENTICATION_ENABLED is True
        assert config.ADMIN_USERNAME == "super-admin"
        assert config.ADMIN_PASSWORD == "super-password"
        assert config.CLUSTER_NAME == "my-custom-cluster"
