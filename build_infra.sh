#!/bin/bash

# Exit immediately if any command exits with a non-zero status.
set -e

# Load environment variables from local .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Sync feature submodules to the LATEST commit on each feature's tracked branch
# (branch set per submodule in .gitmodules, = main) so the Hub always ships the
# newest feature code without manual SHA bumps. --remote follows the branch tip;
# --init checks out any not-yet-initialized submodule. Idempotent; non-fatal if it
# can't reach the network (falls back to whatever is already checked out).
if [ -f .gitmodules ] && git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Syncing feature submodules to latest main..."
  git submodule update --remote --init --recursive || echo "Warning: submodule sync failed; continuing (ensure features/* are present)."
fi

# Set defaults
PROJECT_ID=${PROJECT_NAME:-$(gcloud config get-value project)}
REGION=${REGION:-"us-west1"}
CLUSTER_NAME=${CLUSTER_NAME:-"gke-showcase-cluster"}
# Optional. Leave empty to use GKE's release-channel default (always valid & current).
# Only set CLUSTER_VERSION to pin a specific version (note: GPU time-sharing needs
# >= 1.35.2-gke.1485000).
CLUSTER_VERSION=${CLUSTER_VERSION:-""}
NODE_POOL_NAME=${NODE_POOL_NAME:-"showcase-node-pool"}
MACHINE_TYPE=${MACHINE_TYPE:-"e2-standard-2"}
ARTIFACT_REGISTRY_REPO=${ARTIFACT_REGISTRY_REPO:-"gke-showcase-repo"}

# Validation check
if [ -z "$CLUSTER_NAME" ]; then
  echo "Error: CLUSTER_NAME is not configured in .env."
  exit 1
fi

# Parse command-line arguments
DESTROY_MODE=false
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --destroy) DESTROY_MODE=true ;;
    *) echo "Unknown parameter: $1"; echo "Usage: ./build_infra.sh [--destroy]"; exit 1 ;;
  esac
  shift
done

# ----------------------------------------------------------------------
# 1. DESTROY MODE: Cleanup all GCP resources cleanly
# ----------------------------------------------------------------------
if [ "$DESTROY_MODE" = "true" ]; then
  echo "======================================================================"
  echo " DESTROYING GKE FEATURE SHOWCASE INFRASTRUCTURE: ${CLUSTER_NAME}"
  echo "======================================================================"
  
  if gcloud container clusters describe "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "Deleting GKE Cluster $CLUSTER_NAME in region $REGION..."
    gcloud container clusters delete "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --quiet
    echo "Cluster $CLUSTER_NAME deleted successfully."
  else
    echo "Cluster $CLUSTER_NAME does not exist, skipping cluster deletion."
  fi
  
  if gcloud artifacts repositories describe "$ARTIFACT_REGISTRY_REPO" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "Deleting Artifact Registry repository $ARTIFACT_REGISTRY_REPO in location $REGION..."
    gcloud artifacts repositories delete "$ARTIFACT_REGISTRY_REPO" --location="$REGION" --project="$PROJECT_ID" --quiet
    echo "Repository $ARTIFACT_REGISTRY_REPO deleted successfully."
  else
    echo "Repository $ARTIFACT_REGISTRY_REPO does not exist, skipping repository deletion."
  fi

  # Delete the proxy-only subnet last (it's deletable once the cluster's gateways are gone).
  if gcloud compute networks subnets describe gke-showcase-proxy-subnet --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "Deleting proxy-only subnet gke-showcase-proxy-subnet in region $REGION..."
    gcloud compute networks subnets delete gke-showcase-proxy-subnet --region="$REGION" --project="$PROJECT_ID" --quiet \
      || echo "Could not delete proxy-only subnet (it may still be reconciling or in use); leaving it — bootstrap will reuse it."
  else
    echo "Proxy-only subnet gke-showcase-proxy-subnet does not exist, skipping."
  fi

  echo "======================================================================"
  echo " Cleanup completed successfully!"
  echo "======================================================================"
  exit 0
fi

# ----------------------------------------------------------------------
# 2. BOOTSTRAP MODE: Provision baseline GKE Cluster
# ----------------------------------------------------------------------
echo "======================================================================"
echo " BOOTSTRAPPING GKE FEATURE SHOWCASE CLUSTER: ${CLUSTER_NAME}"
echo " NOTE: Specialized Node Pools (gVisor & GPUs) are NOT created here."
echo " They will be provisioned dynamically when their features are deployed."
echo "======================================================================"

