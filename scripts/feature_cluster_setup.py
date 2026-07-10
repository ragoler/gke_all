#!/usr/bin/env python3
"""Emit per-feature cluster BOOTSTRAP HOOK scripts declared by feature descriptors.

Some features need cluster-scoped prerequisites that are *imperative* and cannot be
expressed as plain manifests applied via ``paths.cluster_dir`` — e.g. a
nested-virtualization GKE node pool (``gcloud``), a ``helm`` install, or ``ko``-built
operator images. Those features declare a setup script via ``paths.cluster_setup`` in
feature.yaml; ``build_infra.sh`` runs each one at cluster bootstrap (non-fatal), so a
fresh clone + ``build_infra.sh`` installs everything without the operator needing to
know which manual scripts to run.

Prints one tab-separated line per declaring feature:

    <feature_name>\t<absolute_setup_script>

The script MUST be idempotent (safe to re-run on every bootstrap) — see feature.md §5b.
"""

import os
import sys

import yaml

FEATURES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "features")


def main() -> int:
    if not os.path.isdir(FEATURES_DIR):
        return 0
    for entry in sorted(os.listdir(FEATURES_DIR)):
        descriptor = os.path.join(FEATURES_DIR, entry, "feature.yaml")
        if not os.path.isfile(descriptor):
            continue
        try:
            with open(descriptor, "r") as handle:
                data = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("name") or entry
        setup = (data.get("paths") or {}).get("cluster_setup")
        if not setup:
            continue
        abs_script = os.path.join(FEATURES_DIR, entry, setup)
        if os.path.isfile(abs_script):
            print("\t".join([name, abs_script]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
