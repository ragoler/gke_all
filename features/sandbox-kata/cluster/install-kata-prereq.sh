#!/usr/bin/env bash
# One-time Kata / MicroVM runtime prerequisite for the sandbox-kata feature.
#
# Creates a nested-virtualization node pool and installs kata-deploy (which
# registers the kata-clh RuntimeClass this feature references). Run once per
# cluster BEFORE deploying the feature. Idempotent-ish: re-running the node-pool
# create or helm install on an existing resource fails loudly rather than
# double-applying — safe to inspect and re-run the individual step you need.
#
# See README.md in this directory for the step-by-step explanation.
set -euo pipefail

: "${PROJECT:?set PROJECT to your GCP project}"
: "${CLUSTER:?set CLUSTER to your GKE cluster name}"
: "${REGION:?set REGION to your cluster region, e.g. us-central1}"
NODE_POOL="${NODE_POOL:-kata-microvm-pool}"
KATA_DEPLOY_VERSION="${KATA_DEPLOY_VERSION:-3.32.0}"
# Autoscaling bounds. Defaults keep the pool scale-to-zero (no cost at rest):
# the first Kata sandbox request then cold-starts a node (multi-minute). For a
# live UI demo / screenshots, pre-warm one always-on node so the first click is
# instant: MIN_NODES=1 NUM_NODES=1 bash install-kata-prereq.sh
MIN_NODES="${MIN_NODES:-0}"
MAX_NODES="${MAX_NODES:-3}"
NUM_NODES="${NUM_NODES:-0}"

echo "==> [1/3] Creating nested-virtualization node pool '${NODE_POOL}' (autoscale ${MIN_NODES}-${MAX_NODES}, ${NUM_NODES} initial, tainted for Kata)"
gcloud container node-pools create "${NODE_POOL}" \
  --project "${PROJECT}" --cluster "${CLUSTER}" --region "${REGION}" \
  --machine-type n2-standard-4 \
  --image-type COS_CONTAINERD \
  --enable-nested-virtualization \
  --node-labels nested-virtualization=enabled \
  --node-taints sandbox.gke.io/kata=true:NoSchedule \
  --enable-autoscaling --min-nodes "${MIN_NODES}" --max-nodes "${MAX_NODES}" --num-nodes "${NUM_NODES}"

echo "==> [2/3] Installing kata-deploy ${KATA_DEPLOY_VERSION} (Cloud Hypervisor shim -> registers kata-clh)"
helm install kata-deploy \
  oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy \
  --version "${KATA_DEPLOY_VERSION}" \
  --namespace kube-system \
  --set env.shims="clh"

echo "==> [3/3] Waiting for kata-deploy rollout + kata-clh RuntimeClass"
kubectl -n kube-system rollout status ds/kata-deploy
kubectl get runtimeclass kata-clh

echo "==> Done. Deploy the sandbox-kata feature from the Hub."
