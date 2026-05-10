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
echo " BOOTSTRAPPING GKE FEATURE SHOWCASE CLUSTER: ${CLUSTER_NAME}"
echo " NOTE: Specialized Node Pools (gVisor & GPUs) are NOT created here."
echo " They will be provisioned dynamically when their features are deployed."
echo "======================================================================"

# 1. Create GKE Standard Cluster with a standard default node pool and Workload Identity
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

# 2. Enable GKE Cluster features (Agent Sandbox & Gateway API)
echo "Updating cluster capabilities (Agent Sandbox & Gateway API)..."
gcloud beta container clusters update "$CLUSTER_NAME" \
    --region="$REGION" \
    --enable-agent-sandbox \
    --gateway-api=standard

# 3. Retrieve cluster credentials
echo "Importing GKE context credentials locally..."
gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION"

# 4. Configure Workload Identity bindings for Vertex AI
echo "Configuring Workload Identity IAM roles..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")

# Bind service accounts dynamically to Vertex AI user role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --role="roles/aiplatform.user" \
    --member="principal://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${PROJECT_ID}.svc.id.goog/subject/ns/gke-showcase-sandbox/sa/default" \
    --condition=None || echo "WIF binding mapped or failed, continuing..."

# 5. Provision admin Namespace and Shared Gateway
echo "Creating admin namespace..."
kubectl create namespace gke-showcase-admin --dry-run=client -o yaml | kubectl apply -f -

echo "Applying shared gateway configuration..."
kubectl apply -f infra/gateway.yaml

# 6. Setup Showcase Admin Dashboard PVC & Deployments
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
