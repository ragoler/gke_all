import os
import pytest

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

def test_frontend_features_client_auth():
    js_files = [
        os.path.join(root_dir, "showcase_admin", "frontend", "features", "agent-sandbox.js"),
        os.path.join(root_dir, "showcase_admin", "frontend", "features", "gpu-inference.js"),
        os.path.join(root_dir, "showcase_admin", "frontend", "features", "inference-gateway.js"),
    ]
    
    for js_file in js_files:
        assert os.path.exists(js_file), f"File not found: {js_file}"
        with open(js_file, "r") as f:
            content = f.read()
            
        assert "fetchWithAuth" in content, f"fetchWithAuth not found in {js_file}"
        assert "localStorage.getItem(\"admin_jwt\")" in content, f"localStorage.getItem('admin_jwt') not found in {js_file}"

def test_infra_main_app_rbac():
    yaml_file = os.path.join(root_dir, "infra", "main-app.yaml")
    assert os.path.exists(yaml_file), f"File not found: {yaml_file}"
    
    with open(yaml_file, "r") as f:
        content = f.read()
        
    assert "inference.networking.k8s.io" in content
    assert "inference.networking.x-k8s.io" in content
    assert "inferencepools" in content
    assert "inferenceobjectives" in content
