import os
import sys
import pytest
import importlib.util
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Resolve absolute path to features/gpu-inference/app/main.py
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
main_py_path = os.path.join(root_dir, "features", "gpu-inference", "app", "main.py")

spec = importlib.util.spec_from_file_location("gpu_inference_main", main_py_path)
gpu_inference_main = importlib.util.module_from_spec(spec)
sys.modules["gpu_inference_main"] = gpu_inference_main
spec.loader.exec_module(gpu_inference_main)

app = gpu_inference_main.app
client = TestClient(app)


def test_serve_index_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "vLLM GPU Playground" in response.text
    assert "/static/style.css" in response.text
    assert "/static/app.js" in response.text


def test_serve_static_style_css():
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "background-color" in response.text
    assert "chat-container" in response.text


def test_serve_static_app_js():
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "async function sendMessage()" in response.text
    assert "fetch(\"/chat\"" in response.text or "fetch('/chat'" in response.text


def test_post_chat_success():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello from mock GPU vLLM!"}}]
        }
        mock_post.return_value = mock_resp

        response = client.post("/chat", json={"prompt": "Test prompt"})
        assert response.status_code == 200
        assert response.json() == {"reply": "Hello from mock GPU vLLM!"}


def test_post_chat_fallback():
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("vLLM unreachable")

        response = client.post("/chat", json={"prompt": "Test prompt"})
        assert response.status_code == 200
        assert "STATUS: MODEL LOADING" in response.json()["reply"]
