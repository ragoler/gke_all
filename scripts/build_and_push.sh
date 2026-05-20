#!/bin/bash

# Exit immediately if any command exits with a non-zero status.
set -e

# Load environment variables from local .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Fallback to gcloud config project if PROJECT_NAME is blank
PROJECT_ID=${PROJECT_NAME:-$(gcloud config get-value project)}
REGION=${REGION:-"us-west1"}
REPO_NAME=${ARTIFACT_REGISTRY_REPO:-"gke-showcase-repo"}
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

# Help menu
show_help() {
  echo "GKE Showcase Hub Container Builder Utility"
  echo "Usage: ./scripts/build_and_push.sh [options]"
  echo ""
  echo "Options:"
  echo "  --feature <name>  Build only a specific container: admin, sandbox-demo, sandbox-router, gpu-playroom, inference-gateway"
  echo "  --help            Display this menu"
}

# Parse command-line args
TARGET_FEATURE=""
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --feature) TARGET_FEATURE="$2"; shift ;;
    --help) show_help; exit 0 ;;
    *) echo "Unknown parameter: $1"; show_help; exit 1 ;;
  esac
  shift
done

echo "======================================================================"
echo " GKE SHOWCASE HUB BUILDER: Pushing to ${REGISTRY}"
echo "======================================================================"

# Create Artifact Registry repository if not exists
echo "Creating Artifact Registry Docker repository if it doesn't exist..."
gcloud artifacts repositories create "$REPO_NAME" \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --description="Docker repository for GKE Feature Showcase Hub showcases" || echo "Repository already exists or skipped, continuing..."

echo "Authenticating Docker daemon to Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Build and push target containers
build_admin() {
  echo ">>> Building Showcase Admin Dashboard..."
  docker build -t "${REGISTRY}/showcase-admin:latest" -f showcase_admin/Dockerfile .
  echo ">>> Pushing Showcase Admin Dashboard..."
  docker push "${REGISTRY}/showcase-admin:latest"
}

build_sandbox_demo() {
  echo ">>> Building Sandbox Demo Workload container..."
  docker build -t "${REGISTRY}/agent-sandbox-demo:latest" ./features/agent-sandbox/demo-app
  echo ">>> Pushing Sandbox Demo Workload container..."
  docker push "${REGISTRY}/agent-sandbox-demo:latest"
}

build_sandbox_router() {
  echo ">>> Building Sandbox Router container..."
  # Clones and builds the sandbox router from the official upstream Kubernetes-SIGs repository
  TMP_DIR=$(mktemp -d)
  echo "Cloning upstream kubernetes-sigs/agent-sandbox repo into ${TMP_DIR}..."
  git clone https://github.com/kubernetes-sigs/agent-sandbox.git "$TMP_DIR"
  
  docker build -t "${REGISTRY}/agent-sandbox-router:latest" "${TMP_DIR}/clients/python/agentic-sandbox-client/sandbox-router"
  docker push "${REGISTRY}/agent-sandbox-router:latest"
  rm -rf "$TMP_DIR"
  echo ">>> Sandbox Router container pushed successfully."
}

build_gpu_playroom() {
  echo ">>> Building GPU Inference Playroom app..."
  docker build -t "${REGISTRY}/gpu-inference-playroom:latest" -f ./features/gpu-inference/app/Dockerfile ./features/gpu-inference
  echo ">>> Pushing GPU Inference Playroom app..."
  docker push "${REGISTRY}/gpu-inference-playroom:latest"
}

build_inference_gateway() {
  echo ">>> Building Inference Gateway Playroom app..."
  docker build -t "${REGISTRY}/inference-gateway-playroom:latest" -f ./features/inference-gateway/app/Dockerfile ./features/inference-gateway
  echo ">>> Pushing Inference Gateway Playroom app..."
  docker push "${REGISTRY}/inference-gateway-playroom:latest"
}

# Orchestrate builds
if [ -n "$TARGET_FEATURE" ]; then
  case $TARGET_FEATURE in
    admin) build_admin ;;
    sandbox-demo) build_sandbox_demo ;;
    sandbox-router) build_sandbox_router ;;
    gpu-playroom) build_gpu_playroom ;;
    inference-gateway) build_inference_gateway ;;
    *) echo "Unsupported feature target: $TARGET_FEATURE"; exit 1 ;;
  esac
else
  # Build all by default
  build_admin
  build_sandbox_demo
  build_sandbox_router
  build_gpu_playroom
  build_inference_gateway
fi

echo "======================================================================"
echo " GKE Showcase Hub images pushed successfully to ${REGISTRY}"
echo "======================================================================"
