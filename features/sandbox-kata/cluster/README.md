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

### Pre-warming for a live demo / screenshots

The pool above scales from **0**, so the *first* Kata sandbox request cold-starts
a node — a multi-minute wait the first time you click the tile. For a live UI
walkthrough or screenshots, pre-warm one always-on node so the first click is
instant. The script accepts `MIN_NODES` / `NUM_NODES` overrides (both default
`0`, preserving scale-to-zero):

```bash
MIN_NODES=1 NUM_NODES=1 bash install-kata-prereq.sh
```

Scale the pool back to zero after the demo to drop the idle node cost.

## 2. Install kata-deploy (registers the `kata-clh` RuntimeClass)

kata-deploy lays the Kata binaries onto the labeled nodes and creates the
RuntimeClasses. **No Helm required** — the DaemonSet + RBAC manifests are vendored
under [`kata-deploy/`](kata-deploy/), pinned to kata **3.20.0** (the last release
that ships plain kustomize manifests; 3.28+ moved kata-deploy to a Helm chart only).
The vendored DaemonSet is edited to install only the Cloud Hypervisor (`clh`) shim,
so the `kata-clh` RuntimeClass this feature references is the one created.

```bash
kubectl apply -f kata-deploy/kata-rbac.yaml
kubectl apply -f kata-deploy/kata-deploy.yaml
```

To bump the kata version, re-download the two files from the kata-containers repo
at a tag that still carries `tools/packaging/kata-deploy/{kata-rbac,kata-deploy}/base/`,
then re-apply `SHIMS: "clh"` / `DEFAULT_SHIM: "clh"` and pin the DaemonSet image tag.

## 3. Verify

```bash
# RuntimeClass present:
kubectl get runtimeclass kata-clh

# kata-deploy rolled out on the labeled nodes:
kubectl -n kube-system rollout status ds/kata-deploy
```

Once `kubectl get runtimeclass kata-clh` returns the class, deploy the
`sandbox-kata` feature from the Hub as usual.
