# One-time cluster prerequisite — Agent Substrate core reconcile control plane

Run this **once per cluster**, before deploying the `substrate-basic` feature. It
installs only the **core reconcile control plane** — the `ate-controller`
Deployment, the `atelet` DaemonSet, the `ate.dev` CRDs, and the default gVisor
`SandboxConfig` — and builds+pushes the `ateom-gvisor` worker image the
`WorkerPool` references.

It is deliberately kept out of the Hub's automatic `cluster_dir` apply for two
reasons:

1. **It needs `ko`.** The substrate operator images are built from upstream Go
   source with [`ko`](https://ko.build) — upstream ships no Dockerfiles, so the
   images can't come from the Hub's plain `docker build` pipeline. The Hub's
   `cluster_dir` auto-apply only handles plain manifests.
2. **It is an operator-run bootstrap**, not a per-deploy manifest — same posture
   as the `sandbox-kata` Kata prerequisite.

The convenience script [`install-substrate-prereq.sh`](install-substrate-prereq.sh)
performs all of the steps below; export the env vars and run it, or copy the
commands by hand.

```bash
export PROJECT_NAME=<your-gcp-project>
export CLUSTER=<your-gke-cluster>
export REGION=<your-region>                 # e.g. us-central1
export ARTIFACT_REGISTRY_REPO=gke-showcase  # must match the feature's ateomImage repo
```

## Scope — CORE reconcile only, NO alpha agent-identity data plane

This install brings up **only** the declarative reconcile loop:

- **CRDs:** `workerpools`, `actortemplates`, `sandboxconfigs` (`ate.dev/v1alpha1`)
- **controller:** `deployment/ate-controller` — reconciles a `WorkerPool` into a
  worker `Deployment`
- **node agent:** `daemonset/atelet` — lays the gVisor `runsc` binary onto nodes
- **sandbox class:** the default gVisor `SandboxConfig` that `sandboxClass: gvisor`
  resolves to
- **worker image:** `ateom-gvisor:latest` pushed to your Artifact Registry

It **intentionally does NOT install** the alpha agent-identity data plane
(`ate-api-server`, `atenet`, `valkey`, `pod-certificate-controller`). Those
require the alpha `certificates.k8s.io/v1beta1` `ClusterTrustBundle` /
`PodCertificate` APIs, which are **not served on a plain GKE Standard cluster**,
and the core reconcile loop does not depend on them. This is why the demo runs on
a stock Standard cluster with no alpha API flags.

> **Why not upstream's `install-ate.sh --deploy-ate-system`?** That path forces
> the alpha data plane — it creates the apiserver JWT/CA/valkey secrets, applies
> `pod-certificate-controller.yaml`, and waits on the alpha `ClusterTrustBundle`
> resources before resolving the whole `manifests/ate-install` directory. On a
> Standard cluster it blocks. So this script applies the core components
> **individually** instead.

## 1. gVisor on GKE Standard — no special node pool needed

The reconciled worker runs its actor under gVisor via the `ateom-gvisor` worker,
which brings its own `runsc`; `atelet` lays the runtime onto the node. This means
the demo needs **no** `--sandbox type=gvisor` node pool and **no** nested
virtualization — a stock GKE Standard node pool is sufficient.

## 2. Install the core reconcile control plane

Export the env vars above and run:

```bash
bash install-substrate-prereq.sh
```

The script:

1. Gets cluster credentials and configures Docker auth for Artifact Registry.
2. Clones upstream `agent-substrate/substrate` (or reuses an existing checkout via
   `UPSTREAM_DIR=/path/to/substrate`).
3. `ko apply -f manifests/ate-install/generated` — applies the three `ate.dev`
   CRDs and waits for them to become `Established`.
4. Applies the `SandboxConfig` validation policy + the default gVisor
   `SandboxConfig`.
5. `ko apply` the `ate-controller` Deployment + `atelet` DaemonSet, and waits for
   both to roll out.
6. `ko build --base-import-paths --tags=latest --push ./cmd/ateom-gvisor` — builds
   and pushes the worker image to
   `${REGION}-docker.pkg.dev/${PROJECT_NAME}/${ARTIFACT_REGISTRY_REPO}/ateom-gvisor:latest`,
   which is exactly the ref the feature's `WorkerPool` `ateomImage` points at.

The image path **must** match the feature's `WorkerPool.ateomImage`, so
`ARTIFACT_REGISTRY_REPO` here must equal the value the Hub templates into
`infra/workerpool.yaml`.

## 3. Verify

```bash
# CRDs Established:
kubectl get crd workerpools.ate.dev actortemplates.ate.dev sandboxconfigs.ate.dev

# controller + node agent up:
kubectl rollout status deployment/ate-controller -n ate-system
kubectl rollout status daemonset/atelet         -n ate-system

# worker image present:
gcloud artifacts docker images list \
  "${REGION}-docker.pkg.dev/${PROJECT_NAME}/${ARTIFACT_REGISTRY_REPO}" \
  --include-tags --filter="package~ateom-gvisor"
```

Once the controller + atelet are rolled out and the `ateom-gvisor:latest` image
is present, deploy the `substrate-basic` feature from the Hub as usual. The Hub
applies the `WorkerPool` + `ActorTemplate` from `infra/`, the `ate-controller`
reconciles the `WorkerPool` into `substrate-basic-deployment`, and the playroom
renders the live desired-vs-reconciled state.

## Preflight

The script requires `gcloud`, `kubectl`, `ko`, and `git` on `PATH`. Installing
`ko`: <https://ko.build>.
