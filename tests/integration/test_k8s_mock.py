import os
import sys
import pytest
from unittest import mock

# Ensure showcase_admin in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.k8s_client import expand_template, apply_yaml_manifests, deploy_showcase, get_gateway_ip, create_sandbox_claim
from showcase_admin.app.database import Base, engine, SessionLocal, ShowcaseModel

@pytest.fixture(autouse=True, name="init_memory_db")
def fixture_init_memory_db():
    engine.dispose()
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
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
    mock_core_instance = mock.MagicMock()
    mock_ns_info = mock.MagicMock()
    mock_ns_info.status.phase = "Active"
    mock_core_instance.read_namespace = mock.AsyncMock(return_value=mock_ns_info)
    mock_core_instance.create_namespace = mock.AsyncMock()
    mock_core_instance.create_namespaced_service = mock.AsyncMock()
    mock_core_instance.create_namespaced_config_map = mock.AsyncMock()
    mock_core_instance.create_namespaced_secret = mock.AsyncMock()
    
    mock_apps_instance = mock.MagicMock()
    mock_apps_instance.create_namespaced_deployment = mock.AsyncMock()
    mock_apps_instance.read_namespaced_deployment = mock.AsyncMock(return_value=mock.MagicMock())
    
    mock_custom_instance = mock.MagicMock()
    mock_custom_instance.create_namespaced_custom_object = mock.AsyncMock()
    mock_custom_instance.get_namespaced_custom_object = mock.AsyncMock()
    
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

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_get_gateway_ip_fallback_sandbox(mock_init):
    import kubernetes_asyncio.client as k8s_client
    mock_custom = mock.MagicMock()
    mock_custom.get_namespaced_custom_object = mock.AsyncMock(side_effect=Exception("Not ready"))
    
    with mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        
        ip = await get_gateway_ip("gke-showcase-agent-sandbox-123", "agent-sandbox-gateway")
        assert ip == "sandbox-router-svc.gke-showcase-agent-sandbox-123.svc.cluster.local:8080"

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_get_gateway_ip_fallback_inference(mock_init):
    mock_custom = mock.MagicMock()
    mock_custom.get_namespaced_custom_object = mock.AsyncMock(side_effect=Exception("Not ready"))
    
    with mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        
        ip = await get_gateway_ip("gke-showcase-gpu-inference", "gpu-inference-gateway")
        assert ip == "inference-playroom-svc.gke-showcase-gpu-inference.svc.cluster.local:8080"

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_get_gateway_ip_fallback_default(mock_init):
    mock_custom = mock.MagicMock()
    mock_custom.get_namespaced_custom_object = mock.AsyncMock(side_effect=Exception("Not ready"))
    
    with mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        
        ip = await get_gateway_ip("other-namespace", "some-gateway")
        # No programmed gateway (and not a sandbox/inference namespace) -> empty, so
        # the playroom can show "provisioning…" instead of fetching a dead address.
        assert ip == ""

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_deploy_showcase_k8s_timeout(mock_init, init_memory_db):
    import asyncio
    import kubernetes_asyncio.client as k8s_client
    mock_core_instance = mock.MagicMock()
    mock_core_instance.read_namespace = mock.AsyncMock(side_effect=k8s_client.exceptions.ApiException(status=404))
    mock_core_instance.create_namespace = mock.AsyncMock(side_effect=asyncio.TimeoutError("K8s API connection timed out"))
    
    with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core_instance), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        
        db = SessionLocal()
        try:
            with pytest.raises(asyncio.TimeoutError, match="K8s API connection timed out"):
                await deploy_showcase("agent-sandbox", "timeout-ns", db_session=db)
            
            showcase = db.query(ShowcaseModel).filter_by(name="agent-sandbox").first()
            assert showcase is not None
            assert showcase.status == "ERROR"
        finally:
            db.close()

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_create_sandbox_claim_api_exceptions(mock_init):
    import showcase_admin.app.k8s_client as sak
    # Failure: the session helper (official client) raises -> wrapped error.
    with mock.patch("showcase_admin.app.k8s_client._create_sandbox_session_sync", side_effect=Exception("boom")):
        with pytest.raises(Exception, match="Failed to claim sandbox on GKE"):
            await create_sandbox_claim("test-ns", "claim-1")
    # Success: returns the client's generated claim name and registers the session.
    with mock.patch("showcase_admin.app.k8s_client._create_sandbox_session_sync",
                    return_value=mock.MagicMock(sandbox_id="agent-sandbox-warmpool-abcd")):
        res = await create_sandbox_claim("test-ns")
        assert res == {"id": "agent-sandbox-warmpool-abcd", "status": "RUNNING"}
        assert "agent-sandbox-warmpool-abcd" in sak._sandbox_sessions
    sak._sandbox_sessions.clear()

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_real_mode_k8s_client_helpers(mock_init, init_memory_db):
    import kubernetes_asyncio.client as k8s_client
    from showcase_admin.app.k8s_client import (
        list_sandbox_claims, delete_sandbox_claim, message_sandbox_claim,
        quote_sandbox_claim, query_gpu_inference_server, check_and_update_showcase_status,
        get_cluster_stats, get_showcase_logs
    )
    
    mock_custom = mock.MagicMock()
    mock_custom.list_namespaced_custom_object = mock.AsyncMock(return_value={
        "items": [{"metadata": {"name": "sb-1"}, "status": {"phase": "RUNNING"}}]
    })
    mock_custom.delete_namespaced_custom_object = mock.AsyncMock()
    
    mock_core = mock.MagicMock()
    mock_node = mock.MagicMock()
    mock_node.status.conditions = [mock.MagicMock(type="Ready", status="True")]
    mock_node.metadata.labels = {"sandbox.gke.io/runtime": "gvisor"}
    mock_core.list_node = mock.AsyncMock(return_value=mock.MagicMock(items=[mock_node]))
    mock_core.list_namespace = mock.AsyncMock(return_value=mock.MagicMock(items=[mock.MagicMock()]))
    
    mock_pod = mock.MagicMock()
    mock_pod.status.phase = "Running"
    mock_pod.spec.runtime_class_name = "gvisor"
    mock_container = mock.MagicMock()
    mock_container.resources.requests = {"nvidia.com/gpu": "1"}
    mock_pod.spec.containers = [mock_container]
    mock_core.list_pod_for_all_namespaces = mock.AsyncMock(return_value=mock.MagicMock(items=[mock_pod]))
    mock_core.read_namespaced_pod_log = mock.AsyncMock(return_value="Mock showcase pod logs output")
    
    mock_apps = mock.MagicMock()
    mock_dep = mock.MagicMock()
    mock_dep.status.ready_replicas = 1
    mock_dep.status.replicas = 1
    mock_dep.spec.replicas = 1
    mock_apps.read_namespaced_deployment = mock.AsyncMock(return_value=mock_dep)
    
    mock_http = mock.MagicMock()
    mock_http.status_code = 200
    mock_http.json.return_value = {"reply": "real mock reply", "quote": "real mock quote"}
    
    with mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom), \
         mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core), \
         mock.patch("kubernetes_asyncio.client.AppsV1Api", return_value=mock_apps), \
         mock.patch("showcase_admin.app.k8s_client.execute_http_with_retry", return_value=mock_http) as mock_req, \
         mock.patch("showcase_admin.app.k8s_client.get_gateway_ip", return_value="10.0.0.1"), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        
        import showcase_admin.app.k8s_client as sak
        # 1. List claims from the SandboxClaim CRDs (source of truth; survives a Hub restart)
        sak._sandbox_sessions.clear()
        claims = await list_sandbox_claims("test-ns")
        assert len(claims) == 1
        assert claims[0]["id"] == "sb-1"

        # 1b. No CRDs -> empty list
        mock_custom.list_namespaced_custom_object = mock.AsyncMock(return_value={"items": []})
        assert await list_sandbox_claims("test-ns") == []
        # restore the one-claim listing for the delete sub-test below
        mock_custom.list_namespaced_custom_object = mock.AsyncMock(return_value={
            "items": [{"metadata": {"name": "sb-1"}, "status": {"sandbox": {"Name": "sb-1"}}}]
        })

        # 2. Delete terminates the live handle (if any) AND deletes the SandboxClaim CRD,
        #    so a claim orphaned by a restart (not in the registry) is still removable.
        term = mock.MagicMock()
        sak._sandbox_sessions["sb-1"] = mock.MagicMock(terminate=term)
        await delete_sandbox_claim("test-ns", "sb-1")
        term.assert_called_once()
        assert "sb-1" not in sak._sandbox_sessions
        mock_custom.delete_namespaced_custom_object.assert_called()

        # 3/4. Message + quote route through the live session
        sak._sandbox_sessions["sb-1"] = object()
        with mock.patch("showcase_admin.app.k8s_client._sandbox_request_sync", return_value=mock_http):
            rep = await message_sandbox_claim("test-ns", "sb-1", "msg", "vertex", "vllm-ns")
            assert rep == "real mock reply"
            qt = await quote_sandbox_claim("test-ns", "sb-1", "vertex", "vllm-ns")
            assert qt == "real mock quote"
        sak._sandbox_sessions.clear()
        
        # 5. Query GPU
        gpu_rep = await query_gpu_inference_server("test-ns", "query")
        assert gpu_rep == "real mock reply"
        
        # 6. Cluster stats
        stats = await get_cluster_stats()
        assert stats["mode"] == "REAL"
        assert stats["nodes"]["total"] == 1
        assert stats["accelerators"]["nvidia_l4"] == 1
        assert stats["accelerators"]["gvisor"] == 1
        
        # 7. Showcase logs
        from types import SimpleNamespace
        mock_log_pod = SimpleNamespace(
            metadata=SimpleNamespace(name="pod-1"),
            status=SimpleNamespace(phase="Running"),
            spec=SimpleNamespace(containers=[SimpleNamespace(name="container-1")])
        )
        mock_core.list_namespaced_pod = mock.AsyncMock(return_value=mock.MagicMock(items=[mock_log_pod]))
        logs = await get_showcase_logs("agent-sandbox", "test-ns")
        assert "Mock showcase pod logs output" in logs
        
        # 8. Check and update status
        db = SessionLocal()
        try:
            showcase = ShowcaseModel(name="agent-sandbox", namespace="test-ns", status="DEPLOYING")
            db.add(showcase)
            db.commit()
            
            await check_and_update_showcase_status("agent-sandbox", "test-ns")
            db.refresh(showcase)
            assert showcase.status == "ACTIVE"

            # 8b. Spot reclaim: a Ready backend loses its replicas -> REPROVISIONING
            mock_dep.status.ready_replicas = 0
            await check_and_update_showcase_status("agent-sandbox", "test-ns")
            db.refresh(showcase)
            assert showcase.status == "REPROVISIONING"

            # 8c. Self-heal: replicas back (model reloaded) -> ACTIVE
            mock_dep.status.ready_replicas = 1
            await check_and_update_showcase_status("agent-sandbox", "test-ns")
            db.refresh(showcase)
            assert showcase.status == "ACTIVE"
        finally:
            db.close()

