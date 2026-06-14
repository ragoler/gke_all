#!/usr/bin/env python3
"""Emit container build targets declared across all feature.yaml descriptors.

Used by scripts/build_and_push.sh to build feature images without hardcoding a
per-feature function. Prints one tab-separated line per build target:

    <feature_name>\t<image>\t<context>\t<dockerfile>\t<git>

Missing optional fields (dockerfile, git) are emitted as ``-``. The script reads
descriptors directly from ``features/*/feature.yaml`` relative to the repo root and
depends only on PyYAML (present in the repo's .venv and the Admin image).
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
        for target in data.get("build") or []:
            image = target.get("image")
            if not image:
                continue
            context = target.get("context", ".")
            dockerfile = target.get("dockerfile", "-")
            git = target.get("git", "-")
            print("\t".join([name, image, context, dockerfile, git]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
