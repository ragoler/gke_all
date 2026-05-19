#!/bin/bash

# Exit immediately if any command exits with a non-zero status.
set -e

echo "======================================================================"
echo " RESETTING GKE FEATURE SHOWCASE HUB TO PRISTINE DORMANT STATE"
echo "======================================================================"

# 1. Local / Mock mode reset
if [ -f data/showcase.db ]; then
  echo ">>> Resetting local SQLite mock database..."
  rm -f data/showcase.db
  echo "Local mock database deleted successfully."
fi

# 2. GKE Live mode reset
if kubectl get namespace gke-showcase-admin >/dev/null 2>&1; then
  echo ">>> Discovering and cleaning active GKE showcase namespaces..."
  
  # Delete standard showcase namespaces if they exist
  kubectl delete namespace gke-showcase-agent-sandbox --ignore-not-found --wait=false
  kubectl delete namespace gke-showcase-gpu-inference --ignore-not-found --wait=false
  
  # Delete any custom namespaces tracked by Gateway API or Sandbox
  for ns in $(kubectl get ns -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep -E '^agent-|^gpu-|^showcase-|^gke-showcase-|^inference-|^my-test-' || true); do
    if [ "$ns" != "gke-showcase-admin" ]; then
      echo ">>> Deleting custom showcase namespace: $ns"
      kubectl delete namespace "$ns" --ignore-not-found --wait=false
    fi
  done
  
  echo ">>> Resetting persistent GKE SQLite database on PVC..."
  kubectl exec deployment/showcase-admin-deployment -n gke-showcase-admin -- rm -f /data/showcase.db || echo "No active database found on PVC."
  
  echo ">>> Restarting Admin Hub pod to re-initialize pristine database schema..."
  kubectl rollout restart deployment showcase-admin-deployment -n gke-showcase-admin
  kubectl rollout status deployment showcase-admin-deployment -n gke-showcase-admin --timeout=90s
fi

echo "======================================================================"
echo " Showcase Hub successfully reset to a clean, dormant state!"
echo "======================================================================"
