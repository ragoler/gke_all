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

echo "======================================================================"
echo " BOOTSTRAPPING GKE FEATURE SHOWCASE HUB CLUSTER: ${CLUSTER_NAME}"
echo "======================================================================"

# 1. Create GKE Standard Cluster with Workload Identity enabled
if gcloud container clusters describe "$CLUSTER_NAME" --region="$REGION" >/dev/null 2>&1; then
  echo "Cluster $CLUSTER_NAME already exists, skipping cluster creation."
else
  echo "Creating GKE Cluster with Workload Identity..."
  gcloud beta container clusters create "$CLUSTER_NAME" \
      --region="$REGION" \
      --cluster-version="$CLUSTER_VERSION" \
      --no-enable-master-authorized-networks \
      --workload-pool="${PROJECT_ID}.svc.id.goog"
fi

# 2. Create gVisor Node Pool (For Agent Sandbox)
GVISOR_POOL="showcase-gvisor-pool"
if gcloud container node-pools describe "$GVISOR_POOL" --cluster="$CLUSTER_NAME" --region="$REGION" >/dev/null 2>&1; then
  echo "gVisor Node Pool $GVISOR_POOL already exists."
else
  echo "Creating gVisor-enabled Node Pool..."
  gcloud container node-pools create "$GVISOR_POOL" \
      --cluster="$CLUSTER_NAME" \
      --region="$REGION" \
      --machine-type="e2-standard-2" \
      --image-type=cos_containerd \
      --sandbox=type=gvisor
fi

# 3. Create Spot NVIDIA L4 GPU Node Pool (For vLLM GPU Inference Showcase)
GPU_POOL="showcase-gpu-pool"
if gcloud container node-pools describe "$GPU_POOL" --cluster="$CLUSTER_NAME" --region="$REGION" >/dev/null 2>&1; then
  echo "GPU Node Pool $GPU_POOL already exists."
else
  echo "Creating Spot GPU Node Pool (NVIDIA L4)..."
  gcloud container node-pools create "$GPU_POOL" \
      --cluster="$CLUSTER_NAME" \
      --region="$REGION" \
      --machine-type="g2-standard-8" \
      --accelerator="type=nvidia-l4,count=1" \
      --enable-image-streaming \
      --cloud-provider-gke-spot=true
fi

# 4. Enable GKE Add-ons dynamically (Agent Sandbox + Gateway API)
echo "Updating cluster capabilities (Agent Sandbox & Gateway API)..."
gcloud beta container clusters update "$CLUSTER_NAME" \
    --region="$REGION" \
    --enable-agent-sandbox \
    --gateway-api=standard

# 5. Retrieve cluster context credentials
echo "Importing GKE context credentials locally..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION"

# 6. Configure IAM Workload Identity bindings for Vertex AI
echo "Configuring Workload Identity IAM roles..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

# Dynamically bind the default ServiceAccount in showcase namespaces to Vertex AI user role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --role="roles/aiplatform.user" \
    --member="principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${PROJECT_ID}.svc.id.goog/subject/ns/gke-showcase-sandbox/sa/default" \
    --condition=None || echo "WIF binding mapped or failed, continuing..."

# 7. Provision core Namespace and Shared Gateway
echo "Creating admin namespace..."
kubectl create namespace gke-showcase-admin --dry-run=client -o yaml | kubectl apply -f -

echo "Applying shared gateway configuration..."
kubectl apply -f infra/gateway.yaml

# 8. Setup Showcase Admin Dashboard deployments
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
