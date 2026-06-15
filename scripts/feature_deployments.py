#!/usr/bin/env python3
"""Emit each feature's primary Deployment (for post-push rollout restarts).

build_and_push.sh uses this to roll the running Deployments after pushing new images, so
the cluster picks them up (a :latest tag is not auto-pulled). Prints one tab-separated
line per feature:

    <feature_name>\t<deployment_name>\t<default_namespace>
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
        with open(descriptor, "r") as handle:
            data = yaml.safe_load(handle) or {}
        name = data.get("name") or entry
        deployment = data.get("deployment_name") or f"{name}-deployment"
        print("\t".join([name, deployment, f"gke-showcase-{name}"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
