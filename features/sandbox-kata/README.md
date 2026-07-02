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

---

## Why GKE, why agent-sandbox, why Kata + MicroVM

If you are new to running agent workloads in sandboxes, here is the short version
of the three decisions this feature makes, and why.

**Why GKE.** Agents generate and run untrusted code at machine speed, so the
sandbox layer has to be something you *operate*, not something you hand-roll. GKE
gives you the two ingredients the sandbox layer needs out of the box: a managed
Kubernetes control plane to schedule and reconcile sandbox pods, and node-level
isolation runtimes (gVisor as a managed add-on; Kata via a nested-virtualization
node pool). You get autoscaling, per-node pools with distinct isolation
guarantees, and Workload Identity so the code inside a sandbox can call Google
Cloud APIs (e.g. Vertex AI) with a scoped identity instead of a static key.

**Why agent-sandbox.** [`agent-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox)
(a `kubernetes-sigs` project) turns "give me an isolated place to run this agent's
code" into a declarative Kubernetes API. You create a `SandboxClaim`, the
controller binds it to a pre-warmed sandbox pod, and you talk to a stable
per-claim endpoint — no per-request pod plumbing in your app. Because it is a
CRD + controller, warm pools, claim lifecycle, and the routing layer are all
things Kubernetes reconciles for you. Your application code never touches the
Kubernetes API directly; it calls the sandbox-router.

**Why Kata + MicroVM instead of gVisor.** Both gVisor and Kata isolate a sandbox
from the host, but at different boundaries:

| | gVisor | Kata + Cloud Hypervisor MicroVM |
|---|---|---|
| Isolation boundary | User-space kernel intercepts syscalls | Hardware-virtualized VM with its own guest kernel |
| Blast radius of a kernel exploit | Contained in the gVisor sentry (still one host kernel) | Contained in a separate guest kernel + VM boundary |
| Syscall compatibility | Some syscalls emulated/limited | Full Linux kernel in the guest — highest compatibility |
| Cold-start / overhead | Lower (no VM) | Slightly higher (a MicroVM boots), amortized by the warm pool |
| Managed on GKE? | Yes (`--sandbox type=gvisor`) | DIY: nested-virt node pool + kata-deploy |

Choose **gVisor** when you want the lightest managed isolation and your workloads
tolerate its syscall surface — it is the right default for most agent code.
Choose **Kata + MicroVM** when you are running *highly sensitive or untrusted*
code and want a hardware-virtualization boundary and a full, independent guest
kernel — at the cost of running (and paying for) a nested-virtualization node
pool. This feature exists so you can A/B the exact same agent workload across
both boundaries and decide with your own numbers.

---

## What changed vs. the upstream `kata-gke-sandbox` example

Upstream ships a minimal Kata walkthrough at
[`examples/kata-gke-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox/tree/main/examples/kata-gke-sandbox).
It is the right place to start to prove Kata works on your cluster: it creates a
single `Sandbox` object whose pod runs an inline `busybox` command, and you
confirm isolation by `kubectl exec`-ing in and checking that the pod's kernel
version differs from the host node's.

This feature keeps upstream's isolation mechanism and layers a **real,
API-driven agent workload** on top of it. The deltas:

| Aspect | Upstream `kata-gke-sandbox` example | This `sandbox-kata` feature |
|---|---|---|
| Hypervisor / RuntimeClass | `kata-qemu` (QEMU) | `kata-clh` (Cloud Hypervisor — lighter, faster-booting MicroVM) |
| API shape | A single raw `Sandbox` CR (`agents.x-k8s.io/v1beta1`) | `SandboxTemplate` + `SandboxWarmPool` + `SandboxClaim` (`extensions.agents.x-k8s.io/v1alpha1`) driven through the sandbox-router |
| Node targeting | `nodeSelector: cloud.google.com/gke-os-distribution: ubuntu` | `nodeSelector: nested-virtualization: enabled` + toleration `sandbox.gke.io/kata="true"` on a dedicated tainted pool |
| Warm pool | None (one pod, created on demand) | Yes — claims bind to pre-warmed MicroVMs, so acquisition is fast |
| Workload | Inline `busybox` echo/sleep | A FastAPI demo app running **inside** the MicroVM, reachable over HTTP through the router |
| How you send work | `kubectl exec` into the pod | `POST /api/features/sandbox-kata/sandboxes/{claim_id}/message` (or `/quote`) from the Hub UI or `curl` |
| Isolation swap vs. gVisor sibling | n/a (Kata-only example) | Localized to the SandboxTemplate pod spec (see below) — everything else is identical to the gVisor feature |