# Pre-flight validation: ensure target container images exist in Artifact Registry
echo "Verifying that target container images exist in Artifact Registry..."
for img in showcase-admin agent-sandbox-demo agent-sandbox-router gpu-inference-playroom; do
  if ! gcloud artifacts tags list --package="$img" --repository="$ARTIFACT_REGISTRY_REPO" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "Error: Container image '$img' not found in Artifact Registry repository '$ARTIFACT_REGISTRY_REPO' ($REGION)."
    echo "Please execute ./scripts/build_and_push.sh before running ./build_infra.sh to populate required container images."
    exit 1
  fi
done
echo "Pre-flight image validation passed successfully."

# Pre-flight validation: ensure Network Services API is enabled for GKE Gateway Service Extensions
echo "Verifying and enabling Network Services API for GKE Gateway Service Extensions..."
gcloud services enable networkservices.googleapis.com --project="$PROJECT_ID" --quiet || echo "Network Services API already enabled."

# Image Streaming (gcfs) needs the Container File System API.
echo "Verifying and enabling Container File System API (for Image Streaming)..."
gcloud services enable containerfilesystem.googleapis.com --project="$PROJECT_ID" --quiet || echo "Container File System API already enabled."


# Pre-flight validation: ensure proxy-only subnet exists in region for Regional Gateway API
echo "Verifying and provisioning proxy-only subnet in region $REGION for Regional Gateway API..."
if gcloud compute networks subnets describe gke-showcase-proxy-subnet --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Proxy-only subnet gke-showcase-proxy-subnet already exists in $REGION; skipping."
else
  gcloud compute networks subnets create gke-showcase-proxy-subnet \
      --purpose=REGIONAL_MANAGED_PROXY \
      --role=ACTIVE \
      --region="$REGION" \
      --network=default \
      --range=192.168.10.0/23 \
      --project="$PROJECT_ID" \
      --quiet
fi

# Base cluster creation
if gcloud container clusters describe "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Cluster $CLUSTER_NAME already exists."
  echo "Verifying and enabling Gateway API on existing cluster..."
  gcloud beta container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --gateway-api=standard --quiet || echo "Gateway API already enabled or update in progress."
  echo "Verifying and enabling Agent Sandbox on existing cluster..."
  gcloud beta container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --enable-agent-sandbox --quiet || echo "Agent Sandbox already enabled or update in progress."
  echo "Verifying and enabling GCSFuse CSI driver on existing cluster..."
  gcloud beta container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --update-addons=GcsFuseCsiDriver=ENABLED --quiet || echo "GCSFuse CSI driver already enabled or update in progress."
  echo "Verifying and enabling Node Auto-Provisioning (lets GPU Custom Compute Classes auto-create pools with fallback)..."
  gcloud container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" \
      --enable-autoprovisioning --min-cpu=0 --max-cpu=200 --min-memory=0 --max-memory=2000 \
      --max-accelerator=type=nvidia-l4,count=8 --max-accelerator=type=nvidia-rtx-pro-6000,count=8 \
      --quiet || echo "Node Auto-Provisioning already enabled or update in progress."
  echo "Verifying and enabling Image Streaming (streams the 14GB+ vLLM image so GPU pods start in seconds, not a ~9min pull)..."
  gcloud container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --enable-image-streaming --quiet || echo "Image Streaming already enabled or update in progress."
else
  echo "Creating base GKE Cluster with Workload Identity, Gateway API, and Agent Sandbox..."
  # Pin the version only if CLUSTER_VERSION is set; otherwise use the channel default.
  VERSION_FLAG=()
  if [ -n "$CLUSTER_VERSION" ]; then
    VERSION_FLAG=(--cluster-version="$CLUSTER_VERSION")
    echo "Pinning cluster version: $CLUSTER_VERSION"
  else
    echo "Using GKE release-channel default version (CLUSTER_VERSION unset)."
  fi
  gcloud beta container clusters create "$CLUSTER_NAME" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      "${VERSION_FLAG[@]}" \
      --machine-type="$MACHINE_TYPE" \
      `# regional cluster: --num-nodes is PER ZONE, so 1 x 3 zones = 3 nodes total.` \
      `# The default pool only hosts the admin + lightweight operators; feature` \
      `# workloads auto-provision their own pools via ComputeClass/NAP.` \
      --num-nodes=1 \
      --no-enable-master-authorized-networks \
      --workload-pool="${PROJECT_ID}.svc.id.goog" \
      --gateway-api=standard \
      --enable-agent-sandbox \
      --enable-image-streaming \
      --enable-autoprovisioning \
      --min-cpu=0 --max-cpu=200 --min-memory=0 --max-memory=2000 \
      --max-accelerator=type=nvidia-l4,count=8 \
      --max-accelerator=type=nvidia-rtx-pro-6000,count=8
fi

# Retrieve GKE cluster credentials
echo "Importing GKE context credentials locally..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID"

