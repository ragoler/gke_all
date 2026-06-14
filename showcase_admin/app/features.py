"""Manifest-driven feature discovery for the GKE Feature Showcase Hub.

Each showcase feature ships a declarative ``feature.yaml`` descriptor in its own
directory under ``features/<name>/`` (see the repo-root ``feature.md`` contract).
This module scans those descriptors once at import time and derives every map the
Hub previously hardcoded (available showcases, deployment names, playroom URLs),
so adding or removing a feature never requires editing Hub core code.

Both *local* features (directories committed to this repo) and *external* features
(git submodules mounted at the same path) are discovered identically — the loader
only cares that a ``feature.yaml`` exists.
"""

import importlib.util
import logging
import os
import shutil
import sys
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Repo-root ``features/`` directory, resolved the same way as k8s_client does for
# feature infra manifests (showcase_admin/app/features.py -> repo root -> features).
FEATURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "features",
)


def load_descriptors() -> dict[str, dict[str, Any]]:
    """Scan ``features/*/feature.yaml`` and return descriptors keyed by feature name.

    Directories are scanned in sorted order so the resulting dict (and therefore the
    dashboard ordering) is deterministic. A feature directory without a parsable
    ``feature.yaml`` is skipped with a logged warning rather than aborting discovery.

    Returns:
        Mapping of feature name to its parsed descriptor dict. Each descriptor is
        guaranteed to carry a ``name`` key (defaulting to the directory name).
    """
    descriptors: dict[str, dict[str, Any]] = {}
    if not os.path.isdir(FEATURES_DIR):
        logger.warning("Features directory not found at %s; no features loaded.", FEATURES_DIR)
        return descriptors

    for entry in sorted(os.listdir(FEATURES_DIR)):
        descriptor_path = os.path.join(FEATURES_DIR, entry, "feature.yaml")
        if not os.path.isfile(descriptor_path):
            continue
        try:
            with open(descriptor_path, "r") as handle:
                data = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.error("Failed to load feature descriptor %s: %s", descriptor_path, exc, exc_info=True)
            continue
        if not isinstance(data, dict):
            logger.warning("Feature descriptor %s is not a mapping; skipping.", descriptor_path)
            continue
        name = data.get("name") or entry
        data["name"] = name
        descriptors[name] = data

    return descriptors


# Descriptors are loaded once per process; the feature set is static at runtime.
FEATURES: dict[str, dict[str, Any]] = load_descriptors()


def available_showcases() -> dict[str, dict[str, Any]]:
    """Return the dashboard metadata map (name -> card fields) for all features."""
    return {
        name: {
            "name": name,
            "title": desc.get("title", name),
            "description": desc.get("description", ""),
            "gke_features": desc.get("gke_features", []),
        }
        for name, desc in FEATURES.items()
    }


def deployment_map() -> dict[str, str]:
    """Return name -> primary Deployment name (used for readiness polling)."""
    return {
        name: desc.get("deployment_name", f"{name}-deployment")
        for name, desc in FEATURES.items()
    }


def url_map() -> dict[str, str]:
    """Return name -> playroom URL path (e.g. ``/sandbox/``) for features with a UI."""
    out: dict[str, str] = {}
    for name, desc in FEATURES.items():
        slug = (desc.get("paths") or {}).get("playroom_slug")
        if slug:
            out[name] = f"/{slug}/"
    return out


def playroom_routes() -> list[tuple[str, str]]:
    """Return ``(slug, feature_name)`` pairs for features exposing a playroom UI."""
    routes: list[tuple[str, str]] = []
    for name, desc in FEATURES.items():
        slug = (desc.get("paths") or {}).get("playroom_slug")
        if slug:
            routes.append((slug, name))
    return routes


def aggregate_frontends(dest_features_dir: str) -> None:
    """Copy each feature's Hub-playroom UI into the Admin Hub's served static root.

    Every feature owns its playroom UI under ``features/<name>/<frontend_dir>/`` (the
    source of truth). The Admin Hub serves playrooms from ``<frontend>/features/<name>/``,
    so this mirrors each feature's UI there. Running it at app startup keeps local dev,
    tests, and the container image consistent without committing duplicated copies, and
    means a submodule feature's UI is served with no manual step. A feature without a
    ``frontend_dir`` (or whose dir is missing) is skipped.

    Args:
        dest_features_dir: Target ``<frontend>/features`` directory in the Admin Hub.
    """
    for name, desc in FEATURES.items():
        frontend_dir = (desc.get("paths") or {}).get("frontend_dir")
        if not frontend_dir:
            continue
        src = os.path.join(FEATURES_DIR, name, frontend_dir)
        if not os.path.isdir(src):
            logger.warning("Feature '%s' declares frontend_dir '%s' but %s is missing.", name, frontend_dir, src)
            continue
        dest = os.path.join(dest_features_dir, name)
        try:
            if os.path.isdir(dest):
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        except OSError as exc:
            logger.error("Failed to aggregate frontend for feature '%s': %s", name, exc, exc_info=True)


def template_defaults(name: str) -> dict[str, str]:
    """Return a feature's declared manifest template defaults (``template_defaults``).

    External features often template their manifests on variables the Hub doesn't supply
    by default (e.g. ``GATEWAY_NAME``, ``REPLICAS``, ``MODEL_NAME``). A feature declares
    those values in feature.yaml so its manifests expand correctly when deployed through
    the Hub. Hub-provided standard variables (NAMESPACE, PROJECT_NAME, …) take precedence
    over these defaults at deploy time.

    Args:
        name: The feature's registered name.

    Returns:
        Mapping of variable name to default string value (empty if none declared).
    """
    desc = FEATURES.get(name) or {}
    defaults = desc.get("template_defaults") or {}
    return {str(k): str(v) for k, v in defaults.items()}


def load_routers() -> dict[str, Any]:
    """Import each feature's own data-plane router (its independent "proxy").

    A feature declares ``hub_router: "<module>:<attr>"`` in feature.yaml, pointing at a
    Python file in its directory exposing a FastAPI ``APIRouter``. The Hub mounts each
    returned router under ``/api/features/<name>`` so the feature's API is fully
    self-contained and isolated from other features. A feature with no ``hub_router`` is
    simply skipped; an import error is logged and skipped rather than aborting the Hub.

    Returns:
        Mapping of feature name to its FastAPI APIRouter instance.
    """
    routers: dict[str, Any] = {}
    for name, desc in FEATURES.items():
        spec_str = desc.get("hub_router")
        if not spec_str:
            continue
        module_file, _, attr = spec_str.partition(":")
        attr = attr or "router"
        module_path = os.path.join(FEATURES_DIR, name, f"{module_file}.py")
        if not os.path.isfile(module_path):
            logger.warning("Feature '%s' declares hub_router '%s' but %s is missing.", name, spec_str, module_path)
            continue
        try:
            mod_name = f"_feature_router_{name.replace('-', '_')}_{module_file}"
            spec = importlib.util.spec_from_file_location(mod_name, module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            routers[name] = getattr(module, attr)
        except Exception as exc:  # noqa: BLE001 — one bad feature must not break the Hub
            logger.error("Failed to load hub_router for feature '%s': %s", name, exc, exc_info=True)
            continue
    return routers
