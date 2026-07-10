# Authoring a Showcase Feature (Standalone Repo + Hub Plugin)

This document is the **feature contract** for the GKE Feature Showcase Hub. Every
showcase feature — whether it lives inside this repo or in its own — satisfies the
same contract: a directory under `features/<name>/` containing a `feature.yaml`
descriptor. The Hub discovers features by scanning `features/*/feature.yaml` and is
**indifferent to how that directory got there.**

## Two kinds of features

| | **Local feature** | **External feature** |
|---|---|---|
| Lives | directly in this repo under `features/<name>/` | in its own git repo, mounted as a **git submodule** at `features/<name>/` |
| Tracked by | the Hub's own git history | a `.gitmodules` entry + a pinned commit |
| Updated by | editing files in place + normal commits | committing in the feature repo, then bumping the submodule pointer |
| Examples | `agent-sandbox`, `gpu-inference` | `inference-gateway` (from `ragoler/inference_gateway`) |
| Must run standalone? | no — it only ever runs inside the Hub | **yes** — its own README, `.env`, infra scripts, CI |

Both kinds expose an identical `feature.yaml` and identical directory conventions, so
the Hub loader, build pipeline, deploy/teardown, playroom, and telemetry treat them
the same. The flavor only changes the **authoring + update workflow** (§8), never the
runtime wiring.

> **Why a contract?** Historically, adding a feature meant editing hardcoded maps in
> `showcase_admin/app/main.py`, `k8s_client.py`, and `scripts/build_and_push.sh`. The
> Hub is moving to **manifest-driven discovery**: it scans `features/*/feature.yaml`
> and derives everything from the descriptor. Author to this contract — local or
> external — and you never touch Hub core code to add a feature.

---

## 1. Repository layout

Your standalone repo must contain at least this (extra files for standalone operation
are fine and ignored by the Hub):

```
<your-feature-repo>/
├── feature.yaml            # REQUIRED — the Hub descriptor (see §2)
├── README.md               # standalone usage
├── infra/                  # REQUIRED — per-namespace K8s manifests (templated)
│   ├── gateway.yaml        #   dedicated Gateway (decentralized; own external IP)
│   ├── http-route.yaml     #   HTTPRoute -> your Service
│   ├── deployment.yaml     #   your workload Deployment(s)
│   └── service.yaml        #   ClusterIP Service the route targets
├── cluster/                # OPTIONAL — cluster-scoped prerequisites (see §5)
│   └── compute-class.yaml
├── app/                    # OPTIONAL — container source if you build an image
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── frontend/               # OPTIONAL — standalone playroom UI
│   ├── index.html
│   ├── style.css
│   └── app.js
├── hub_router.py           # OPTIONAL — this feature's own data-plane API router (§6a)
│
│   # --- Standalone operation (Hub IGNORES all of these) — see §7a ---------
├── .env.example            # standalone config template (cp .env.example .env)
├── .env                    # local config (gitignored), sourced by the scripts
├── setup_infra.sh          # create the GKE CLUSTER + cluster-scoped prereqs
├── deploy_app.sh           # build/push image + deploy per-namespace infra
└── verify_setup.sh         # post-deploy readiness + smoke test
```

> **External features must run standalone** (§ table above), and that is what the
> `.env` + script trio is for. A **local** feature only ever runs inside the Hub,
> so it can skip them. The Hub never reads `.env` or runs these scripts — it has
> its own equivalents (see §7a). They exist so the repo also stands alone.

The Hub never assumes fixed paths beyond `feature.yaml`; the descriptor's `paths:`
block tells it where your `infra/`, `frontend/`, and build contexts actually live, so
you can keep whatever layout your standalone repo already uses (e.g. UI under
`app/static/`).

---

## 2. `feature.yaml` — the descriptor

This is the single source of truth the Hub reads. Schema:

