# One-time cluster prerequisite — Kata / MicroVM runtime

Run this **once per cluster**, before deploying the `sandbox-kata` feature. It is
deliberately kept out of the Hub's automatic `cluster_dir` apply because it
creates a node pool via `gcloud` and installs a cluster-wide DaemonSet into
`kube-system` — operator-run steps, not safe auto-applied plain manifests.

The convenience script [`install-kata-prereq.sh`](install-kata-prereq.sh) performs
all of the steps below; export the four env vars and run it, or copy the commands
by hand.

```bash
export PROJECT=<your-gcp-project>
export CLUSTER=<your-gke-cluster>
export REGION=<your-region>          # e.g. us-central1
export NODE_POOL=kata-microvm-pool
```

## 1. Nested-virtualization node pool

Kata Cloud Hypervisor MicroVMs require **nested virtualization**, which is not
available on E2 machine types — use an N2/N2D/C2/C3 shape. The pool autoscales
from **0** (no cost at rest) and is tainted so only Kata workloads land on it.

```bash
gcloud container node-pools create "$NODE_POOL" \
  --project "$PROJECT" --cluster "$CLUSTER" --region "$REGION" \
  --machine-type n2-standard-4 \
  --image-type COS_CONTAINERD \
  --enable-nested-virtualization \
  --node-labels nested-virtualization=enabled \
  --node-taints sandbox.gke.io/kata=true:NoSchedule \
  --enable-autoscaling --min-nodes 0 --max-nodes 3 --num-nodes 0
```

## 2. Install kata-deploy (registers the `kata-clh` RuntimeClass)

kata-deploy lays the Kata binaries onto the labeled nodes and creates the
RuntimeClasses. Pin a released chart version and select the Cloud Hypervisor
(`clh`) shim so the `kata-clh` RuntimeClass this feature references is created.

```bash
helm install kata-deploy \
  oci://ghcr.io/kata-containers/kata-deploy-charts/kata-deploy \
  --version 3.32.0 \
  --namespace kube-system \
  --set env.shims="clh"
```

## 3. Verify

```bash
# RuntimeClass present:
kubectl get runtimeclass kata-clh

# kata-deploy rolled out on the labeled nodes:
kubectl -n kube-system rollout status ds/kata-deploy
```

Once `kubectl get runtimeclass kata-clh` returns the class, deploy the
`sandbox-kata` feature from the Hub as usual.
