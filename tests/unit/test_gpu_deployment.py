import os
import yaml
import pytest

def test_vllm_deployment_architecture():
    """Verify GPU deployment YAML correctly contains the us-docker image and /dev/shm volume mount."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    deployment_path = os.path.join(root_dir, "features", "gpu-inference", "infra", "vllm-deployment.yaml")
    
    assert os.path.exists(deployment_path), f"Deployment file not found at {deployment_path}"
    
    with open(deployment_path, "r") as f:
        content = f.read()
        
    doc = yaml.safe_load(content)
    
    assert doc["kind"] == "Deployment"
    spec = doc["spec"]["template"]["spec"]
    
    # Check containers
    containers = spec["containers"]
    vllm_server = next((c for c in containers if c["name"] == "vllm-server"), None)
    assert vllm_server is not None, "vllm-server container not found"
    
    # Verify container image
    expected_image = "us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:gemma"
    assert vllm_server["image"] == expected_image, f"Expected image {expected_image}, got {vllm_server[image]}"
    
    # Verify MODEL_ID environment variable
    env = vllm_server.get("env", [])
    model_id_var = next((e for e in env if e["name"] == "MODEL_ID"), None)
    assert model_id_var is not None, "MODEL_ID environment variable not found"
    assert model_id_var["value"] == "google/gemma-2b-it", f"Expected MODEL_ID value google/gemma-2b-it, got {model_id_var[value]}"
    
    # Verify volume mounts
    volume_mounts = vllm_server.get("volumeMounts", [])
    shm_mount = next((vm for vm in volume_mounts if vm["mountPath"] == "/dev/shm"), None)
    assert shm_mount is not None, "/dev/shm volume mount not found"
    assert shm_mount["name"] == "dshm", f"Expected volume name dshm for /dev/shm, got {shm_mount[name]}"
    
    # Verify pod volumes
    volumes = spec.get("volumes", [])
    dshm_volume = next((v for v in volumes if v["name"] == "dshm"), None)
    assert dshm_volume is not None, "dshm volume not found"
    assert "emptyDir" in dshm_volume, "dshm volume must be emptyDir"
    assert dshm_volume["emptyDir"].get("medium") == "Memory", "dshm emptyDir medium must be Memory"