```yaml
# Identity (shown on the Hub dashboard card)
name: my-feature                 # kebab-case; also the default namespace suffix
title: My GKE Feature
description: One-sentence value proposition shown on the card.
gke_features:                    # bullet chips on the card
  - "ComputeClass GPU sharing"
  - "Gateway API L7 routing"

# Where things live in THIS repo (relative paths)
paths:
  infra_dir: infra               # per-namespace manifests applied on deploy
  # OR, if your manifests span several dirs (keep your own layout), use a list instead
  # of infra_dir — all are applied in order:
  # infra_dirs: [infra, k8s]
  cluster_dir: cluster           # OPTIONAL cluster-scoped prereqs (see §5)
  frontend_dir: frontend         # served as the playroom UI; omit if no UI
  playroom_slug: my-feature      # Hub serves the UI at /my-feature/

# Lifecycle wiring
deployment_name: my-feature-deployment   # Deployment the Hub polls for readiness
gateway:
  name: my-feature-gateway       # metadata.name of your Gateway resource
  class: gke-l7-gxlb             # or gke-l7-rilb (internal), etc.

# UI integration — choose ONE model (see §2a):
#  (a) Hub-hosted playroom: set paths.frontend_dir + paths.playroom_slug (+ usually
#      hub_router). The Hub mirrors your UI and serves it at /<slug>/.
#  (b) Link-out: set entrypoint_service to a LoadBalancer Service name. The Hub's
#      "Feature dashboard ↗" links straight to that Service's external IP (new tab); the
#      feature serves its own UI + API. No frontend_dir/playroom_slug/hub_router.
entrypoint_service: my-feature-svc   # link-out only; omit for hub-hosted playroom

# Container images the Hub build pipeline should produce (omit if you use only
# public/prebuilt images)
build:
  - image: my-feature-app        # -> ${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/my-feature-app
    context: app                 # docker build context
    dockerfile: app/Dockerfile

# Template variables your manifests reference (see §3). The Hub guarantees the
# standard set; declare any extra ones here so the descriptor is self-documenting.
template_vars:
  - NAMESPACE
  - PROJECT_NAME
  - REGION
  - ARTIFACT_REGISTRY_REPO

# Default values for any variables the Hub does NOT supply (e.g. an external demo's
# own GATEWAY_NAME / REPLICAS / MODEL_NAME). These fill in at deploy time; Hub standard
# variables (NAMESPACE, PROJECT_NAME, …) always take precedence over them. Values may
# themselves reference other variables — they resolve to a fixed point, so you can keep
# an existing image ref like ${REGISTRY}/app:${IMAGE_TAG} unchanged and define REGISTRY
# here in terms of the Hub's REGION/PROJECT_NAME/ARTIFACT_REGISTRY_REPO.
template_defaults:
  GATEWAY_NAME: my-feature-gateway
  REPLICAS: "2"
  REGISTRY: "${REGION}-docker.pkg.dev/${PROJECT_NAME}/${ARTIFACT_REGISTRY_REPO}"
  IMAGE_TAG: latest

# This feature's own data-plane router (its independent "proxy"). The Hub imports
# "<module>:<attr>" from this directory and mounts the FastAPI APIRouter under
# /api/features/<name>. Each feature owns its router, so its API is fully isolated
# from other features and needs zero edits to Hub core. Omit if the feature has no
# backend API (UI-only).
hub_router: "hub_router:router"
```

Keep it declarative. If you find yourself wanting the Hub to special-case your
feature, that's a sign the descriptor schema should grow a field instead — raise it.

> **Every `${VAR}` your manifests reference MUST be either a Hub-standard variable (§3)
> or declared in `template_defaults`.** Anything undeclared is left as the literal text
> `${VAR}` and your apply fails (or silently mis-configures). After authoring, grep your
> manifests for `\${[A-Z_]+}` and confirm each one is covered.

---

## 2a. Two UI integration models

A feature surfaces its UI in exactly one of two ways. Pick based on whether the Hub
should host the UI or just link to it.

| | **Hub-hosted playroom** | **Link-out** |
|---|---|---|
| Declares | `paths.frontend_dir` + `paths.playroom_slug` (+ usually `hub_router`) | `entrypoint_service: <LoadBalancer Service name>` |
| UI served by | the Hub (mirrors your static UI, serves at `/<slug>/`) | the feature itself, at its own external LoadBalancer |
| Data-plane API | your `hub_router` mounted at `/api/features/<name>` (behind the Hub JWT) | the feature's own app at its own IP (CORS) |
| "Feature dashboard" link | internal Hub path (same tab) | the Service's external IP (opens in a **new tab**) |
| Examples | `agent-sandbox`, `gpu-inference` | `inference-gateway` |
| Best for | light playrooms whose API the Hub can front | self-contained apps (their own richer UI/API/streaming) |

