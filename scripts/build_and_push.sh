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
# (branch set per submodule in .gitmodules, = main) so we always build the newest
# feature code without manual SHA bumps. --remote follows the branch tip; --init
# checks out any not-yet-initialized submodule. Idempotent; non-fatal if it can't
# reach the network (falls back to whatever is already checked out).
if [ -f .gitmodules ] && git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Syncing feature submodules to latest main..."
  git submodule update --remote --init --recursive || echo "Warning: submodule sync failed; continuing (ensure features/* are present)."
fi

# Fallback to gcloud config project if PROJECT_NAME is blank
PROJECT_ID=${PROJECT_NAME:-$(gcloud config get-value project)}
REGION=${REGION:-"us-west1"}
CLUSTER_NAME=${CLUSTER_NAME:-"gke-showcase-cluster"}
REPO_NAME=${ARTIFACT_REGISTRY_REPO:-"gke-showcase-repo"}
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

# GKE nodes are amd64, so always build amd64 images regardless of the build host's
# architecture (a bare `docker build` on Apple Silicon/arm64 would otherwise produce
# arm64 images that crash on the cluster with exec-format errors). Overridable for the
# rare cross-arch case. On an amd64 build host this is a no-op.
BUILD_PLATFORM="${BUILD_PLATFORM:-linux/amd64}"

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
  echo "  --no-rollout      Do not 'kubectl rollout restart' affected Deployments after"
  echo "                    pushing (default: roll them if a cluster is reachable, so the"
  echo "                    new images take effect — :latest is not auto-pulled)."
  echo "  --help            Display this menu"
  echo ""
  echo "Discoverable feature build targets (feature -> image):"
  "$PY" scripts/feature_builds.py | awk -F'\t' '{printf "  %-16s -> %s\n", $1, $2}'
}

# Parse command-line args
TARGET_FEATURE=""
ROLLOUT=true
while [[ "$#" -gt 0 ]]; do
  case $1 in
    --feature) TARGET_FEATURE="$2"; shift ;;
    --no-rollout) ROLLOUT=false ;;
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

# Local docker is preferred (fast incremental builds), but not required: hosts with
# only gcloud+kubectl (no Docker daemon) fall back to Cloud Build below — the same
# principle as the helm-free kata prereq: the platform must not silently depend on
# tools the operator's machine may not have.
DOCKER_AVAILABLE=true
if command -v docker >/dev/null 2>&1; then
  echo "Authenticating Docker daemon to Artifact Registry..."
  gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
else
  DOCKER_AVAILABLE=false
  echo "docker not found — images will build remotely via Cloud Build (gcloud builds submit)."
fi

# Build + push one image, via local docker or Cloud Build.
# Args: tag context_dir [dockerfile_path]
# dockerfile_path is relative to the CWD (may be empty = <context>/Dockerfile); for the
# Cloud Build path it is re-expressed relative to the uploaded context, which it must
# live inside. Cloud Build workers are amd64, matching BUILD_PLATFORM's default.
build_push() {
  local tag="$1" context="$2" dockerfile="${3:-}"
  if [ "$DOCKER_AVAILABLE" = "true" ]; then
    if [ -n "$dockerfile" ]; then
      docker build --platform "$BUILD_PLATFORM" -t "$tag" -f "$dockerfile" "$context"
    else
      docker build --platform "$BUILD_PLATFORM" -t "$tag" "$context"
    fi
    docker push "$tag"
    return
  fi
  local df_in_ctx="Dockerfile"
  if [ -n "$dockerfile" ]; then
    df_in_ctx=$("$PY" -c "import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))" "$dockerfile" "$context")
  fi
  # mktemp dir rather than a suffixed file template — BSD/macOS mktemp requires the
  # XXXXXX to be trailing, and gcloud requires the config to end in .yaml.
  local cfgdir cfg
  cfgdir=$(mktemp -d)
  cfg="${cfgdir}/cloudbuild.yaml"
  cat > "$cfg" <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ['build', '-t', '${tag}', '-f', '${df_in_ctx}', '.']
images: ['${tag}']
EOF
  if gcloud builds submit "$context" --config "$cfg" --project "$PROJECT_ID" --quiet; then
    rm -rf "$cfgdir"
    return
  fi
  rm -rf "$cfgdir"
  # Last resort: Cloud Build can be denied by org policy for user credentials
  # (serviceusage.services.use). Build on the showcase cluster itself with Kaniko —
  # needs only gcloud+kubectl and Workload Identity. See scripts/kaniko_build.sh.
  echo "Cloud Build unavailable — falling back to an in-cluster Kaniko build..."
  PROJECT_ID="$PROJECT_ID" REGION="$REGION" \
    bash "$(dirname "$0")/kaniko_build.sh" "$tag" "$context" "$df_in_ctx"
}

# The Admin Hub container is the platform itself (not a feature), so it stays explicit.
build_admin() {
  echo ">>> Building Showcase Admin Dashboard..."
  build_push "${REGISTRY}/showcase-admin:latest" . showcase_admin/Dockerfile
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
      build_push "$tag" "${tmp}/${context}" "${tmp}/${dockerfile}"
    else
      build_push "$tag" "${tmp}/${context}"
    fi
    rm -rf "$tmp"
  else
    local feature_dir="features/${fname}"
    echo ">>> [$fname] Building ${image}..."
    if [ "$dockerfile" != "-" ]; then
      build_push "$tag" "${feature_dir}/${context}" "${feature_dir}/${dockerfile}"
    else
      build_push "$tag" "${feature_dir}/${context}"
    fi
  fi
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

# Roll the Deployments affected by this build so the cluster pulls the new images
# (a :latest tag is not re-pulled on its own). Default on; skip with --no-rollout, and a
# no-op when no cluster is reachable (e.g. a build-only machine).
roll_deployment() {
  local dep="$1" ns="$2"
  if kubectl get deployment "$dep" -n "$ns" >/dev/null 2>&1; then
    echo ">>> Rolling deployment/${dep} in ${ns}..."
    kubectl rollout restart "deployment/${dep}" -n "$ns" || echo "Warning: rollout of ${dep} failed."
  fi
}

maybe_rollout() {
  [ "$ROLLOUT" = "true" ] || { echo "Skipping rollout (--no-rollout)."; return; }
  if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl not found; skipping rollout (images are pushed)."; return
  fi
  # Point kubectl at the showcase cluster before rolling. Without this, a build machine whose
  # kubectl context is elsewhere (or unset) silently fails the reachability check below, so the
  # images get pushed but the Deployments never roll — leaving stale pods on :latest.
  if command -v gcloud >/dev/null 2>&1; then
    gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 \
      || echo "Note: could not fetch credentials for $CLUSTER_NAME (${REGION}); using current kubectl context."
  fi
  if ! kubectl get namespace gke-showcase-admin >/dev/null 2>&1; then
    echo "No reachable showcase cluster; skipping rollout (images are pushed)."; return
  fi
  echo "Rolling affected Deployments so new images take effect..."
  if [ -z "$TARGET_FEATURE" ] || [ "$TARGET_FEATURE" = "admin" ]; then
    roll_deployment showcase-admin-deployment gke-showcase-admin
  fi
  # Roll any built feature's Deployment in its default namespace (best-effort).
  while IFS=$'\t' read -r fname dep ns; do
    [ -z "$dep" ] && continue
    if [ -z "$TARGET_FEATURE" ] || [ "$TARGET_FEATURE" = "$fname" ]; then
      roll_deployment "$dep" "$ns"
    fi
  done < <("$PY" scripts/feature_deployments.py)
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

maybe_rollout
