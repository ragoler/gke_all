import os
import sys
import pytest
from unittest import mock

# Ensure showcase_admin in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.k8s_client import expand_template, apply_yaml_manifests, deploy_showcase
from showcase_admin.app.database import Base, engine, SessionLocal, ShowcaseModel

@pytest.fixture(autouse=True, name="init_memory_db")
def fixture_init_memory_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_expand_template():
    raw_yaml = "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: ${NAMESPACE}\n  project: ${PROJECT_NAME}"
    vars_dict = {"NAMESPACE": "custom-ns", "PROJECT_NAME": "my-gcp-proj"}
    
    expanded = expand_template(raw_yaml, vars_dict)
    assert "custom-ns" in expanded
    assert "my-gcp-proj" in expanded
    assert "${NAMESPACE}" not in expanded
    assert "${PROJECT_NAME}" not in expanded

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_deploy_showcase_real_mode(mock_init, init_memory_db):
    # Mock CoreV1Api and CustomObjectsApi
    mock_core_instance = mock.AsyncMock()
    mock_apps_instance = mock.AsyncMock()
    mock_custom_instance = mock.AsyncMock()
    
    # We patch the ApiClient, gcloud CLI commands, and specific client builders
    with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core_instance), \
         mock.patch("kubernetes_asyncio.client.AppsV1Api", return_value=mock_apps_instance), \
         mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom_instance), \
         mock.patch("showcase_admin.app.k8s_client.run_gcloud_cmd", new_callable=mock.AsyncMock) as mock_gcloud, \
         mock.patch("kubernetes_asyncio.client.ApiClient") as mock_client_class:
        
        # Simulate that the pool exists to prevent dynamic creation trigger
        mock_gcloud.return_value = "showcase-gvisor-pool"
        
        db = SessionLocal()
        try:
            # Trigger deploy under REAL mode
            showcase = await deploy_showcase(
                name="agent-sandbox",
                namespace="test-real-ns",
                db_session=db
            )
            
            assert showcase.name == "agent-sandbox"
            assert showcase.status == "ACTIVE"
            assert showcase.namespace == "test-real-ns"
            
            # Verify CoreV1Api.create_namespace was called once
            mock_core_instance.create_namespace.assert_called_once()
        finally:
            db.close()
