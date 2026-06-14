#!/usr/bin/env python3
"""Emit cluster-scoped kustomize refs declared by feature descriptors.

Some features need a CRD bundle (or other cluster-scoped resources) installed once per
cluster via ``kubectl apply -k <ref>`` — e.g. the gateway-api-inference-extension CRDs.
Features declare these as a top-level ``cluster_kustomize`` list in feature.yaml.
build_infra.sh applies them at bootstrap. Prints one tab-separated line per ref:

    <feature_name>\t<kustomize_ref>
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
        for ref in data.get("cluster_kustomize") or []:
            if ref:
                print("\t".join([name, str(ref)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
