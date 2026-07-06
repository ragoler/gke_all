# Agent Substrate — WorkerPool / Actor reconcile (core)

A live, read-only Hub playroom for the **Agent Substrate** declarative reconcile
loop. A `WorkerPool` custom resource declares the desired fleet of sandboxed
agent workers; the `ate-controller` drives a worker `Deployment` to that desired
state. An `ActorTemplate` declares the actor workload those workers run. The
playroom shows desired state (the `WorkerPool` CR) next to reconciled state (the
controller-created `Deployment`), polling every 5s. It observes only — it mutates
nothing.

## Scope — core reconcile only

This feature demonstrates the **core** substrate reconcile chain on a plain GKE
Standard cluster:

- **`WorkerPool`** (`ate.dev/v1alpha1`) — desired replica count + `sandboxClass`
  + `ateomImage`.
- **`ate-controller`** — reconciles the `WorkerPool` into a `Deployment` named
  `<workerpool>-deployment` (here `substrate-basic-deployment`, which is the
  feature's `deployment_name`, so the Hub's readiness poll *is* the reconcile
  signal).
- **`ActorTemplate`** (`ate.dev/v1alpha1`) — the actor workload (a public
  `pause` + `busybox` idler here) bound to the pool's workers by `workerSelector`.
- **gVisor isolation** — `sandboxClass: gvisor` resolves to the cluster's default
  `SandboxConfig`; the `ateom-gvisor` worker brings its own `runsc`, so no special
  sandbox node pool is required (see below).

It **deliberately excludes** the alpha **agent-identity data plane**
(`ate-api-server`, `atenet`, `valkey`, `pod-certificate-controller`), which needs
alpha `certificates.k8s.io/v1beta1` APIs (`ClusterTrustBundle` / `PodCertificate`)
that a Standard cluster does not serve. The core reconcile loop does not depend on
them, which is what lets this demo run on a stock Standard cluster.

## gVisor on GKE Standard — no special node pool

Unlike the `sandbox-kata` feature (which needs a nested-virtualization node pool),
this feature's isolation comes from the `ateom-gvisor` worker + `atelet` node
agent, which lay down and run `runsc` themselves. A stock GKE Standard node pool
is sufficient — no `--sandbox type=gvisor` pool, no nested virt, no `/dev/kvm`.

## Prerequisite — one-time operator install (needs `ko`)

The substrate operator images are built from upstream Go source with
[`ko`](https://ko.build) (upstream ships no Dockerfiles), so the operator install
is a **one-time, operator-run** step — not part of the Hub's `docker build`
pipeline and not wired into the `cluster_dir` auto-apply. Before deploying this
feature, run the core-install prerequisite once per cluster:

See [`cluster/README.md`](cluster/README.md) for the exact steps and
[`cluster/install-substrate-prereq.sh`](cluster/install-substrate-prereq.sh) to
run them. It installs the CRDs + `ate-controller` + `atelet` + default gVisor
`SandboxConfig`, and builds+pushes the `ateom-gvisor:latest` worker image the
`WorkerPool` references.

## What the Hub applies

Once the prerequisite is in place, deploying the feature from the Hub applies the
two `ate.dev` custom resources from `infra/` (`WorkerPool` + `ActorTemplate`,
`${VAR}`-templated with `NAMESPACE` / `PROJECT_NAME` / `REGION` /
`ARTIFACT_REGISTRY_REPO`). The `ate-controller` reconciles the `WorkerPool` into
`substrate-basic-deployment`; the per-feature `hub_router.py` reads the CRs + the
reconciled `Deployment` (read-only) and the playroom renders the live
desired-vs-reconciled state.

## Cost note

The core control plane (`ate-controller` Deployment + `atelet` DaemonSet) plus the
reconciled worker `Deployment` are lightweight and run on the cluster's existing
Standard node pool — no dedicated or nested-virt pool, so no incremental node cost
beyond the reconciled workers themselves.
