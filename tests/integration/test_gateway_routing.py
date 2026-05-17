import pytest
from showcase_admin.app import k8s_client, config

@pytest.mark.anyio
async def test_mock_gateway_routing():
    """Verify gateway IP extraction fallback under mock offline mode."""
    original_mode = config.MODE
    config.MODE = "MOCK"
    try:
        ip_sandbox = await k8s_client.get_gateway_ip("gke-showcase-agent-sandbox", "agent-sandbox-gateway")
        assert "sandbox-router-svc" in ip_sandbox or "127.0.0.1" in ip_sandbox, "Mock mode must return local internal DNS or loopback"
        
        ip_gpu = await k8s_client.get_gateway_ip("gke-showcase-gpu-inference", "gpu-inference-gateway")
        assert "inference-playroom-svc" in ip_gpu or "127.0.0.1" in ip_gpu, "Mock mode must return local internal DNS or loopback"
    finally:
        config.MODE = original_mode
