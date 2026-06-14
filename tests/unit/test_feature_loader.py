"""Unit tests for the manifest-driven feature loader (showcase_admin/app/features.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from showcase_admin.app import features as feature_registry


def test_descriptors_discovered_for_local_features():
    """Both committed local features expose a parsable feature.yaml descriptor."""
    descriptors = feature_registry.load_descriptors()
    assert "agent-sandbox" in descriptors
    assert "gpu-inference" in descriptors
    # Each descriptor is normalized to carry its own name.
    assert descriptors["agent-sandbox"]["name"] == "agent-sandbox"


def test_available_showcases_shape_and_ordering():
    """available_showcases() yields card metadata in deterministic (sorted) order."""
    showcases = feature_registry.available_showcases()
    names = list(showcases.keys())
    # Alphabetical scan keeps agent-sandbox ahead of gpu-inference (asserted by API tests).
    assert names.index("agent-sandbox") < names.index("gpu-inference")
    sandbox = showcases["agent-sandbox"]
    assert sandbox["title"] == "GKE Agent Sandbox"
    assert isinstance(sandbox["gke_features"], list) and sandbox["gke_features"]


def test_deployment_map_matches_manifests():
    """deployment_map() resolves the Deployment names used for readiness polling."""
    deployments = feature_registry.deployment_map()
    assert deployments["agent-sandbox"] == "sandbox-router-deployment"
    assert deployments["gpu-inference"] == "gpu-inference-deployment"


def test_url_map_and_playroom_routes_derive_from_slug():
    """Playroom URLs and route pairs are derived from paths.playroom_slug."""
    urls = feature_registry.url_map()
    assert urls["agent-sandbox"] == "/sandbox/"
    assert urls["gpu-inference"] == "/inference/"

    routes = dict(feature_registry.playroom_routes())
    assert routes["sandbox"] == "agent-sandbox"
    assert routes["inference"] == "gpu-inference"


def test_infra_dirs_defaults_and_overrides():
    """infra_dirs() returns the declared dirs, defaulting to ['infra']."""
    # Local features use the single-dir form.
    assert feature_registry.infra_dirs("agent-sandbox") == ["infra"]
    assert feature_registry.infra_dirs("gpu-inference") == ["infra"]
    # Unknown features still get the safe default.
    assert feature_registry.infra_dirs("does-not-exist") == ["infra"]


def test_template_defaults_returns_mapping():
    """template_defaults() returns a (possibly empty) string->string map per feature."""
    defaults = feature_registry.template_defaults("agent-sandbox")
    assert isinstance(defaults, dict)
    # Local features declare no extra template defaults today.
    assert defaults == {}
    # Unknown features resolve to an empty mapping rather than raising.
    assert feature_registry.template_defaults("does-not-exist") == {}


def test_aggregate_frontends_mirrors_playroom_uis(tmp_path):
    """aggregate_frontends() copies each feature's playroom UI into the served root."""
    dest = tmp_path / "features"
    feature_registry.aggregate_frontends(str(dest))
    # Each local feature with a frontend_dir lands as <dest>/<name>/index.html.
    assert (dest / "agent-sandbox" / "index.html").is_file()
    assert (dest / "agent-sandbox" / "app.js").is_file()
    assert (dest / "gpu-inference" / "index.html").is_file()
    # Re-running is idempotent (overwrites cleanly, no error).
    feature_registry.aggregate_frontends(str(dest))
    assert (dest / "gpu-inference" / "app.js").is_file()


def test_entrypoint_service_none_for_hosted_features():
    """The in-repo features use a Hub-hosted playroom, not a link-out entrypoint."""
    assert feature_registry.entrypoint_service("agent-sandbox") is None
    assert feature_registry.entrypoint_service("gpu-inference") is None


@pytest.mark.anyio
async def test_resolve_reach_out_url_for_hosted_and_linkout():
    """resolve_reach_out_url returns the Hub path for hosted features; link-out uses a URL."""
    from showcase_admin.app import k8s_client, config

    original = config.MODE
    config.MODE = "MOCK"
    try:
        # Hosted feature -> internal Hub playroom path.
        assert await k8s_client.resolve_reach_out_url("agent-sandbox", "ns") == "/sandbox/"
        # A feature with neither a playroom nor an entrypoint resolves to None.
        assert await k8s_client.resolve_reach_out_url("does-not-exist", "ns") is None
    finally:
        config.MODE = original


def test_load_routers_returns_feature_routers():
    """Each feature with a hub_router declaration yields an importable APIRouter."""
    routers = feature_registry.load_routers()
    assert "agent-sandbox" in routers
    assert "gpu-inference" in routers
    # Routers expose FastAPI's routes attribute.
    assert hasattr(routers["agent-sandbox"], "routes")