Don't mix them: a link-out feature has no `frontend_dir`/`playroom_slug`/`hub_router`; a
hub-hosted feature has no `entrypoint_service`. The Hub resolves the link-out address from
the `entrypoint_service` Service once its LoadBalancer gets an external IP (it re-resolves
on later polls, so a slow LB doesn't leave a dead link).

---

## 3. Infra manifests (`infra/`)

Manifests are plain Kubernetes YAML with `${VAR}` placeholders. On deploy the Hub
creates the target namespace, expands variables, and applies every `*.yaml` in each
declared dir (`infra_dir`, or every dir in `infra_dirs` in order), sorted by filename.
On teardown it deletes the whole namespace.

**Variables the Hub always provides:**

| Variable | Meaning |
|---|---|
| `${NAMESPACE}` | the namespace this instance deploys into — put it on every resource's `metadata.namespace` |
| `${PROJECT_NAME}` | GCP project id |
| `${REGION}` | GCP region |
| `${ARTIFACT_REGISTRY_REPO}` | Artifact Registry repo name |
| `${GOOGLE_GENAI_USE_VERTEXAI}` | `TRUE`/`FALSE` for Vertex vs API-key model access |
| `${OPENAI_API_BASE}` | resolved endpoint of a co-deployed model service (soft dependency injection) |
| `${GCS_MODEL_BUCKET}` | model weights bucket |

**Rules that keep features isolated and Hub-friendly:**

- **Be namespace-portable — never hardcode `default`.** The Hub deploys each feature into
  its own namespace (`gke-showcase-<name>`), not `default`. A demo authored to run
  standalone in `default` *will* break under the Hub unless every namespace reference is
  `${NAMESPACE}` (or resolved at runtime). The Hub helps with two of these automatically:
  it rewrites each manifest's `metadata.namespace` **and** rewrites `ServiceAccount`
  subjects in `RoleBinding`/`ClusterRoleBinding` to the deploy namespace. But it can NOT
  fix references it doesn't understand — you must handle these yourself:
    - **Container args / env** that name a namespace (e.g. an EPP `--pool-namespace`, a
      cross-namespace Service host) → use `${NAMESPACE}`.
    - **App code** that needs its own namespace → read it at runtime from the downward API
      (`env: POD_NAMESPACE → fieldRef: metadata.namespace`), never assume `default`.
    - **Cross-resource refs** in spec fields (a `parentRef`/`backendRef`/`poolRef` that
      points at another namespace) → `${NAMESPACE}`, or omit namespace for same-namespace.
  Keep standalone working by defaulting `NAMESPACE=default` in your own `setup_infra.sh`
  (so `${NAMESPACE}` still renders) — that's exactly how `inference-gateway` does both.
- **RBAC is fine to ship.** Features may include their own `ServiceAccount`, `Role`,
  `RoleBinding`, `ClusterRole`, `ClusterRoleBinding`; the Hub applies them (and the admin
  SA has `bind`/`escalate`, so a feature can grant its workload permissions). Bindings'
  `ServiceAccount` subjects are namespace-rewritten for you (see above) — but still author
  them portably so standalone works too.
- **Decentralized gateway.** Ship your own `Gateway` + `HTTPRoute`; never share the
  admin gateway. Its `metadata.name` must match `gateway.name` in `feature.yaml`.
- **Stable Service name.** The `HTTPRoute` backend and the `Service` your `hub_router`
  forwards to must be consistent.
- **Readiness.** Name your primary `Deployment` exactly `deployment_name`; the Hub
  polls it (`ready_replicas == replicas`) to flip the card to `ACTIVE`.
- **Pin model identifiers consistently.** If you call an OpenAI-compatible model
  server, the `model` field your client sends must equal the server's
  `--served-model-name`. (A mismatch here is exactly what broke the agent-sandbox
  vLLM quote path — `codegemma-7b-it` vs the full `gs://…` served name.)
- **No image `:latest` drift across clusters** where avoidable; tag per cluster if
  your standalone repo already does.
- **Never ship a `Namespace` object in `infra/`.** The Hub creates and owns the deploy
  namespace; a cluster-scoped `Namespace` pushed through the per-deploy *namespaced*
  apply path 404s and **aborts the whole deploy** (this stranded Kueue with no
  ServiceAccount → "No pods active"). Need to select your namespace from a
  webhook/policy? Match the built-in `kubernetes.io/metadata.name` label every
  namespace already carries — don't apply your own labeled `Namespace`.
- **Mind apply order — ship RBAC *before* the workload.** `infra/*.yaml` is applied
  **sorted by filename, all-or-nothing**. If your Deployment references a
  `ServiceAccount` you ship, name the RBAC file so it sorts first (e.g. `00-rbac.yaml`);
  otherwise the pods can be rejected (`serviceaccount … not found`) if anything later in
  the apply fails before your RBAC runs.
- **Cluster-scoped CRs may live in `infra/`.** The Hub applies a namespaced CR and, on a
  404/405 (the kind has no namespaced endpoint), retries it at **cluster scope** — so you
  can ship cluster-scoped CRDs (e.g. Kueue's `ClusterQueue`/`ResourceFlavor`/
  `WorkloadPriorityClass`) in `infra/` when they must be applied *after* their operator is
  running, rather than at bootstrap in `cluster/`. (Operators themselves still go in
  `cluster/` per §5.)

---

## 3a. Readiness: a green card ≠ a reachable data plane

The Hub flips a feature's card to **ACTIVE** as soon as its `deployment_name` reports
`ready_replicas == replicas`. But a **hub-hosted playroom's browser talks to the
feature's own Gateway IP directly** (the Hub does not proxy the data plane), and a
global external `Gateway`'s load balancer is **`Programmed` minutes *after* the
Deployment is ready**. So a user can open the playroom and click before the data path
serves traffic — the symptom is a raw **`Failed to fetch`** even though the card is
green. (This is exactly what JobSet hit on its first Hub deploy.)

Two things keep this smooth — do both:

- **The Hub side (already handled):** `k8s_client.get_gateway_ip` only returns an
  address once the Gateway reports `Programmed=True`; otherwise it returns `""`. So
  `/config` never hands the browser a not-yet-serving IP (and never the old dead
  `127.0.0.1` fallback).
- **Your playroom side (you must do this):** treat "LIVE but no gateway IP yet" as a
  first-class state. After resolving the IP, probe `GET <gateway>/healthz`; until it
  succeeds, **disable the controls and show "provisioning the load balancer (a few
  minutes)…"**, and keep polling. Never fall back to the Hub origin for data-plane
  calls (your `hub_router` doesn't serve them — you'd get a 404), and never surface a
  bare fetch error. This mirrors what `verify_setup.sh` already does standalone.

> **Status advances only when the dashboard is fetched.** The card's status is
> re-evaluated by a background task fired from the `/api/showcases` request, not by a
> continuous server-side poller. So a feature that becomes Ready *after* its deploy
> window (e.g. a vLLM pod that takes minutes to load weights, or a Spot-reclaim
> recovery) can sit at `PROVISIONING`/`REPROVISIONING` in the UI until the dashboard is
> reloaded — a refresh promotes it to `ACTIVE`. Don't mistake a stale card for a stuck
> deploy; check the actual Deployment readiness first.

---

## 4. App container (`app/`), if any

- Listen on a single HTTP port; expose `GET /healthz` returning `{"status":"ok"}` so
  Gateway/HealthCheckPolicy probes pass.