The isolation swap relative to the **gVisor** sibling feature is localized to the
`SandboxTemplate` pod spec (`infra/sandbox-template.yaml`):

| Field | `agent-sandbox` (gVisor) | `sandbox-kata` (Kata / MicroVM) |
|---|---|---|
| `runtimeClassName` | `gvisor` | `kata-clh` |
| `nodeSelector` | `sandbox.gke.io/runtime: gvisor` | `nested-virtualization: enabled` |
| toleration key | `sandbox.gke.io/runtime` (value `gvisor`) | `sandbox.gke.io/kata` (value `"true"`) |

Everything else is a mechanical rename to the `sandbox-kata` prefix (image names,
Service/Deployment/Gateway/Route/HealthCheckPolicy names, the `hub_router`
`FEATURE_NAME`, the frontend API prefix and UI labels) so the two features never
collide when both are loaded.

---

## How code reaches the sandbox and executes there (evidence it works)

The upstream example proves *isolation*; this feature proves *the full agent
loop* — sending work in and getting a result back over a stable API. The path
from a click in the Hub UI to code executing inside a MicroVM:

1. **Claim a sandbox.** The Hub UI (or `curl`) calls
   `POST /api/features/sandbox-kata/sandboxes`. `hub_router.py` creates a
   `SandboxClaim` CR (`k8s_client.create_sandbox_claim`) with a generated id like
   `sb-1a2b3c4d`. The agent-sandbox controller binds that claim to a pre-warmed
   Kata MicroVM pod from the `SandboxWarmPool` and reports a per-claim endpoint in
   the claim status.

2. **Send a prompt.** The UI calls
   `POST /api/features/sandbox-kata/sandboxes/{claim_id}/message` with
   `{"message": "..."}`. `hub_router.py` routes it through
   `k8s_client.message_sandbox_claim`, which resolves the bound MicroVM from the
   claim and forwards an HTTP `POST /message` to the demo app **inside** the VM,
   stamping an `X-Sandbox-Id` header.

3. **Execute inside the MicroVM.** The demo app (`demo-app/main.py`, a FastAPI
   server) handles `/message` and echoes `"[{x_sandbox_id}] {message}"`. The
   returned sandbox id in the reply is your proof the request executed inside the
   specific claimed VM, not on the host or the router.

4. **Do real model work inside the MicroVM.** `POST .../sandboxes/{claim_id}/quote`
   drives the demo app's `/quote` endpoint, which calls a model **from inside the
   sandbox** — either Vertex AI Gemini (`gemini-2.5-flash`, authenticated via
   Workload Identity, no static key) or, when `provider=vllm`, a self-hosted vLLM
   endpoint over HTTP. This demonstrates the sandboxed workload reaching out to
   inference with a scoped cloud identity, which is the realistic shape of an
   agent tool call.

5. **Release.** `DELETE /api/features/sandbox-kata/sandboxes/{claim_id}` tears the
   claim down; the warm pool replenishes.

### Confirm the isolation is real (kernel-version check)

Because a Kata sandbox runs its own guest kernel, the fastest hard proof is a
kernel-version diff between the host node and the sandbox pod (the same check
upstream uses):

```shell
# Host node kernel (the nested-virt Ubuntu pool):
kubectl get nodes -o wide      # note KERNEL-VERSION, e.g. 6.8.0-*-gke

# Sandbox pod kernel (inside the MicroVM):
POD=$(kubectl get pods -n <sandbox-kata-namespace> \
  -l app=sandbox-worker -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n <sandbox-kata-namespace> "$POD" -- uname -r
```

A **different** kernel version inside the pod means the workload is running in its
own MicroVM with its own kernel — hardware-virtualized isolation is active. An
identical version means the Kata runtime is not being used and you are back on the
host kernel.

---

## Prerequisite — this is the one real cost of Kata

GKE's gVisor sandbox is **managed**: you create a node pool with
`--sandbox type=gvisor` and the `gvisor` RuntimeClass is there. Kata is **DIY** —
before you deploy this feature you must, **once per cluster**:

1. Create a **nested-virtualization** node pool (Kata MicroVMs need nested virt,
   which rules out E2 machine types — use Intel N2), labeled
   `nested-virtualization=enabled` and tainted
   `sandbox.gke.io/kata=true:NoSchedule`.
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