@pytest.mark.anyio
async def test_k8s_client_remaining_lines():
    import kubernetes_asyncio.client as k8s_client
    from showcase_admin.app.k8s_client import (
        init_k8s_connection, run_gcloud_cmd, get_gateway_ip, apply_yaml_manifests, teardown_showcase
    )
    from showcase_admin.app.database import SessionLocal, ShowcaseModel
    
    # 1. init_k8s_connection
    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("kubernetes_asyncio.config.load_incluster_config", side_effect=Exception("not incluster")), \
         mock.patch("kubernetes_asyncio.config.load_kube_config", new_callable=mock.AsyncMock) as mock_kube:
        await init_k8s_connection()
        mock_kube.assert_called_once()
        
    # 2. run_gcloud_cmd
    mock_proc = mock.AsyncMock()
    mock_proc.communicate = mock.AsyncMock(return_value=(b"success output", b""))
    mock_proc.returncode = 0
    with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        assert await run_gcloud_cmd(["info"]) == "success output"
        
    mock_proc_err = mock.AsyncMock()
    mock_proc_err.communicate = mock.AsyncMock(return_value=(b"", b"error msg"))
    mock_proc_err.returncode = 1
    with mock.patch("asyncio.create_subprocess_exec", return_value=mock_proc_err):
        with pytest.raises(Exception, match="gcloud command failed: error msg"):
            await run_gcloud_cmd(["fail"])
            
    # 3. get_gateway_ip success — only returns the address once the gateway is
    #    Programmed (has both an address AND a Programmed=True condition).
    mock_custom_gw = mock.MagicMock()
    mock_custom_gw.get_namespaced_custom_object = mock.AsyncMock(return_value={
        "status": {
            "addresses": [{"value": "34.123.45.67"}],
            "conditions": [{"type": "Programmed", "status": "True"}],
        }
    })
    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("showcase_admin.app.k8s_client.init_k8s_connection"), \
         mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom_gw), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        assert await get_gateway_ip("test-ns", "gw") == "34.123.45.67"

    # 3b. address present but NOT yet Programmed -> empty (still provisioning).
    mock_custom_gw_np = mock.MagicMock()
    mock_custom_gw_np.get_namespaced_custom_object = mock.AsyncMock(return_value={
        "status": {"addresses": [{"value": "34.123.45.67"}]}
    })
    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("showcase_admin.app.k8s_client.init_k8s_connection"), \
         mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom_gw_np), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        assert await get_gateway_ip("test-ns", "gw") == ""
        
    # 4. apply_yaml_manifests
    yaml_content = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
