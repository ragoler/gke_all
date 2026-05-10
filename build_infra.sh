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
PROJECT_ID=$(gcloud config get-value project)
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
  
  if gcloud container clusters describe "$CLUSTER_NAME" --region="$REGION" >/dev/null 2>&1; then
    echo "Deleting GKE Cluster $CLUSTER_NAME in region $REGION..."
    gcloud container clusters delete "$CLUSTER_NAME" --region="$REGION" --quiet
    echo "Cluster $CLUSTER_NAME deleted successfully."
  else
    echo "Cluster $CLUSTER_NAME does not exist, skipping cluster deletion."
  fi
  
  if gcloud artifacts repositories describe "$ARTIFACT_REGISTRY_REPO" --location="$REGION" >/dev/null 2>&1; then
    echo "Deleting Artifact Registry repository $ARTIFACT_REGISTRY_REPO in location $REGION..."
    gcloud artifacts repositories delete "$ARTIFACT_REGISTRY_REPO" --location="$REGION" --quiet
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

# Base cluster creation
if gcloud container clusters describe "$CLUSTER_NAME" --region="$REGION" >/dev/null 2>&1; then
  echo "Cluster $CLUSTER_NAME already exists, skipping cluster creation."
else
  echo "Creating base GKE Cluster with Workload Identity..."
  gcloud beta container clusters create "$CLUSTER_NAME" \
      --region="$REGION" \
      --cluster-version="$CLUSTER_VERSION" \
      --machine-type="$MACHINE_TYPE" \
      --num-nodes=2 \
      --no-enable-master-authorized-networks \
      --workload-pool="${PROJECT_ID}.svc.id.goog"
fi

# Retrieve GKE cluster credentials
echo "Importing GKE context credentials locally..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION"

# Configure Workload Identity bindings for Vertex AI
echo "Configuring Workload Identity IAM roles..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

# Bind service accounts dynamically to Vertex AI user role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --role="roles/aiplatform.user" \
    --member="principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${PROJECT_ID}.svc.id.goog/subject/ns/gke-showcase-sandbox/sa/default" \
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
    -n gke-showcase-admin --dry-run=client -o yaml | kubectl apply -f -

# Setup Showcase Admin DashboardPVC & Deployments
echo "Deploying Showcase Admin Hub..."
export PROJECT_NAME="$PROJECT_ID"
export REGION
export ARTIFACT_REGISTRY_REPO
export ADMIN_AUTHENTICATION_ENABLED="${ADMIN_AUTHENTICATION_ENABLED:-TRUE}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin-password}"
export GOOGLE_GENAI_USE_VERTEXAI="${GOOGLE_GENAI_USE_VERTEXAI:-FALSE}"
export GEMINI_API_KEY="${GEMINI_API_KEY:-}"

python3 -c "import os, sys; print(os.path.expandvars(sys.stdin.read()))" < infra/main-app.yaml | kubectl apply -f -

echo "======================================================================"
echo " GKE Feature Showcase Hub Bootstrapped successfully!"
echo "======================================================================"
