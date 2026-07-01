# GKE Agent Sandbox — Kata / MicroVM

A sibling of the `agent-sandbox` feature that keeps the exact same agent
control-plane shape and swaps the isolation boundary from **gVisor** (a
user-space kernel) to **Kata Containers running Cloud Hypervisor MicroVMs** (a
hardware-virtualization boundary — each sandbox pod gets its own lightweight VM
with its own guest kernel).

Both features drive the same `SandboxTemplate` / `SandboxWarmPool` /
`SandboxClaim` CRDs (`extensions.agents.x-k8s.io/v1alpha1`) and the same
runtime-agnostic sandbox-router, so the Hub playroom, the per-feature
`hub_router.py`, and the demo workload are identical. The only difference is
*where the sandbox pod runs*.

## What changed vs. `agent-sandbox`

The swap is localized to the SandboxTemplate pod spec (`infra/sandbox-template.yaml`):

| Field | `agent-sandbox` (gVisor) | `sandbox-kata` (Kata / MicroVM) |
|---|---|---|
| `runtimeClassName` | `gvisor` | `kata-clh` |
| `nodeSelector` | `sandbox.gke.io/runtime: gvisor` | `nested-virtualization: enabled` |
| toleration key | `sandbox.gke.io/runtime` (value `gvisor`) | `sandbox.gke.io/kata` (value `"true"`) |

Everything else is a mechanical rename to the `sandbox-kata` prefix (image names,
Service/Deployment/Gateway/Route/HealthCheckPolicy names, the `hub_router`
`FEATURE_NAME`, the frontend API prefix and UI labels) so the two features never
collide when both are loaded.

## Prerequisite — this is the one real cost of Kata

GKE's gVisor sandbox is **managed**: you create a node pool with
`--sandbox type=gvisor` and the `gvisor` RuntimeClass is there. Kata is **DIY** —
before you deploy this feature you must, **once per cluster**:

1. Create a **nested-virtualization** node pool (Kata MicroVMs need nested virt,
   which rules out E2 machine types), labeled `nested-virtualization=enabled` and
   tainted `sandbox.gke.io/kata=true:NoSchedule`.
2. Install **kata-deploy** cluster-wide, which lays down the Kata binaries on
   those nodes and registers the `kata-clh` (Cloud Hypervisor) RuntimeClass.

See [`cluster/README.md`](cluster/README.md) for the exact, copy-pasteable steps
(and [`cluster/install-kata-prereq.sh`](cluster/install-kata-prereq.sh) to run
them). This step is intentionally **not** wired into the Hub's `cluster_dir`
auto-apply: it creates a node pool via `gcloud` and mutates `kube-system`
cluster-wide, neither of which is a safe auto-applied plain manifest.

## Cost note

The nested-virt pool can autoscale to **0 nodes at rest**, so an idle cluster
carries no Kata cost; nodes spin up only when a warm-pool replica or a claim is
scheduled onto the Kata pool.
