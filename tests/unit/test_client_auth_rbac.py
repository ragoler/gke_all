import os
import pytest

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

def test_frontend_features_client_auth():
    js_files = [
        os.path.join(root_dir, "features", "agent-sandbox", "frontend", "app.js"),
        os.path.join(root_dir, "features", "gpu-inference", "hub-playroom", "app.js"),
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
    # ray feature: the admin SA must be able to manage its CRDs (PodMonitoring metrics +
    # RayCluster), else the deploy 403s and aborts mid-apply (see feature.md §5).
    assert "monitoring.googleapis.com" in content
    assert "podmonitorings" in content
    assert "ray.io" in content
    assert "rayclusters" in content
