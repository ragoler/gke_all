import os
import pytest

def test_modular_directory_structure():
    """Verify Approach B modularity: features must contain frontend and infra assets."""
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    features_dir = os.path.join(root_dir, 'features')
    
    assert os.path.exists(features_dir), "Features directory must exist"
    
    # Check Agent Sandbox modularity
    sandbox_dir = os.path.join(features_dir, 'agent-sandbox')
    assert os.path.exists(os.path.join(sandbox_dir, 'infra')), "Agent Sandbox must contain infra manifests"
    assert os.path.exists(os.path.join(sandbox_dir, 'infra', 'gateway.yaml')), "Agent Sandbox must contain standalone gateway"
    
    # Check GPU Inference modularity
    gpu_dir = os.path.join(features_dir, 'gpu-inference')
    assert os.path.exists(os.path.join(gpu_dir, 'infra')), "GPU Inference must contain infra manifests"
    assert os.path.exists(os.path.join(gpu_dir, 'infra', 'gateway.yaml')), "GPU Inference must contain standalone gateway"
