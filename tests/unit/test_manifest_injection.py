import os
import sys
import pytest
from unittest import mock

# Ensure showcase-admin is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from showcase_admin.app.k8s_client import expand_template, deploy_showcase
from showcase_admin.app.database import Base, engine, SessionLocal, ShowcaseModel

@pytest.fixture(autouse=True, name="init_memory_db")
def fixture_init_memory_db():
    engine.dispose()
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    Base.metadata.drop_all(bind=engine)

def test_dynamic_variable_replacement():
    raw_content = (
        "env:\n"
        "- name: GOOGLE_GENAI_USE_VERTEXAI\n"
        "  value: \"${GOOGLE_GENAI_USE_VERTEXAI}\"\n"
        "- name: OPENAI_API_BASE\n"
        "  value: \"${OPENAI_API_BASE}\"\n"
    )
    
    # 1. Test Vertex AI settings
    vars_vertex = {
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        "OPENAI_API_BASE": "http://vllm-service.ns.svc.cluster.local:8000/v1"
    }
    res_vertex = expand_template(raw_content, vars_vertex)
    assert 'value: "TRUE"' in res_vertex
    assert 'value: "http://vllm-service.ns.svc.cluster.local:8000/v1"' in res_vertex
    
    # 2. Test Custom Endpoint settings
    vars_custom = {
        "GOOGLE_GENAI_USE_VERTEXAI": "FALSE",
        "OPENAI_API_BASE": "https://api.custom-llm.ai/v1"
    }
    res_custom = expand_template(raw_content, vars_custom)
    assert 'value: "FALSE"' in res_custom
    assert 'value: "https://api.custom-llm.ai/v1"' in res_custom

@pytest.mark.anyio
@mock.patch("showcase_admin.app.config.MODE", "REAL")
@mock.patch("showcase_admin.app.k8s_client.init_k8s_connection")
async def test_deploy_showcase_manifest_injection(mock_init, init_memory_db):
    # Mock CoreV1Api and AppsV1Api and CustomObjectsApi
    mock_core = mock.AsyncMock()
    mock_apps = mock.AsyncMock()
    mock_custom = mock.AsyncMock()
    
    with mock.patch("kubernetes_asyncio.client.CoreV1Api", return_value=mock_core), \
         mock.patch("kubernetes_asyncio.client.AppsV1Api", return_value=mock_apps), \
         mock.patch("kubernetes_asyncio.client.CustomObjectsApi", return_value=mock_custom), \
         mock.patch("showcase_admin.app.k8s_client.run_gcloud_cmd", new_callable=mock.AsyncMock) as mock_gcloud, \
         mock.patch("showcase_admin.app.k8s_client.apply_yaml_manifests", new_callable=mock.AsyncMock) as mock_apply, \
         mock.patch("kubernetes_asyncio.client.ApiClient"):
        
        mock_gcloud.return_value = "success"
        db = SessionLocal()
        try:
            # 1. Test Vertex AI injection
            await deploy_showcase(
                name="agent-sandbox",
                namespace="test-vertex-ns",
                llm_provider="vertex",
                db_session=db
            )
            
            # Verify what was passed to apply_yaml_manifests
            applied_manifests = [call.args[1] for call in mock_apply.call_args_list]
            combined_yaml = "\n".join(applied_manifests)
            assert 'name: GOOGLE_GENAI_USE_VERTEXAI\n          value: "TRUE"' in combined_yaml
            
            mock_apply.reset_mock()
            
            # 2. Test Custom vLLM endpoint injection
            await deploy_showcase(
                name="agent-sandbox",
                namespace="test-custom-ns",
                llm_provider="custom",
                llm_service_endpoint="https://custom.vllm.gw/v1",
                db_session=db
            )
            applied_manifests = [call.args[1] for call in mock_apply.call_args_list]
            combined_yaml = "\n".join(applied_manifests)
            assert 'name: GOOGLE_GENAI_USE_VERTEXAI\n          value: "FALSE"' in combined_yaml
            assert 'name: OPENAI_API_BASE\n          value: "https://custom.vllm.gw/v1"' in combined_yaml

        finally:
            db.close()
