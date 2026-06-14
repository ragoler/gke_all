import os
import sys
import pytest
from fastapi.testclient import TestClient
from unittest import mock
from kubernetes_asyncio import client

# Ensure showcase_admin is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.main import app
from showcase_admin.app import k8s_client

@pytest.fixture(name="client")
def fixture_client():
    return TestClient(app)

def test_unauthenticated_ui_access(client):
    """Verify that playroom UI endpoints are accessible without authentication."""
    with mock.patch("showcase_admin.app.config.ADMIN_AUTHENTICATION_ENABLED", True):
        for route in ["/sandbox/", "/inference/"]:
            response = client.get(route)
            assert response.status_code == 200, f"Expected 200 for {route}, got {response.status_code}"

@pytest.mark.anyio
async def test_get_cluster_stats_rbac_403():
    """Verify RBAC 403 fallback in get_cluster_stats."""
    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("showcase_admin.app.k8s_client.init_k8s_connection", new_callable=mock.AsyncMock):
        
        mock_api_client_instance = mock.MagicMock()
        mock_api_client_cm = mock.AsyncMock()
        mock_api_client_cm.__aenter__.return_value = mock_api_client_instance
        
        mock_core_v1_instance = mock.MagicMock()
        
        # list_node raises 403 ApiException
        mock_core_v1_instance.list_node = mock.AsyncMock(side_effect=client.exceptions.ApiException(status=403, reason="Forbidden"))
        
        # list_namespace returns mock namespaces
        mock_ns_list = mock.MagicMock()
        mock_ns_list.items = [mock.MagicMock(), mock.MagicMock()]
        mock_core_v1_instance.list_namespace = mock.AsyncMock(return_value=mock_ns_list)
        
        # list_pod_for_all_namespaces returns mock pods
        mock_pod_list = mock.MagicMock()
        mock_pod = mock.MagicMock()
        mock_pod.status.phase = "Running"
        mock_pod.spec.runtime_class_name = "gvisor"
        mock_pod.spec.containers = []
        mock_pod_list.items = [mock_pod]
        mock_core_v1_instance.list_pod_for_all_namespaces = mock.AsyncMock(return_value=mock_pod_list)
        
        with mock.patch("kubernetes_asyncio.client.ApiClient", return_value=mock_api_client_cm), \
             mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core_v1_instance):
            
            stats = await k8s_client.get_cluster_stats()
            
            assert stats["mode"] == "REAL"
            assert stats["nodes"]["total"] == 0
            assert stats["nodes"]["ready"] == 0
            assert stats["namespaces"]["total"] == 2
            assert stats["pods"]["total"] == 1
            assert stats["pods"]["running"] == 1

@pytest.mark.anyio
async def test_get_showcase_logs_bad_request_400():
    """Verify 400 BadRequest log handling in get_showcase_logs."""
    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("showcase_admin.app.k8s_client.init_k8s_connection", new_callable=mock.AsyncMock):
        
        mock_api_client_instance = mock.MagicMock()
        mock_api_client_cm = mock.AsyncMock()
        mock_api_client_cm.__aenter__.return_value = mock_api_client_instance
        
        mock_core_v1_instance = mock.MagicMock()
        
        # list_namespaced_pod returns a pod
        mock_pod_list = mock.MagicMock()
        mock_pod = mock.MagicMock()
        mock_pod.metadata.name = "vllm-pod-1"
        mock_pod.status.phase = "ContainerCreating"
        mock_c = mock.MagicMock()
        mock_c.name = "vllm-container"
        mock_pod.spec.containers = [mock_c]
        mock_pod_list.items = [mock_pod]
        mock_core_v1_instance.list_namespaced_pod = mock.AsyncMock(return_value=mock_pod_list)
        
        # read_namespaced_pod_log raises 400 ApiException
        mock_core_v1_instance.read_namespaced_pod_log = mock.AsyncMock(side_effect=client.exceptions.ApiException(status=400, reason="BadRequest"))
        
        with mock.patch("kubernetes_asyncio.client.ApiClient", return_value=mock_api_client_cm), \
             mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core_v1_instance):
            
            logs = await k8s_client.get_showcase_logs("gpu-inference", "gke-showcase-gpu-inference")
            
            expected_substr = "[STATUS: CONTAINER PROVISIONING] The container is currently pulling image or initializing volume mounts"
            assert expected_substr in logs
