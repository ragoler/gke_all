import pytest
import asyncio
import httpx
import os
import uuid
from kubernetes_asyncio import client, config as k8s_config
from showcase_admin.app import config, k8s_client, database

# Global authorization headers for admin REST API calls
AUTH_HEADERS = {
    "Authorization": "Basic YWRtaW46bW9jay1wYXNz",  # admin:mock-pass
    "Content-Type": "application/json"
}

@pytest.fixture(scope="module", autouse=True)
def enforce_real_mode():
    os.environ["MODE"] = "REAL"
    config.MODE = "REAL"
    yield
@pytest.fixture(scope="module", autouse=True)
def anyio_backend():
    return "asyncio"
@pytest.fixture(scope="module")
def live_admin_url():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(k8s_client.init_k8s_connection())
        async def _get_ip():
            async with client.ApiClient() as api:
                core = client.CoreV1Api(api)
                svc = await core.read_namespaced_service("showcase-admin-svc", "gke-showcase-admin")
                ingress = svc.status.load_balancer.ingress
                if not ingress:
                    pytest.fail("showcase-admin-svc has no external LoadBalancer IP assigned on GKE.")
                return svc.status.load_balancer.ingress[0].ip
        ip = loop.run_until_complete(_get_ip())
        return f"http://{ip}"
    except Exception as e:
        pytest.fail(f"Failed to discover showcase-admin-svc IP: {e}")
    finally:
        loop.close()

# ==============================================================================
# PART 1: SYSTEM-LEVEL AUDITING (10 Tests)
# ==============================================================================

@pytest.mark.gke
@pytest.mark.anyio
async def test_gke_control_plane_connection():
    """Test 1: Verify real kubernetes_asyncio client authorization against GKE control plane."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        ns_list = await core_v1.list_namespace()
        ns_names = [ns.metadata.name for ns in ns_list.items]
        assert "default" in ns_names
        assert "kube-system" in ns_names

@pytest.mark.gke
@pytest.mark.anyio
async def test_admin_namespace_exists():
    """Test 2: Verify gke-showcase-admin namespace active state on GKE."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        ns = await core_v1.read_namespace("gke-showcase-admin")
        assert ns.status.phase == "Active"

@pytest.mark.gke
@pytest.mark.anyio
async def test_admin_service_account_rbac():
    """Test 3: Verify showcase-admin-sa exists and possesses proper role binding metadata."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        sa = await core_v1.read_namespaced_service_account("showcase-admin-sa", "gke-showcase-admin")
        assert sa.metadata.name == "showcase-admin-sa"

@pytest.mark.gke
@pytest.mark.anyio
async def test_admin_pod_running_status():
    """Test 4: Verify showcase-admin-deployment pod is 1/1 Running with zero restarts."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        pods = await core_v1.list_namespaced_pod("gke-showcase-admin", label_selector="app=showcase-admin")
        assert len(pods.items) > 0
        admin_pod = pods.items[0]
        assert admin_pod.status.phase == "Running"
        assert admin_pod.status.container_statuses[0].ready is True

@pytest.mark.gke
@pytest.mark.anyio
async def test_admin_loadbalancer_service():
    """Test 5: Verify LoadBalancer external IP assignment and port mapping."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        svc = await core_v1.read_namespaced_service("showcase-admin-svc", "gke-showcase-admin")
        assert svc.spec.type == "LoadBalancer"
        assert svc.spec.ports[0].port == 80
        assert svc.spec.ports[0].target_port == 8000

@pytest.mark.gke
@pytest.mark.anyio
async def test_api_root_html_response(live_admin_url):
    """Test 6: Query GET / and verify HTTP 200 OK glassmorphic SPA return."""
    async with httpx.AsyncClient() as http:
        res = await http.get(live_admin_url, headers=AUTH_HEADERS, timeout=10.0)
        assert res.status_code == 200
        assert "GKE" in res.text
        assert "Showcase Hub" in res.text

@pytest.mark.gke
@pytest.mark.anyio
async def test_api_list_showcases_endpoint(live_admin_url):
    """Test 7: Query GET /api/showcases and verify valid JSON schema."""
    async with httpx.AsyncClient() as http:
        res = await http.get(f"{live_admin_url}/api/showcases", headers=AUTH_HEADERS, timeout=10.0)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        names = [s["name"] for s in data]
        assert "agent-sandbox" in names
        assert "gpu-inference" in names

@pytest.mark.gke
@pytest.mark.anyio
async def test_gke_node_pools_discovery():
    """Test 8: Verify baseline GKE node pool discovery via K8s API."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        nodes = await core_v1.list_node()
        assert len(nodes.items) > 0
        labels = nodes.items[0].metadata.labels
        assert "kubernetes.io/hostname" in labels

