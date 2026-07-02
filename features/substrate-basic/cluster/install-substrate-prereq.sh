#!/usr/bin/env bash
# One-time agent-substrate operator prerequisite for the substrate-basic feature.
#
# Installs the CORE reconcile control plane only — the ate-controller Deployment,
# the atelet DaemonSet, the ate.dev CRDs, and the default gVisor SandboxConfig —
# and builds+pushes the ateom-gvisor worker image the WorkerPool references. It
# DELIBERATELY does NOT install the alpha agent-identity data plane (ate-api-server,
# atenet, valkey, pod-certificate-controller), so it needs no alpha APIs and runs
# on a plain GKE Standard cluster. See README.md in this directory for the
# step-by-step explanation and the scope rationale.
#
# Run once per cluster BEFORE deploying the substrate-basic feature. The operator
# images are built from upstream source with `ko` — this is why the install is a
# documented operator-run step, not a Hub `cluster_dir` auto-apply (which only
# handles plain manifests, and the Hub build pipeline has no `ko`).
#
# Idempotent-ish: CRD/manifest applies are safe to re-run; the ko builds re-push
# the :latest tag. Inspect and re-run the individual step you need.
set -euo pipefail

# --- Hub template vars (same names the feature's infra manifests use) ---------
: "${PROJECT_NAME:?set PROJECT_NAME to your GCP project id}"
: "${CLUSTER:?set CLUSTER to your GKE cluster name}"
: "${REGION:?set REGION to your cluster region, e.g. us-central1}"
ARTIFACT_REGISTRY_REPO="${ARTIFACT_REGISTRY_REPO:-gke-showcase}"

# Upstream agent-substrate source. Cloned fresh into WORK_DIR unless UPSTREAM_DIR
# points at an existing checkout (e.g. a cached clone).
UPSTREAM_REPO_URL="${UPSTREAM_REPO_URL:-https://github.com/agent-substrate/substrate.git}"
WORK_DIR="${WORK_DIR:-/tmp/substrate-src}"
UPSTREAM_DIR="${UPSTREAM_DIR:-}"

# ko pushes every operator image (atecontroller, atelet, ateom-gvisor) here. This
# MUST match the registry path the feature's WorkerPool ateomImage references:
#   ${REGION}-docker.pkg.dev/${PROJECT_NAME}/${ARTIFACT_REGISTRY_REPO}/ateom-gvisor:latest
export KO_DOCKER_REPO="${REGION}-docker.pkg.dev/${PROJECT_NAME}/${ARTIFACT_REGISTRY_REPO}"

fail() { echo "FAIL [$1] $2" >&2; exit 1; }
note() { echo "==> $*"; }

# --- 0. preflight -------------------------------------------------------------
command -v gcloud  >/dev/null || fail preflight "gcloud not on PATH"
command -v kubectl >/dev/null || fail preflight "kubectl not on PATH"
command -v ko      >/dev/null || fail preflight "ko not on PATH (https://ko.build)"
command -v git     >/dev/null || fail preflight "git not on PATH"

note "[0/5] cluster credentials + Artifact Registry auth"
gcloud container clusters get-credentials "${CLUSTER}" \
  --region "${REGION}" --project "${PROJECT_NAME}" --quiet \
  || fail preflight "get-credentials failed — does the cluster exist?"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet \
  || fail preflight "configure-docker for ${REGION}-docker.pkg.dev failed"

# --- 1. upstream source -------------------------------------------------------
if [ -n "${UPSTREAM_DIR}" ]; then
  note "[1/5] using existing upstream checkout: ${UPSTREAM_DIR}"
  SRC="${UPSTREAM_DIR}"
else
  note "[1/5] cloning ${UPSTREAM_REPO_URL} -> ${WORK_DIR}"
  rm -rf "${WORK_DIR}"
  git clone --depth 1 "${UPSTREAM_REPO_URL}" "${WORK_DIR}"
  SRC="${WORK_DIR}"
fi
cd "${SRC}"
[ -d manifests/ate-install/generated ] || fail source "manifests/ate-install/generated not found — unexpected upstream layout"

# --- 2. CRDs (workerpools, actortemplates, sandboxconfigs) --------------------
note "[2/5] applying ate.dev CRDs"
ko apply -f manifests/ate-install/generated
kubectl wait --for=condition=Established --timeout=60s \
  crd/workerpools.ate.dev crd/actortemplates.ate.dev crd/sandboxconfigs.ate.dev

# --- 3. gVisor SandboxConfig (validation policy + default class) --------------
# The WorkerPool's `sandboxClass: gvisor` resolves to this cluster-scoped default.
note "[3/5] applying SandboxConfig validation policy + default gVisor class"
kubectl apply -f manifests/ate-install/sandboxconfig-validation.yaml
kubectl apply -f manifests/ate-install/sandboxconfig-gvisor.yaml

# --- 4. core reconcile control plane (ate-controller + atelet) ---------------
# CORE ONLY: ate-controller (reconciles WorkerPool -> Deployment) + atelet (lays
# the gVisor runsc binary onto nodes). We intentionally skip the alpha data-plane
# manifests in this same directory (ate-api-server.yaml, atenet-*.yaml,
# valkey.yaml, pod-certificate-controller.yaml) — they require alpha
# certificates.k8s.io/v1beta1 (ClusterTrustBundle / PodCertificate) not served on
# a Standard cluster, and the core reconcile loop does not depend on them.
note "[4/5] deploying ate-controller (WorkerPool reconciler) + atelet DaemonSet"
ko apply -f manifests/ate-install/ate-controller.yaml
ko apply -f manifests/ate-install/atelet.yaml
kubectl rollout status deployment/ate-controller -n ate-system --timeout=180s
kubectl rollout status daemonset/atelet         -n ate-system --timeout=180s

# --- 5. ateom-gvisor worker image --------------------------------------------
# The WorkerPool's ateomImage points at ${KO_DOCKER_REPO}/ateom-gvisor:latest.
# --base-import-paths => image path is exactly <repo>/ateom-gvisor (no md5 hash
# suffix); --tags=latest matches the WorkerPool ref.
note "[5/5] building + pushing ateom-gvisor:latest -> ${KO_DOCKER_REPO}/ateom-gvisor"
ko build --base-import-paths --tags=latest --push ./cmd/ateom-gvisor

cat <<EOF

==> Done. Core substrate reconcile control plane is installed:
      - CRDs:            workerpools / actortemplates / sandboxconfigs (ate.dev)
      - controller:      deployment/ate-controller  (ate-system)
      - node agent:      daemonset/atelet           (ate-system)
      - sandbox class:   gvisor (default SandboxConfig)
      - worker image:    ${KO_DOCKER_REPO}/ateom-gvisor:latest
    The alpha agent-identity data plane (apiserver / atenet / valkey /
    pod-certificate-controller) was intentionally NOT installed — see README.md.

    Now deploy the substrate-basic feature from the Hub.
EOF
