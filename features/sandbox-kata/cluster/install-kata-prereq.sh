#!/usr/bin/env bash
# One-time Kata / MicroVM runtime prerequisite for the sandbox-kata feature.
#
# Creates a nested-virtualization node pool and installs kata-deploy (which
# registers the kata-clh RuntimeClass this feature references). Declared as this
# feature's paths.cluster_setup hook, so build_infra.sh runs it at cluster bootstrap
# (a fresh clone installs it with no manual step) — and it must therefore be IDEMPOTENT
# (safe to re-run on every bootstrap): the node pool is created only if absent, and
# kata-deploy is applied with `kubectl apply` (declarative, converges on re-run).
#
# NO HELM REQUIRED. Earlier revisions used `helm install kata-deploy`, but the
# kata-deploy manifests (DaemonSet + RBAC) are vendored under ./kata-deploy/ pinned
# to kata 3.20.0 — the last release that ships plain kustomize manifests — so this
# hook needs only `gcloud` + `kubectl`. See README.md for details.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Accept PROJECT/CLUSTER or the PROJECT_ID/CLUSTER_NAME names build_infra.sh exports.
PROJECT="${PROJECT:-${PROJECT_ID:-}}"
CLUSTER="${CLUSTER:-${CLUSTER_NAME:-}}"
: "${PROJECT:?set PROJECT (or PROJECT_ID) to your GCP project}"
: "${CLUSTER:?set CLUSTER (or CLUSTER_NAME) to your GKE cluster name}"
: "${REGION:?set REGION to your cluster region, e.g. us-central1}"
NODE_POOL="${NODE_POOL:-kata-microvm-pool}"
# Autoscaling bounds. Defaults keep the pool scale-to-zero (no cost at rest):
# the first Kata sandbox request then cold-starts a node (multi-minute). For a
# live UI demo / screenshots, pre-warm one always-on node so the first click is
# instant: MIN_NODES=1 NUM_NODES=1 bash install-kata-prereq.sh
MIN_NODES="${MIN_NODES:-0}"
MAX_NODES="${MAX_NODES:-3}"
NUM_NODES="${NUM_NODES:-0}"

if gcloud container node-pools describe "${NODE_POOL}" \
     --project "${PROJECT}" --cluster "${CLUSTER}" --region "${REGION}" >/dev/null 2>&1; then
  echo "==> [1/3] node pool '${NODE_POOL}' already exists — skipping create (idempotent)"
else
  echo "==> [1/3] Creating nested-virtualization node pool '${NODE_POOL}' (autoscale ${MIN_NODES}-${MAX_NODES}, ${NUM_NODES} initial, tainted for Kata)"
  gcloud container node-pools create "${NODE_POOL}" \
    --project "${PROJECT}" --cluster "${CLUSTER}" --region "${REGION}" \
    --machine-type n2-standard-4 \
    --image-type COS_CONTAINERD \
    --enable-nested-virtualization \
    --node-labels nested-virtualization=enabled \
    --node-taints sandbox.gke.io/kata=true:NoSchedule \
    --enable-autoscaling --min-nodes "${MIN_NODES}" --max-nodes "${MAX_NODES}" --num-nodes "${NUM_NODES}"
fi

echo "==> [2/3] Applying vendored kata-deploy (Cloud Hypervisor shim -> registers kata-clh)"
# kubectl apply is idempotent: creates if absent, converges if present. RBAC first
# so the DaemonSet's ServiceAccount exists before it starts.
kubectl apply -f "${SCRIPT_DIR}/kata-deploy/kata-rbac.yaml"
kubectl apply -f "${SCRIPT_DIR}/kata-deploy/kata-deploy.yaml"

echo "==> [3/3] Waiting for kata-deploy rollout + kata-clh RuntimeClass"
kubectl -n kube-system rollout status ds/kata-deploy --timeout=300s
# kata-deploy creates the RuntimeClass from each node once the shim is installed;
# give it a short grace window rather than assuming it is instant.
for i in $(seq 1 30); do
  if kubectl get runtimeclass kata-clh >/dev/null 2>&1; then break; fi
  echo "     waiting for kata-clh RuntimeClass to be registered ($i/30)..."
  sleep 5
done
kubectl get runtimeclass kata-clh

echo "==> Done. Deploy the sandbox-kata feature from the Hub."
