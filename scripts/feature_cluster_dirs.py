#!/usr/bin/env python3
"""Emit cluster-scoped prerequisite directories declared by feature descriptors.

Some features need resources that exist once per cluster (GPU ComputeClasses, CRD
installs, etc.) rather than once per namespace. They declare these via
``paths.cluster_dir`` in feature.yaml. build_infra.sh applies them at cluster
bootstrap. Prints one tab-separated line per declaring feature:

    <feature_name>\t<absolute_cluster_dir>
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
        cluster_dir = (data.get("paths") or {}).get("cluster_dir")
        if not cluster_dir:
            continue
        abs_dir = os.path.join(FEATURES_DIR, entry, cluster_dir)
        if os.path.isdir(abs_dir):
            print("\t".join([name, abs_dir]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