---
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
---
apiVersion: extensions.agents.x-k8s.io/v1alpha1
kind: SandboxClaim
metadata:
  name: my-claim
"""
    mock_core = mock.MagicMock()
    mock_core.create_namespaced_config_map = mock.AsyncMock()
    mock_core.create_namespaced_secret = mock.AsyncMock(side_effect=k8s_client.exceptions.ApiException(status=409))
    mock_custom = mock.MagicMock()
    mock_custom.create_namespaced_custom_object = mock.AsyncMock()
    
    with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core), \
         mock.patch("kubernetes_asyncio.client.AppsV1Api"), \
         mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        await apply_yaml_manifests("test-ns", yaml_content)
        mock_core.create_namespaced_config_map.assert_called_once()
        mock_core.create_namespaced_secret.assert_called_once()
        mock_custom.create_namespaced_custom_object.assert_called_once()
        
    # 5. teardown_showcase in real mode
    mock_core_del = mock.MagicMock()
    mock_core_del.delete_namespace = mock.AsyncMock()
    mock_core_del.read_namespace = mock.AsyncMock(side_effect=k8s_client.exceptions.ApiException(status=404))
    
    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("showcase_admin.app.k8s_client.init_k8s_connection"), \
         mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core_del), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        db = SessionLocal()
        try:
            sh = ShowcaseModel(name="agent-sandbox", namespace="real-teardown-ns", status="ACTIVE")
            db.add(sh)
            db.commit()
            
            await teardown_showcase("agent-sandbox", "real-teardown-ns", db_session=db)
            assert sh.status == "DORMANT"
        finally:
            db.close()

@pytest.mark.anyio
async def test_k8s_client_thorough_coverage():
    import kubernetes_asyncio.client as k8s_client
    import httpx
    from types import SimpleNamespace
    from showcase_admin.app import config
    from showcase_admin.app.k8s_client import (
        get_showcase_logs, execute_http_with_retry, list_sandbox_claims, create_sandbox_claim,
        delete_sandbox_claim, message_sandbox_claim, quote_sandbox_claim, query_gpu_inference_server,
        check_and_update_showcase_status, get_cluster_stats
    )
    
    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("showcase_admin.app.k8s_client.init_k8s_connection"), \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
         
        # 1. get_showcase_logs branches
        mock_core = mock.MagicMock()
        mock_core.list_namespaced_pod = mock.AsyncMock(return_value=mock.MagicMock(items=[]))
        with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core):
            assert await get_showcase_logs("app", "ns") == "No pods active in namespace 'ns'."
            
        mock_pod_err = SimpleNamespace(metadata=SimpleNamespace(name="p1"), status=SimpleNamespace(phase="Running"), spec=SimpleNamespace(containers=[SimpleNamespace(name="c1")]))
        mock_core.list_namespaced_pod = mock.AsyncMock(return_value=mock.MagicMock(items=[mock_pod_err]))
        mock_core.read_namespaced_pod_log = mock.AsyncMock(side_effect=Exception("log error"))
        with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core):
            logs = await get_showcase_logs("app", "ns")
            assert "Logs unavailable: log error" in logs
            
        mock_core.list_namespaced_pod = mock.AsyncMock(side_effect=Exception("list error"))
        with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core):
            assert await get_showcase_logs("app", "ns") == "Failed to retrieve live GKE logs: list error"
            
        # 2. execute_http_with_retry PUT and RequestError
        mock_resp = mock.MagicMock(status_code=200)
        with mock.patch("httpx.AsyncClient.request", new_callable=mock.AsyncMock, return_value=mock_resp):
            res = await execute_http_with_retry("PUT", "http://url")
            assert res.status_code == 200
            
        with mock.patch("httpx.AsyncClient.get", new_callable=mock.AsyncMock, side_effect=httpx.RequestError("conn err")):
            with pytest.raises(httpx.RequestError):
                await execute_http_with_retry("GET", "http://url", max_retries=1)
                
        # 3. Sandbox Claims: delete is best-effort on terminate(), then deletes the CRD.
        import kubernetes_asyncio.client as kclient
        import showcase_admin.app.k8s_client as sak
        # A failing terminate() is swallowed; an error deleting the SandboxClaim CRD surfaces.
        mock_custom_d = mock.MagicMock()
        mock_custom_d.list_namespaced_custom_object = mock.AsyncMock(return_value={
            "items": [{"metadata": {"name": "c1"}, "status": {"sandbox": {"Name": "c1"}}}]
        })
        mock_custom_d.delete_namespaced_custom_object = mock.AsyncMock(
            side_effect=kclient.exceptions.ApiException(status=500))
        bad = mock.MagicMock()
        bad.terminate.side_effect = Exception("del error")
        sak._sandbox_sessions["c1"] = bad
        with mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom_d):
            with pytest.raises(Exception, match="Failed to delete claim on GKE"):
                await delete_sandbox_claim("ns", "c1")
        # create success returns the resolved sandbox id
        with mock.patch("showcase_admin.app.k8s_client._create_sandbox_session_sync",
                        return_value=mock.MagicMock(sandbox_id="c1")):
            res = await create_sandbox_claim("ns")
            assert res == {"id": "c1", "status": "RUNNING"}
        with mock.patch("showcase_admin.app.k8s_client._create_sandbox_session_sync", side_effect=Exception("boom")):
            with pytest.raises(Exception, match="Failed to claim sandbox on GKE"):
                await create_sandbox_claim("ns")
        sak._sandbox_sessions.clear()
                
        # 4. REST APIs with SANDBOX_ROUTER_URL and 500 errors
        mock_500 = mock.MagicMock(status_code=500, text="Internal Error")
        # message/quote re-attach from the SandboxClaim CRD when the in-memory session is
        # gone (e.g. after a Hub restart). With no matching claim the rebind yields None and
        # we return the friendly error.
        mock_custom_nf = mock.MagicMock()
        mock_custom_nf.list_namespaced_custom_object = mock.AsyncMock(return_value={"items": []})
        with mock.patch("showcase_admin.app.config.SANDBOX_ROUTER_URL", "http://router-svc/"), \
             mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom_nf), \
             mock.patch("showcase_admin.app.k8s_client.execute_http_with_retry", new_callable=mock.AsyncMock, return_value=mock_500):
            assert "Failed to communicate with GKE sandbox" in await message_sandbox_claim("ns", "c1", "msg", "p", "vllm")
            assert "Failed to fetch quotes from GKE sandbox" in await quote_sandbox_claim("ns", "c1", "p", "vllm")
            # A backend error now maps to a friendly provisioning/re-provisioning message.
            assert "temporarily unavailable" in await query_gpu_inference_server("ns", "prompt")

                    
        # 5. check_and_update_showcase_status mock return & exception
        with mock.patch("showcase_admin.app.config.MODE", "MOCK"):
            assert await check_and_update_showcase_status("app", "ns") is None
            
        mock_apps = mock.MagicMock()
        mock_apps.read_namespaced_deployment = mock.AsyncMock(side_effect=Exception("dep error"))
        with mock.patch("kubernetes_asyncio.client.AppsV1Api", return_value=mock_apps):
            assert await check_and_update_showcase_status("app", "ns") is None
            
        # 6. get_cluster_stats comprehensive branches
        mock_node = SimpleNamespace(status=SimpleNamespace(conditions=[]), metadata=SimpleNamespace(labels={"sandbox.gke.io/runtime": "gvisor"}))
        mock_pod_pend = SimpleNamespace(status=SimpleNamespace(phase="Pending"), spec=SimpleNamespace(runtime_class_name="gvisor", containers=[]))
        mock_pod_fail = SimpleNamespace(status=SimpleNamespace(phase="Failed"), spec=SimpleNamespace(runtime_class_name="standard", containers=[
            SimpleNamespace(resources=SimpleNamespace(requests={"nvidia.com/gpu": "invalid_int"}))
        ]))
        mock_core.list_node = mock.AsyncMock(return_value=mock.MagicMock(items=[mock_node]))
        mock_core.list_namespace = mock.AsyncMock(return_value=mock.MagicMock(items=[1, 2]))
        mock_core.list_pod_for_all_namespaces = mock.AsyncMock(return_value=mock.MagicMock(items=[mock_pod_pend, mock_pod_fail]))
        
        with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core):
            stats = await get_cluster_stats()
            assert stats["mode"] == "REAL"
            assert stats["pods"]["pending"] == 1
            assert stats["pods"]["failed"] == 1
            assert stats["accelerators"]["nvidia_l4"] == 1 # fallback +1 on ValueError
            
        mock_core.list_node = mock.AsyncMock(side_effect=Exception("cluster error"))
        with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core):
            stats = await get_cluster_stats()
            assert stats["error"] == "cluster error"


@pytest.mark.anyio
async def test_sandbox_rebind_after_hub_restart():
    """A still-running claim is re-attached from its SandboxClaim CRD when the in-memory
    session was lost (admin pod restart) — instead of failing with 'session not found'."""
    import showcase_admin.app.k8s_client as sak
    sak._sandbox_sessions.clear()

    fake_resp = mock.MagicMock(status_code=200)
    fake_resp.json.return_value = {"reply": "[bound-id] hi"}
    fake_sandbox = mock.MagicMock()
    fake_sandbox.connector.send_request.return_value = fake_resp
    fake_client = mock.MagicMock()
    fake_client.get_sandbox.return_value = fake_sandbox

    # claim_id carried by the Hub is the bound sandbox id; the CRD maps it to the claim name.
    mock_custom = mock.MagicMock()
    mock_custom.list_namespaced_custom_object = mock.AsyncMock(return_value={
        "items": [{"metadata": {"name": "sandbox-claim-xyz"},
                   "status": {"sandbox": {"Name": "bound-id"}}}]
    })

    with mock.patch("showcase_admin.app.config.MODE", "REAL"), \
         mock.patch("showcase_admin.app.k8s_client.init_k8s_connection"), \
         mock.patch("kubernetes_asyncio.client.ApiClient"), \
         mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom), \
         mock.patch("showcase_admin.app.k8s_client._build_sandbox_client", return_value=fake_client), \
         mock.patch("showcase_admin.app.k8s_client._resolve_vllm_endpoint",
                    new_callable=mock.AsyncMock, return_value="http://vllm/v1"):
        reply = await sak.message_sandbox_claim("ns", "bound-id", "hi", "vertex", "vllm-ns")

    assert reply == "[bound-id] hi"
    # rebound via the resolved CLAIM NAME (not the bound id) and cached for reuse.
    fake_client.get_sandbox.assert_called_once_with("sandbox-claim-xyz", "ns")
    assert "bound-id" in sak._sandbox_sessions
    sak._sandbox_sessions.clear()
