#!/bin/bash

# Exit immediately if any command exits with a non-zero status.
set -e

# Load environment variables from local .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Set defaults
PROJECT_ID=${PROJECT_NAME:-$(gcloud config get-value project)}
REGION=${REGION:-"us-west1"}
CLUSTER_NAME=${CLUSTER_NAME:-"gke-showcase-cluster"}
CLUSTER_VERSION=${CLUSTER_VERSION:-"1.35.2-gke.1269000"}
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

# Base cluster creation
if gcloud container clusters describe "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "Cluster $CLUSTER_NAME already exists."
  echo "Verifying and enabling Gateway API on existing cluster..."
  gcloud beta container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --gateway-api=standard --quiet || echo "Gateway API already enabled or update in progress."
  echo "Verifying and enabling Agent Sandbox on existing cluster..."
  gcloud beta container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --enable-agent-sandbox --quiet || echo "Agent Sandbox already enabled or update in progress."
  echo "Verifying and enabling GCSFuse CSI driver on existing cluster..."
  gcloud beta container clusters update "$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" --update-addons=GcsFuseCsiDriver=ENABLED --quiet || echo "GCSFuse CSI driver already enabled or update in progress."
else
  echo "Creating base GKE Cluster with Workload Identity, Gateway API, and Agent Sandbox..."
  gcloud beta container clusters create "$CLUSTER_NAME" \
      --region="$REGION" \
      --project="$PROJECT_ID" \
      --cluster-version="$CLUSTER_VERSION" \
      --machine-type="$MACHINE_TYPE" \
      --num-nodes=2 \
      --no-enable-master-authorized-networks \
      --workload-pool="${PROJECT_ID}.svc.id.goog" \
      --gateway-api=standard \
      --enable-agent-sandbox
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

gcloud container node-pools create showcase-gpu-pool \
    --cluster="$CLUSTER_NAME" --region="$REGION" --project="$PROJECT_ID" \
    --machine-type="g2-standard-8" \
    --accelerator="type=nvidia-l4,count=1" \
    --spot \
    --enable-autoscaling --min-nodes=0 --max-nodes=2 --num-nodes=0 \
    --quiet || echo "Spot GPU node pool already exists or skipped."

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