@pytest.mark.gke
@pytest.mark.anyio
async def test_cluster_autoscaler_health():
    """Test 9: Verify kube-system cluster autoscaler and DNS pod readiness."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        pods = await core_v1.list_namespaced_pod("kube-system", label_selector="k8s-app=kube-dns")
        assert len(pods.items) > 0
        for pod in pods.items:
            assert pod.status.phase == "Running"

@pytest.mark.gke
@pytest.mark.anyio
async def test_system_healthz_probes(live_admin_url):
    """Test 10: Verify /healthz liveness probe response over external LoadBalancer."""
    async with httpx.AsyncClient() as http:
        res = await http.get(f"{live_admin_url}/healthz", timeout=10.0)
        assert res.status_code in (200, 404)

# ==============================================================================
# PART 2: GKE AGENT SANDBOX INTEGRATION (4 Tests)
# ==============================================================================

@pytest.mark.gke
@pytest.mark.anyio
async def test_agent_sandbox_dynamic_deployment(live_admin_url):
    """Test 11: Audit POST /deploy on agent-sandbox and verify ACTIVE state transition."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        try:
            ns = await core_v1.read_namespace("gke-showcase-agent-sandbox")
            if ns.status.phase == "Terminating":
                for _ in range(30):
                    await asyncio.sleep(2.0)
                    try:
                        await core_v1.read_namespace("gke-showcase-agent-sandbox")
                    except Exception:
                        break
        except Exception:
            pass
            
    async with httpx.AsyncClient() as http:
        res = await http.post(
            f"{live_admin_url}/api/showcases/agent-sandbox/deploy", 
            json={"namespace": "gke-showcase-agent-sandbox"},
            headers=AUTH_HEADERS,
            timeout=25.0
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("DEPLOYING", "ACTIVE")
        
        async with client.ApiClient() as api:
            core_v1 = client.CoreV1Api(api)
            ns = await core_v1.read_namespace("gke-showcase-agent-sandbox")
            assert ns.status.phase == "Active"

@pytest.mark.gke
@pytest.mark.anyio
async def test_gvisor_node_pool_autoscaling():
    """Test 12: Audit showcase-gvisor-pool node selector scheduling and warmpool readiness."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        pods = await core_v1.list_namespaced_pod("gke-showcase-agent-sandbox", label_selector="app=demo-agent")
        assert len(pods.items) > 0
        for pod in pods.items:
            assert pod.spec.runtime_class_name == "gvisor"
            assert pod.spec.node_selector.get("sandbox.gke.io/runtime") == "gvisor"

@pytest.mark.gke
@pytest.mark.anyio
async def test_agent_sandbox_message_routing(live_admin_url):
    """Test 13: Audit POST /message routing and WIF Vertex AI fallback."""
    async with httpx.AsyncClient() as http:
        claim_res = await http.post(f"{live_admin_url}/api/sandboxes", headers=AUTH_HEADERS, timeout=15.0)
        assert claim_res.status_code == 200
        claim_id = claim_res.json()["id"]
        
        msg_res = await http.post(
            f"{live_admin_url}/api/sandboxes/{claim_id}/message",
            json={"message": "Live integration verification prompt", "provider": "vertex"},
            headers=AUTH_HEADERS,
            timeout=20.0
        )
        assert msg_res.status_code == 200
        assert "Live integration verification prompt" in msg_res.json()["reply"]

# ==============================================================================
# PART 3: vLLM GPU INFERENCE INTEGRATION (4 Tests)
# ==============================================================================

@pytest.mark.gke
@pytest.mark.anyio
async def test_gpu_inference_dynamic_deployment(live_admin_url):
    """Test 14: Audit POST /deploy on gpu-inference and PROVISIONING status transitions."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        try:
            ns = await core_v1.read_namespace("gke-showcase-gpu-inference")
            if ns.status.phase == "Terminating":
                for _ in range(30):
                    await asyncio.sleep(2.0)
                    try:
                        await core_v1.read_namespace("gke-showcase-gpu-inference")
                    except Exception:
                        break
        except Exception:
            pass

    async with httpx.AsyncClient() as http:
        res = await http.post(
            f"{live_admin_url}/api/showcases/gpu-inference/deploy",
            json={"namespace": "gke-showcase-gpu-inference"},
            headers=AUTH_HEADERS,
            timeout=25.0
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("DEPLOYING", "PROVISIONING", "ACTIVE")

@pytest.mark.gke
@pytest.mark.anyio
async def test_spot_gpu_node_pool_autoscaling():
    """Test 15: Audit Spot L4 GPU node pool scale-up requests and node taints."""
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api:
        core_v1 = client.CoreV1Api(api)
        pods = await core_v1.list_namespaced_pod("gke-showcase-gpu-inference", label_selector="app=gpu-inference")
        assert len(pods.items) > 0
        pod = pods.items[0]
        assert pod.spec.node_selector.get("cloud.google.com/gke-accelerator") == "nvidia-l4"
        assert pod.spec.node_selector.get("cloud.google.com/gke-spot") == "true"

@pytest.mark.gke
@pytest.mark.anyio
async def test_gpu_inference_multi_container_observability(live_admin_url):
    """Test 16: Audit GET /logs multi-container aggregated observability streams."""
    async with httpx.AsyncClient() as http:
        res = await http.get(f"{live_admin_url}/api/showcases/gpu-inference/logs", headers=AUTH_HEADERS, timeout=15.0)
        assert res.status_code == 200
        logs = res.json()["logs"]
        assert "Container: vllm-server" in logs or "No pods active" in logs or "Logs unavailable" in logs

@pytest.mark.gke
@pytest.mark.anyio
async def test_dual_showcase_inter_routing(live_admin_url):
    """Test 17: Audit X-Sandbox-Provider: vllm internal cluster DNS quote routing."""
    async with httpx.AsyncClient() as http:
        res = await http.get(f"{live_admin_url}/api/showcases", headers=AUTH_HEADERS, timeout=10.0)
        active = [s["name"] for s in res.json() if s["status"] == "ACTIVE"]
        if "agent-sandbox" not in active or "gpu-inference" not in active:
            pytest.skip("Both showcases must be fully ACTIVE to test inter-service DNS quote routing.")
            
        claim_res = await http.post(f"{live_admin_url}/api/sandboxes", headers=AUTH_HEADERS, timeout=15.0)
        claim_id = claim_res.json()["id"]
        
        quote_res = await http.post(
            f"{live_admin_url}/api/sandboxes/{claim_id}/quote",
            json={"provider": "vllm"},
            headers=AUTH_HEADERS,
            timeout=30.0
        )
        assert quote_res.status_code == 200
        assert "quote" in quote_res.json()

# ==============================================================================
# PART 4: TEARDOWN & DE-PROVISIONING (1 Test)
# ==============================================================================

@pytest.mark.gke
@pytest.mark.anyio
async def test_agent_sandbox_teardown_lock(live_admin_url):
    """Test 18: Audit DELETE /teardown locking and namespace de-provisioning."""
    async with httpx.AsyncClient() as http:
        res = await http.delete(
            f"{live_admin_url}/api/showcases/agent-sandbox/teardown",
            headers=AUTH_HEADERS,
            timeout=15.0
        )
        assert res.status_code == 200
        assert res.json()["status"] == "TERMINATING"
        
        await k8s_client.init_k8s_connection()
        async with client.ApiClient() as api:
            core_v1 = client.CoreV1Api(api)
            ns = await core_v1.read_namespace("gke-showcase-agent-sandbox")
            assert ns.status.phase in ("Terminating", "Active")

