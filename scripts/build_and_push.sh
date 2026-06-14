#!/bin/bash

# Exit immediately if any command exits with a non-zero status.
set -e

# Load environment variables from local .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Ensure feature submodules are checked out so features/* (e.g. inference-gateway) are
# present — no need to remember `git submodule update --init --recursive`. Idempotent and
# a no-op for an already-initialized checkout; non-fatal if it can't reach the network.
if [ -f .gitmodules ] && git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Syncing feature submodules..."
  git submodule update --init --recursive || echo "Warning: submodule sync failed; continuing (ensure features/* are present)."
fi

# Fallback to gcloud config project if PROJECT_NAME is blank
PROJECT_ID=${PROJECT_NAME:-$(gcloud config get-value project)}
REGION=${REGION:-"us-west1"}
REPO_NAME=${ARTIFACT_REGISTRY_REPO:-"gke-showcase-repo"}
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

# Python interpreter for reading feature descriptors (prefer the repo venv, which has PyYAML)
PY="python3"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

# Help menu
show_help() {
  echo "GKE Showcase Hub Container Builder Utility"
  echo "Usage: ./scripts/build_and_push.sh [options]"
  echo ""
  echo "Options:"
  echo "  --feature <name>  Build only 'admin', a feature name, or a specific image name."
  echo "                    Feature images are discovered from features/*/feature.yaml."
  echo "  --help            Display this menu"
  echo ""
  echo "Discoverable feature build targets (feature -> image):"
  "$PY" scripts/feature_builds.py | awk -F'\t' '{printf "  %-16s -> %s\n", $1, $2}'
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

# The Admin Hub container is the platform itself (not a feature), so it stays explicit.
build_admin() {
  echo ">>> Building Showcase Admin Dashboard..."
  docker build -t "${REGISTRY}/showcase-admin:latest" -f showcase_admin/Dockerfile .
  echo ">>> Pushing Showcase Admin Dashboard..."
  docker push "${REGISTRY}/showcase-admin:latest"
}

# Build one feature image. Entries with a git source are cloned and built from upstream;
# otherwise the build context is resolved inside the feature directory.
# Args: feature_name image context dockerfile git
build_feature_image() {
  local fname="$1" image="$2" context="$3" dockerfile="$4" git_url="$5"
  local tag="${REGISTRY}/${image}:latest"

  if [ "$git_url" != "-" ]; then
    local tmp; tmp=$(mktemp -d)
    echo ">>> [$fname] Cloning ${git_url} to build ${image}..."
    git clone --depth 1 "$git_url" "$tmp"
    if [ "$dockerfile" != "-" ]; then
      docker build -t "$tag" -f "${tmp}/${dockerfile}" "${tmp}/${context}"
    else
      docker build -t "$tag" "${tmp}/${context}"
    fi
    rm -rf "$tmp"
  else
    local feature_dir="features/${fname}"
    echo ">>> [$fname] Building ${image}..."
    if [ "$dockerfile" != "-" ]; then
      docker build -t "$tag" -f "${feature_dir}/${dockerfile}" "${feature_dir}/${context}"
    else
      docker build -t "$tag" "${feature_dir}/${context}"
    fi
  fi
  echo ">>> [$fname] Pushing ${image}..."
  docker push "$tag"
}

# Iterate every build target declared across features/*/feature.yaml. When TARGET_FEATURE
# is set it filters by feature name OR image name; otherwise all features build.
build_features() {
  local matched=0
  while IFS=$'\t' read -r fname image context dockerfile git_url; do
    [ -z "$image" ] && continue
    if [ -n "$TARGET_FEATURE" ] && [ "$TARGET_FEATURE" != "$fname" ] && [ "$TARGET_FEATURE" != "$image" ]; then
      continue
    fi
    matched=1
    build_feature_image "$fname" "$image" "$context" "$dockerfile" "$git_url"
  done < <("$PY" scripts/feature_builds.py)

  if [ -n "$TARGET_FEATURE" ] && [ "$matched" -eq 0 ]; then
    echo "Error: no build target matched feature/image '$TARGET_FEATURE'."
    show_help
    exit 1
  fi
}

# Orchestrate builds
if [ -n "$TARGET_FEATURE" ]; then
  if [ "$TARGET_FEATURE" = "admin" ]; then
    build_admin
  else
    build_features
  fi
else
  build_admin
  build_features
fi

echo "======================================================================"
echo " GKE Showcase Hub images pushed successfully to ${REGISTRY}"
echo "======================================================================"