- **CORS is mandatory.** Browsers call your feature's external Gateway IP directly
  (the Hub does not proxy data-plane traffic), so add permissive CORS
  (`Access-Control-Allow-Origin: *`, methods `GET, POST, DELETE, OPTIONS`).
- Log errors with context (`logger.error(..., exc_info=True)`); never swallow a model
  call failure silently — surface a clear status string or non-200 so the UI can show
  the real reason rather than a blank "not working."
- Keep secrets out of the image; read from env / mounted `Secret` (optional refs are
  fine, as the sandbox demo does with `gemini-api-key`).

---

## 5. Cluster-scoped prerequisites (`cluster/`) — important for GPU/llm-d demos

Some features need resources that exist **once per cluster**, not per namespace:
GPU `ComputeClass` definitions, CRD installs (e.g. InferencePool), proxy-only subnets,
GPU time-sharing config. These cannot be created inside a per-deploy namespace.

Put them in `cluster_dir`. The Hub applies them at **cluster bootstrap**
(`build_infra.sh`), not on every feature deploy. Declare them in `feature.yaml` via
`paths.cluster_dir`. If your demo's standalone `setup_infra.sh` provisions these, mirror
the same YAML into `cluster/` so the Hub path stays IaC and reproducible.

`cluster_dir` supports two forms, applied at bootstrap. **It looks only at the top level
of `cluster_dir`** — a `kustomization.yaml` in a *subdirectory* is NOT discovered:
- **Plain manifests** — every top-level `*.yaml` is variable-expanded and `kubectl apply`-ed.
- **A kustomize dir** — if `cluster_dir` *itself* contains a top-level `kustomization.yaml`,
  the Hub runs `kubectl apply --server-side -k` on it (server-side because large upstream
  **CRD bundles** exceed the 256KB client-side annotation limit). This is how to install a
  CRD bundle: e.g. `inference-gateway`'s `cluster/kustomization.yaml` pulls the
  gateway-api-inference-extension CRDs (`resources: [https://github.com/.../config/crd?ref=vX]`),
  and `ray`'s `cluster/kustomization.yaml` composes the KubeRay operator bundle, its
  `ray-system` Namespace, and the Spot ComputeClass into one apply. If your bundle needs a
  dedicated namespace (KubeRay's operator lives in `ray-system`), **include the `Namespace`
  as a kustomize resource** — `apply -k` does not create it for you, and `kubectl` orders
  Namespaces first so the namespaced resources land correctly.

> **New CRD kinds need an RBAC grant — the one sanctioned Hub-core edit.** The Hub's admin
> ServiceAccount applies your manifests through a curated ClusterRole
> (`showcase-admin-role` in `infra/main-app.yaml`). If your feature introduces a Kubernetes
> resource kind no existing feature uses (a CRD like `RayCluster`, or `PodMonitoring`), the
> SA cannot create it and **the deploy 403s and aborts mid-apply** — leaving a half-built
> namespace (this is exactly what broke `ray`'s first deploy). Add an `apiGroups`/`resources`
> rule for the new kind to that ClusterRole. This is in-cluster **Kubernetes RBAC, not GCP
> IAM** — no `gcloud ... add-iam-policy-binding` is involved.

Note: the Hub also routes a `ComputeClass` found in a per-namespace `infra_dir` to the
cluster-scoped API automatically, so a demo that keeps its ComputeClass alongside its
other manifests still works without a separate `cluster_dir`. Put genuinely cluster-once
resources (CRD bundles especially) in `cluster_dir` so a fresh `build_infra.sh` installs
them — don't rely on a demo's standalone `setup_infra.sh` having run.

> This is the one structural gap between a typical standalone demo (which provisions
> cluster + namespace together in `setup_infra.sh`) and a Hub feature (which assumes a
> live cluster and only owns its namespace). Splitting prereqs out is what makes a
> heavy demo like `inference_gateway` mount cleanly.

---

## 5a. Admission webhooks — scope them, or you take down the whole Hub

Some operators (Kueue, Istio, Gatekeeper, cert-manager) install **cluster-scoped
admission webhooks** with `failurePolicy: Fail`. On a *shared* Hub this is the single
most dangerous thing a feature can bring in, and it bit the Kueue integration **twice**:

1. **It couples the entire Hub to your operator's uptime.** Kueue v0.18 ships
   mutating/validating webhooks on `deployments`, `pods`, `statefulsets`, `jobs`,
   `jobsets`, `rayclusters`, … matching *every* namespace. With `failurePolicy: Fail`,
   while the Kueue controller was still starting, **nothing in the cluster could create
   a Deployment or Pod** — `build_infra.sh` died applying the admin Deployment with
   `no endpoints available for service "kueue-webhook-service"`.
2. **Those webhooks intercept other features' resources — and your own infra.** They
   gate the JobSet/Ray features' CRs, and once you opt your namespace in, they gate
   your *own* controller Deployment's pods → Kueue rejected the kueue controller's pods
   and the deploy reported **"No pods active in namespace …"**.

**Rules:**
- Install the operator from `cluster/`, but **patch its webhook configurations down to
  only what you manage.** With a kustomize strategic-merge patch on the upstream
  `MutatingWebhookConfiguration`/`ValidatingWebhookConfiguration`: `$patch: delete`
  every webhook for a kind you don't own, and set a `namespaceSelector` (a label you
  put on your *own* namespace) on the ones you keep. Kueue is the reference — it keeps
  only `mjob`/`vjob` scoped to `kueue.x-k8s.io/managed=true` and deletes
  deployment/pod/statefulset/jobset/ray (`features/kueue/cluster/patch-webhook-scope-*.yaml`).
- **Manage at the highest-level object you own, not its pods.** A batch demo only needs
  the `Job` webhook; Job-level admission (suspend/resume) brings the pods up itself, so
  you never need the cluster-wide `pod` webhook.
- **Keep webhook-gated CRs out of `cluster/`.** Anything the operator's webhook
  validates (e.g. Kueue's `ClusterQueue`/`ResourceFlavor`) goes in `infra/` and is
  applied at *deploy* time — after the operator is up — so the bootstrap apply never
  races the controller coming up.
- If you must keep a broad webhook, prefer `failurePolicy: Ignore` so a down controller
  can't wedge the cluster — but scoping to your namespace is strictly better.

---

## 5b. Imperative cluster prerequisites — the `cluster_setup` hook

`cluster_dir` (§5) only covers **declarative** prereqs the Hub can `kubectl apply`. Some
features need **imperative** cluster setup that can't be a manifest — a GKE node pool
(`gcloud`, e.g. sandbox-kata's nested-virtualization pool), a `helm`/`ko` operator
install, cert minting (`openssl`), etc. For those, declare a **bootstrap hook**:

```yaml
# feature.yaml
paths:
  cluster_setup: cluster/install-my-prereq.sh   # run by build_infra.sh at bootstrap
```

`build_infra.sh` discovers every declared `cluster_setup` and runs it at cluster bootstrap
(after `cluster_dir`), so **a fresh clone + `build_infra.sh` installs everything — the
operator never has to know which manual scripts to run.** It exports the standard vars
(`PROJECT_ID`/`PROJECT_NAME`/`PROJECT`, `CLUSTER_NAME`/`CLUSTER`, `REGION`,
`ARTIFACT_REGISTRY_REPO`) so your script needs no env plumbing.

Two hard rules for a `cluster_setup` script:
- **It MUST be idempotent.** `build_infra.sh` re-runs on every bootstrap. Guard imperative
  steps: create-a-node-pool → `describe … || create …`; `helm install` → `helm upgrade
  --install`; CRDs/manifests → `apply` (already idempotent). A non-idempotent step that
  errors on re-run makes every re-bootstrap noisily "fail" for your feature.
- **A hook failure is non-fatal to the bootstrap** (a missing tool like `ko`/`helm`/`go`
  shouldn't wedge the whole cluster) — `build_infra.sh` warns and continues. So you also
  **must** declare `requires:` (below) or a missing prereq becomes a silent half-deploy.

### `requires:` — the deploy-time guard

Declare what the hook installs so the Hub can pre-flight it before deploying your feature:

```yaml
# feature.yaml
requires:
  runtimeclasses: [kata-clh]                       # e.g. sandbox-kata
  crds: [workerpools.ate.dev, actortemplates.ate.dev]   # e.g. substrate-*
```

Before applying your `infra/`, the Hub checks each declared RuntimeClass/CRD exists. If a
prereq is missing (hook not run, or still building, or a tool was absent at bootstrap), the
deploy **fails fast with an actionable message** ("run ./build_infra.sh …") instead of the
two failure modes these features hit without it: the router coming up but sandbox creation
erroring at runtime (kata), or the deploy aborting on `no matches for kind WorkerPool` and
leaving an **empty namespace stuck in PROVISIONING** (substrate).

> **Prefer `cluster_dir` when you can.** Only reach for `cluster_setup` when the prereq
> genuinely can't be a manifest (node pools, `ko`/`helm`, cert minting). A plain operator
> that installs from a kustomize/CRD bundle belongs in `cluster_dir` (§5) — it's simpler,
> needs no extra tools on the build host, and is idempotent for free.

---

## 6. Frontend / playroom (`frontend/`), if any

- Ship `index.html` (+ `app.js`, optional `style.css`) under your declared
  `paths.frontend_dir`. At startup the Hub **mirrors** `features/<name>/<frontend_dir>/`
  into its served static root and serves it at `/<playroom_slug>/` (e.g. `/sandbox/`).
  Reference your script relatively, e.g. `/static/features/<name>/app.js`. No manual
  copy step — local and submodule features are served identically.
- `frontend_dir` is the **Hub playroom** UI. If your feature's deployed workload serves
  its *own* UI (like gpu-inference's app container), keep that in a different directory
  so the two don't collide.
- **Standalone UI (external features): the Hub serves the playroom, so on its own the
  feature has no UI unless it serves one itself.** An external feature that must run
  standalone should have its own container serve `frontend_dir` too — e.g. the app
  mounts the static dir at `/` and at `/static/features/<name>/` (mirroring the Hub's
  layout so `index.html`'s asset paths resolve in both). Ship the *same* frontend code:
  have it probe the Hub API (`GET /api/features/<name>/config`) and, when that 404s
  (no Hub), fall back to `LIVE` against its own origin / the Gateway IP. That one UI then
  works both hub-hosted and standalone. (A **link-out** feature avoids this entirely —
  its own app already serves the UI; that's `inference-gateway`.)
- Calls to **Hub APIs** must attach the admin JWT:
  `Authorization: Bearer ${localStorage.getItem("admin_jwt")}`.
- Calls to **your feature's data plane** go to your feature's own router under
  `/api/features/<name>/...` (see §6a), or directly to your Gateway IP with CORS.
- Avoid hardcoded cache-buster query strings baked per-edit; rely on the Hub's
  no-cache headers on playroom HTML.

## 6a. Your feature's data-plane router (`hub_router`)

Each feature owns its backend API — its own "proxy" — instead of sharing a Hub-wide
one. This keeps features independent: the API is added/removed with the feature,
namespaced so two features can never collide, and added with **zero edits to Hub code**.

- Add a module in your feature dir (conventionally `hub_router.py`) exposing a FastAPI
  `APIRouter` named `router`, and point `hub_router` in `feature.yaml` at it.
- The Hub mounts it at `/api/features/<name>` and applies the admin JWT dependency, so
  define routes with paths *relative* to that prefix (e.g. `@router.post("/chat")` →
  `/api/features/<name>/chat`). Do **not** import Hub auth/routing internals.
- Use the Hub's shared SDK for plumbing: `from showcase_admin.app import database,
  k8s_client` gives you `database.get_db`, `database.get_feature_namespace(db, name)`,
  and k8s helpers (`get_gateway_ip`, `execute_http_with_retry`, …). Guard live calls
  behind `config.MODE == "MOCK"` so the playroom works offline.
- An external feature's `hub_router.py` runs *inside* the Hub container, so any Python
  deps it imports must be in the Admin image's requirements. Keep it thin — heavy logic
  belongs in the feature's own deployed workload, reached over HTTP.

---

## 7. Mock mode

The Hub runs fully offline with `MODE=MOCK` for fast, zero-cost dev loops. Your feature
must not break mock runs:

- Don't require live cluster calls at import time.
- For any data-plane endpoint the playroom hits, provide a deterministic mock reply
  path (guarded by `MODE=MOCK`) so the UI and tests work without GKE.

---

## 7a. Standalone operation (the `.env` + script trio)

A Hub feature assumes a **live cluster** and owns only its namespace. A standalone
repo has neither — so it must also know how to **create the cluster** and wire up
its own config. That is the one part of the contract the Hub can't exercise for
you, and historically the most under-specified. An external feature ships three
scripts plus an env file (the Hub ignores all four):

| File | Responsibility | Hub equivalent |
|---|---|---|
| `.env` / `.env.example` | all standalone config (project, cluster, region, knobs) | the Hub injects its standard vars (§3) + `template_defaults` |
| `setup_infra.sh` | create the GKE **cluster** + apply **cluster-scoped** prereqs (`cluster/`) | `build_infra.sh` (cluster bootstrap) |
| `deploy_app.sh` | build/push the image + apply **per-namespace** infra (`infra/`) | `scripts/build_and_push.sh` + per-deploy apply |
| `verify_setup.sh` | wait for readiness, discover the Gateway IP, smoke-test | the Hub's readiness poll + mock-mode integration test (§9) |

Note the split mirrors the Hub's own: **cluster-once vs per-deploy**. Keep
`setup_infra.sh` ↔ `cluster/` and `deploy_app.sh` ↔ `infra/` aligned with the same
YAML the Hub applies, so the two paths never drift. `inference-gateway` is the
reference implementation.

### `.env` — and the standalone↔Hub variable mapping

The standalone scripts source `.env`; the Hub supplies its own variables instead.
Most names line up, but a few differ — author manifests against the **Hub** names
(§3) and define everything else in `template_defaults`, then mirror those names in
`.env` for standalone:

| Standalone `.env` | Hub-provided (§3) | Notes |
|---|---|---|
| `PROJECT_ID` | `PROJECT_NAME` | **same value, different name** — the most common gotcha |
| `REGION` | `REGION` | same |
| `ARTIFACT_REGISTRY_REPO` | `ARTIFACT_REGISTRY_REPO` | same |
| `NAMESPACE` (default `default`) | `NAMESPACE` (`gke-showcase-<name>`) | default it to `default` so `${NAMESPACE}` still renders standalone |
| `ZONE`, `CLUSTER_NAME` | — | standalone-only: the Hub already has a cluster |
| `GATEWAY_NAME` | — | from `feature.yaml` `gateway.name`; mirror in `.env` |
| `REGISTRY`, `IMAGE_TAG` | composed in `template_defaults` | e.g. `REGISTRY: "${REGION}-docker.pkg.dev/${PROJECT_NAME}/${ARTIFACT_REGISTRY_REPO}"` |

Ship a committed `.env.example` (documented, no secrets) and gitignore the real
`.env` (`.env`, `.env_*`).

### `setup_infra.sh` — creating the cluster

The thing a Hub feature never does. At minimum it should:

- **Source `.env`** and fail clearly if it's missing.
- **Create the GKE cluster** idempotently (`gcloud container clusters describe …
  || create …`), with the capabilities the demo needs:
  - `--gateway-api=standard` — required for the `Gateway`/`HTTPRoute` you ship.
  - `--enable-autoprovisioning` (+ `--min/max-cpu`, `--min/max-memory`, and
    `--max-accelerator` for GPU) — **required if your `ComputeClass` uses node
    auto-creation**, so GKE can spin up (Spot/GPU) node pools on demand.
  - a **proxy-only subnet** in the region if you use a regional gateway
    (`gke-l7-rilb`/regional-external) — create it only if absent, and **never
    delete it** (other clusters share it).
- `gcloud container clusters get-credentials …` so `kubectl` targets *this*
  cluster (never act on the ambient context).
- **Apply `cluster/`** — the same cluster-scoped prereqs the Hub installs at
  bootstrap (a kustomize CRD bundle via `kubectl apply -k`, plain manifests
  otherwise).
- Offer **teardown modes** for clean rebuilds, e.g. `--delete` (in-cluster
  resources, keep the cluster) and `--delete-cluster` (also delete the cluster).

### `deploy_app.sh` — image + per-namespace infra

- Ensure the **Artifact Registry repo** exists (`gcloud artifacts repositories
  create … || true`) and `gcloud auth configure-docker <region>-docker.pkg.dev`.
- `docker build --platform linux/amd64` (GKE nodes are amd64) and push.
- Use a **per-cluster image tag** (default `IMAGE_TAG=$CLUSTER_NAME`) so multiple
  clusters never clobber each other's `:latest`.
- Create the namespace, then **apply `infra/`** with portable substitution, and
  wait for the `deployment_name` rollout + the Gateway IP.

### Portable manifest substitution (no `envsubst`)

`envsubst` isn't installed on stock macOS. Use a tiny `python3` helper so the
scripts run anywhere, and so Kubernetes downward-API refs survive:

```bash
# Expands ${VAR}; leaves $(VAR) alone (e.g. downward-API $(POD_IP)).
render() { python3 -c "import os,sys;sys.stdout.write(os.path.expandvars(open(sys.argv[1]).read()))" "$1"; }
export NAMESPACE IMAGE …            # the vars your manifests reference
render infra/deployment.yaml | kubectl apply -n "$NAMESPACE" -f -
```

Author manifests with `${VAR}` for build-time substitution and `$(VAR)` only for
Kubernetes' own runtime refs — `os.path.expandvars` rewrites the former and leaves
the latter intact.

---

## 8. Adding a feature to the Hub

Regardless of flavor, once the directory exists under `features/<name>/` with a valid
`feature.yaml`, the Hub:

1. Discovers `features/<name>/feature.yaml` at startup → builds the dashboard card and
   lifecycle maps.
2. Uses `build` entries to compile/push images via `scripts/build_and_push.sh`.
3. Applies `cluster_dir` during `build_infra.sh`, and `infra_dir` per deploy.

### Local feature (lives in this repo)

```bash
# from the Hub repo root — just create the directory and the descriptor
mkdir -p features/<name>/infra
$EDITOR features/<name>/feature.yaml
git add features/<name>
git commit -m "feat(features): add <name> local showcase"
```

Edit it in place like any other Hub source. No `.gitmodules`, no submodule pointer.
This is how `agent-sandbox` and `gpu-inference` live today.

### External feature (separate repo via submodule)

```bash
# from the Hub repo root
git submodule add https://github.com/<you>/<your-feature-repo>.git features/<name>
git commit -m "feat(features): add <name> as submodule"
```

`build_infra.sh` and `scripts/build_and_push.sh` auto-run `git submodule update --init
--recursive`, so a fresh checkout deploys without remembering it (run it manually only if
you work with the files before invoking the scripts). To update the demo later: commit in
the feature repo, then bump the pointer in the Hub (`git -C features/<name> pull && git
add features/<name> && git commit`). The feature repo keeps its own `setup_infra.sh`/`deploy_app.sh` for
standalone use; the Hub ignores those and drives the feature through `feature.yaml`.

### Converting local → external later

Because both flavors share the same layout, promoting a local feature into its own repo
is mechanical: move `features/<name>/` into a new repo, add that repo back as a
submodule at the same path, and add the standalone scripts. Nothing in the Hub loader
changes.

---

## 8a. Building images on a separate machine (build ↔ deploy split)

The Hub build pipeline is **decoupled from the cluster**. `scripts/build_and_push.sh`
needs only Docker, an authenticated `gcloud`, and the repo, and it only has to reach
**Artifact Registry** — never the GKE cluster. So you can build/push from a dedicated
build host (e.g. a beefy amd64 Linux box) and let a different, cluster-connected machine
(or the Hub UI) do the deploy. This mirrors §7a's standalone split, but for the Hub's own
pipeline rather than a feature's scripts.

On the build host:

1. **Prereqs:** Docker, `git`, and `gcloud auth login` +
   `gcloud auth configure-docker ${REGION}-docker.pkg.dev` (the script also runs the
   latter). `python3` with PyYAML is used to read descriptors (the repo `.venv` is
   preferred, system `python3` is the fallback).
2. **Get the code with submodules.** Commit & push the Hub submodule pointer **first**
   (an external feature's `.gitmodules` entry + pinned commit), then clone the Hub repo
   on the build host. `build_and_push.sh` auto-runs `git submodule update --init
   --recursive`, so `features/*` populate at their pinned commits without a manual step.
3. **Set the AR coordinates** the image tag is composed from — `PROJECT_NAME`, `REGION`,
   `ARTIFACT_REGISTRY_REPO` (via `.env` or env). No cluster variables are needed.
4. **Build + push, skip the rollout:**
   ```bash
   ./scripts/build_and_push.sh --feature <name> --no-rollout   # or omit --feature for all
   ```
   A build-only host with no reachable cluster skips the rollout automatically, but pass
   `--no-rollout` to be explicit and to avoid the script's
   `gcloud container clusters get-credentials` probe.

**Architecture — always build amd64.** GKE nodes are amd64, so the Hub's `docker build`
commands pin `--platform linux/amd64` (overridable via `BUILD_PLATFORM`). A bare
`docker build` on an arm64 host (Apple Silicon, Graviton) would otherwise produce arm64
images that crash on the cluster with exec-format errors — build on amd64, or cross-build
with buildx/qemu. (This is the same rule §7a states for the standalone `deploy_app.sh`.)

**Re-deploying after a rebuild.** First deploy pulls the pushed `:latest` automatically.
But `:latest` is **not** re-pulled on its own, so after rebuilding an already-running
feature you must roll it from a cluster-connected machine: the script does
`kubectl rollout restart deployment/<deployment_name> -n gke-showcase-<name>` when a
cluster is reachable. Note this only recycles the feature's **Deployment** — workloads
managed by a CRD (e.g. a KubeRay `RayCluster`'s head/worker pods) are not Deployments and
need a redeploy (Hub teardown + redeploy, or recreate the CR) to pick up a new image.

---

## 9. Testing

- Author unit tests for manifest expansion and any app logic.
- Author a Hub-side integration test (mock mode) that lists the feature, deploys it,
  hits its router under `/api/features/<name>/...`, and tears it down.
- Live GKE tests must interact **only** through the Hub's REST API
  (`/api/showcases/...`, `/api/features/<name>/...`) — no manual `kubectl apply`
  of feature resources, no finalizer patching.

---

## 10. Pre-merge checklist

- [ ] `feature.yaml` present and valid; `name`, `paths`, `deployment_name`, `gateway` set.
- [ ] Exactly one UI model: hub-hosted (`frontend_dir` + `playroom_slug`) OR link-out
      (`entrypoint_service`) — not both.
- [ ] Dedicated `Gateway` + `HTTPRoute`; `HTTPRoute` backend Service is consistent.
- [ ] `deployment_name` matches the real Deployment metadata name.
- [ ] If the feature has a backend API: `hub_router` declared, router paths are relative
      to the `/api/features/<name>` mount, and it imports no Hub auth/routing internals.
- [ ] **Namespace-portable**: no hardcoded `default` anywhere — `metadata.namespace`,
      RBAC subjects, container args, and cross-resource refs use `${NAMESPACE}`; app code
      reads `POD_NAMESPACE` (downward API). Standalone defaults `NAMESPACE=default`.
- [ ] Every `${VAR}` in manifests is Hub-standard or declared in `template_defaults`
      (`grep -rE '\$\{[A-Z_]+\}'` and check each).
- [ ] Cluster-scoped resources (if any) live in `cluster/` and are declared (plain
      top-level YAML, or a **top-level** `kustomization.yaml` for CRD bundles — subdir
      kustomizations are not discovered; include any needed `Namespace` as a resource).
- [ ] **Imperative prereqs (node pool / helm / ko / certs):** declared via
      `paths.cluster_setup`, the script is **idempotent** (re-run safe), and the prereqs it
      installs are declared in `requires:` (runtimeclasses / crds) so the Hub pre-flights
      them and never silently half-deploys. (See §5b.)
- [ ] **New CRD kinds:** if a manifest uses a resource kind no existing feature uses, add
      its `apiGroups`/`resources` to the admin ClusterRole in `infra/main-app.yaml` (else
      the deploy 403s and aborts). Kubernetes RBAC only — not GCP IAM. (See §5.)
- [ ] **Admission webhooks:** if the feature installs an operator with cluster-scoped
      webhooks (Kueue, Istio, …), they are scoped to the feature's own namespace and only
      the kinds it manages (delete the rest); webhook-gated CRs are applied at deploy time
      (`infra/`), not at bootstrap (`cluster/`). (See §5a.)
- [ ] **Data-plane readiness:** the playroom gates on the gateway being reachable (probe
      `<gateway>/healthz`) and shows a "provisioning…" state instead of erroring while the
      LB programs; it never falls back to the Hub origin for data-plane calls. (See §3a.)
- [ ] **No `Namespace` object in `infra/`** (the Hub owns the namespace; a `Namespace`
      404s the deploy). Select your namespace via the `kubernetes.io/metadata.name` label
      if a webhook/policy needs it. (See §3.)
- [ ] **RBAC applies before the workload** — the `ServiceAccount` your Deployment uses is
      in a file that sorts first (e.g. `00-rbac.yaml`), so pods aren't rejected for a
      missing SA. (See §3.)
- [ ] App exposes `/healthz` and CORS; model `model` field matches `--served-model-name`.
- [ ] Playroom attaches JWT to Hub calls; works in `MODE=MOCK`.
- [ ] **Standalone UI:** an external hub-hosted-playroom feature also serves its own
      `frontend_dir` (the Hub serves the UI only in Hub mode) — same code, with a
      Hub-config probe that falls back to its own origin. (See §6.) Link-out features
      already serve their own UI.
- [ ] **Standalone (external features):** committed `.env.example`, gitignored `.env`;
      `setup_infra.sh` creates the cluster (`--gateway-api`, NAP if the ComputeClass
      auto-creates pools) + applies `cluster/`; `deploy_app.sh` builds/pushes + applies
      `infra/`; `verify_setup.sh` validates. Variable names map to §3 (e.g. `PROJECT_ID`
      ↔ `PROJECT_NAME`); manifests use portable substitution (no `envsubst`). (See §7a.)
- [ ] Tests pass: `.venv/bin/pytest tests/`.
```