# Provision zero-cost autoscaling specialized node pools
echo "Provisioning zero-cost autoscaling specialized node pools..."
gcloud container node-pools create showcase-gvisor-pool \
    --cluster="$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" \
    --machine-type="e2-standard-2" \
    --sandbox="type=gvisor" \
    --workload-metadata=GKE_METADATA \
    --enable-autoscaling --min-nodes=0 --max-nodes=2 --num-nodes=0 \
    --quiet || echo "gVisor node pool already exists or skipped."

# No fixed GPU node pool: the gpu-inference 'gpu-inference-flex' Custom Compute Class
# (features/gpu-inference/infra/compute-classes.yaml) provisions GPU nodes on demand via
# Node Auto-Provisioning, falling back across tiers (G2 Spot L4 -> G4 Spot -> G2 on-demand
# -> G4 on-demand) so a Spot stockout no longer blocks the vLLM workload.

# Apply per-feature cluster-scoped prerequisites (declared via paths.cluster_dir in
# each feature.yaml). These are resources that exist once per cluster — GPU
# ComputeClasses, CRD installs, etc. — that cannot live inside a per-deploy namespace.
# Features without a cluster_dir contribute nothing here (no-op).
echo "Applying per-feature cluster-scoped prerequisites..."
PY="python3"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"
export PROJECT_NAME="$PROJECT_ID"
export REGION
export ARTIFACT_REGISTRY_REPO
while IFS=$'\t' read -r feature_name cluster_dir; do
  [ -z "$cluster_dir" ] && continue
  echo "  -> [$feature_name] applying cluster prerequisites from ${cluster_dir}"
  if [ -f "$cluster_dir/kustomization.yaml" ] || [ -f "$cluster_dir/kustomization.yml" ]; then
    # Kustomize dir (e.g. remote CRD bundles via apply -k). kustomization.yaml is not a
    # standalone resource, so this replaces — not supplements — the per-file apply below.
    # Server-side apply: large CRD bundles (e.g. KubeRay's RayCluster CRD) exceed the
    # 256KB client-side last-applied annotation limit. --force-conflicts lets a re-bootstrap
    # take ownership of fields a prior client-side apply set.
    kubectl apply --server-side --force-conflicts -k "$cluster_dir"
  else
    for manifest in "$cluster_dir"/*.yaml "$cluster_dir"/*.yml; do
      [ -e "$manifest" ] || continue
      "$PY" -c "import os, sys; print(os.path.expandvars(sys.stdin.read()))" < "$manifest" | kubectl apply -f -
    done
  fi
done < <("$PY" scripts/feature_cluster_dirs.py)

# Configure Workload Identity bindings for Vertex AI
echo "Configuring Workload Identity IAM roles..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

# Bind service accounts dynamically to Vertex AI user role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --role="roles/aiplatform.user" \
    --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${PROJECT_ID}.svc.id.goog/*" \
    --condition=None || echo "WIF binding mapped or failed, continuing..."

# Grant GKE nodes read access to Artifact Registry in the same project
echo "Configuring Artifact Registry read permissions for GKE nodes..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --role="roles/artifactregistry.reader" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --condition=None || echo "Registry IAM role binding skipped or failed, continuing..."

# Provision admin Namespace
echo "Creating admin namespace..."
kubectl create namespace gke-showcase-admin --dry-run=client -o yaml | kubectl apply -f -

echo "Creating secure credentials secret..."
kubectl create secret generic showcase-admin-creds \
    --from-literal=ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" \
    --from-literal=ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin-password}" \
    --from-literal=JWT_SECRET_KEY="${JWT_SECRET_KEY:-mock-jwt-secure-signing-secret-key}" \
    -n gke-showcase-admin --dry-run=client -o yaml | kubectl apply -f -

# Setup Showcase Admin DashboardPVC & Deployments
echo "Deploying Showcase Admin Hub..."
export PROJECT_NAME="$PROJECT_ID"
export REGION
export ARTIFACT_REGISTRY_REPO
export ADMIN_AUTHENTICATION_ENABLED="${ADMIN_AUTHENTICATION_ENABLED:-TRUE}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin-password}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-mock-jwt-secure-signing-secret-key}"
export GOOGLE_GENAI_USE_VERTEXAI="${GOOGLE_GENAI_USE_VERTEXAI:-FALSE}"
export GEMINI_API_KEY="${GEMINI_API_KEY:-}"

python3 -c "import os, sys; print(os.path.expandvars(sys.stdin.read()))" < infra/main-app.yaml | kubectl apply -f -

echo "======================================================================"
echo " GKE Feature Showcase Hub Bootstrapped successfully!"
echo "======================================================================"
