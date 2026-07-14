#!/usr/bin/env bash
# Build + push one image with Kaniko ON the showcase cluster.
#
# This is the build path of last resort for hosts with no Docker daemon when
# `gcloud builds submit` is also unavailable (e.g. an org policy denies Cloud Build
# for user credentials — the error looks like "Caller does not have required
# permission to use project ... serviceusage.services.use"). It needs only
# gcloud + kubectl and a reachable showcase cluster with Workload Identity:
#   1. one-time (idempotent): an image-builder GSA with Artifact Registry write,
#      bound via Workload Identity to a kaniko-builder KSA in gke-showcase-admin
#   2. tar the build context, upload it to the project's _cloudbuild GCS bucket
#   3. run a Kaniko Job on the cluster that builds and pushes the image
#
# Usage: PROJECT_ID=... [REGION=...] kaniko_build.sh TAG CONTEXT_DIR [DOCKERFILE_IN_CONTEXT]
set -euo pipefail

TAG="${1:?usage: kaniko_build.sh TAG CONTEXT_DIR [DOCKERFILE_IN_CONTEXT]}"
CONTEXT="${2:?usage: kaniko_build.sh TAG CONTEXT_DIR [DOCKERFILE_IN_CONTEXT]}"
DOCKERFILE="${3:-Dockerfile}"
PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"

# The admin namespace always exists on a bootstrapped showcase cluster, and cluster
# reachability is a precondition of this path anyway (the Job runs there).
NS="${KANIKO_NAMESPACE:-gke-showcase-admin}"
KSA="kaniko-builder"
GSA_NAME="image-builder"
GSA="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="gs://${PROJECT_ID}_cloudbuild"
KANIKO_IMAGE="${KANIKO_IMAGE:-gcr.io/kaniko-project/executor:v1.23.2}"

echo "==> [kaniko] one-time setup (idempotent): builder identity + registry access"
if ! gcloud iam service-accounts describe "$GSA" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$GSA_NAME" --project "$PROJECT_ID" \
    --display-name "In-cluster Kaniko image builder"
fi
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${GSA}" --role="roles/artifactregistry.writer" \
  --condition=None --quiet >/dev/null
gcloud storage buckets add-iam-policy-binding "$BUCKET" \
  --member="serviceAccount:${GSA}" --role="roles/storage.objectViewer" >/dev/null
kubectl -n "$NS" get serviceaccount "$KSA" >/dev/null 2>&1 \
  || kubectl -n "$NS" create serviceaccount "$KSA"
kubectl -n "$NS" annotate serviceaccount "$KSA" \
  "iam.gke.io/gcp-service-account=${GSA}" --overwrite >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$GSA" --project "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NS}/${KSA}]" \
  --role="roles/iam.workloadIdentityUser" --quiet >/dev/null

STAMP="$(date +%s)"
CTX_OBJ="${BUCKET}/kaniko/ctx-${STAMP}.tar.gz"
TARBALL="$(mktemp -d)/ctx.tar.gz"
echo "==> [kaniko] uploading build context ${CONTEXT} -> ${CTX_OBJ}"
# Mirror .dockerignore's heavy hitters; kaniko unpacks the tarball as the context.
COPYFILE_DISABLE=1 tar -czf "$TARBALL" -C "$CONTEXT" \
  --exclude './.git' --exclude '*/.git' --exclude '*/.git/*' \
  --exclude './.venv' --exclude '*/.venv' --exclude '*/.venv/*' \
  --exclude '*/__pycache__' --exclude '*/__pycache__/*' \
  --exclude './.pytest_cache' --exclude './data' --exclude './logs' \
  --exclude './.env' --exclude './.claude' --exclude '.DS_Store' \
  .
gcloud storage cp "$TARBALL" "$CTX_OBJ" --project="$PROJECT_ID" >/dev/null
rm -rf "$(dirname "$TARBALL")"

JOB="kaniko-build-${STAMP}"
echo "==> [kaniko] running build Job ${NS}/${JOB} -> ${TAG}"
kubectl -n "$NS" apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB}
  labels: {app: kaniko-build}
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels: {app: kaniko-build}
    spec:
      serviceAccountName: ${KSA}
      restartPolicy: Never
      containers:
      - name: kaniko
        image: ${KANIKO_IMAGE}
        args:
        - --context=${CTX_OBJ}
        - --dockerfile=${DOCKERFILE}
        - --destination=${TAG}
        - --snapshot-mode=redo
        resources:
          requests: {cpu: "1", memory: 2Gi}
EOF

# Surface success/failure explicitly; stream the tail of the log either way.
if kubectl -n "$NS" wait --for=condition=complete "job/${JOB}" --timeout=900s; then
  kubectl -n "$NS" logs "job/${JOB}" --tail=3 || true
  kubectl -n "$NS" delete job "$JOB" --wait=false >/dev/null
  gcloud storage rm "$CTX_OBJ" >/dev/null 2>&1 || true
  echo "==> [kaniko] pushed ${TAG}"
else
  echo "!! [kaniko] build job failed; logs:"
  kubectl -n "$NS" logs "job/${JOB}" --tail=50 || true
  exit 1
fi
