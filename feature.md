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
└── setup_infra.sh          # OPTIONAL — standalone-only provisioning (Hub ignores)
```

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

Note: the Hub routes a `ComputeClass` found in a per-namespace `infra_dir` to the
cluster-scoped API automatically, so a demo that keeps its ComputeClass alongside its
other manifests still works without a separate `cluster_dir`. CRD bundles (e.g. installed
via `kubectl apply -k` or Helm in a demo's own `setup_infra.sh`) are a one-time cluster
setup — run them as part of cluster bootstrap; they are not a per-feature Hub concern.

> This is the one structural gap between a typical standalone demo (which provisions
> cluster + namespace together in `setup_infra.sh`) and a Hub feature (which assumes a
> live cluster and only owns its namespace). Splitting prereqs out is what makes a
> heavy demo like `inference_gateway` mount cleanly.

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
- [ ] Dedicated `Gateway` + `HTTPRoute`; `HTTPRoute` backend Service is consistent.
- [ ] `deployment_name` matches the real Deployment metadata name.
- [ ] If the feature has a backend API: `hub_router` declared, router paths are relative
      to the `/api/features/<name>` mount, and it imports no Hub auth/routing internals.
- [ ] All manifests namespace-templated with `${NAMESPACE}`.
- [ ] Cluster-scoped resources (if any) live in `cluster/` and are declared.
- [ ] App exposes `/healthz` and CORS; model `model` field matches `--served-model-name`.
- [ ] Playroom attaches JWT to Hub calls; works in `MODE=MOCK`.
- [ ] Standalone deploy still works (your own `setup_infra.sh`/`deploy_app.sh`).
- [ ] Tests pass: `.venv/bin/pytest tests/`.
```
