# Master Implementation & Verification Plan: GKE Feature Showcase Hub

This plan outlines the granular milestones required to build, test, and deploy the GKE Feature Showcase Hub. Each milestone represents a decoupled engineering block that is self-contained, carries explicit automated validation tests, and can be delegated to concurrent, parallel subagents.

---

## Multi-Agent Support & Parallel Delegation
Yes! We support multi-agent orchestration. The execution of this plan is designed to be delegated across specialized subagents:
*   **Orchestrator Agent (Parent)**: Coordinates the global state, integrates components, and manages cluster deployments.
*   **Subagent `backend-developer` (self)**: Focuses on building the FastAPI API layer, SQLite database integrations, basic auth security middleware, and K8s clients.
*   **Subagent `frontend-designer` (self)**: Focuses on building the premium glassmorphic HTML/CSS/JS Showcase Hub dashboard UI and dynamic SSE/polling adapters.
*   **Subagent `qa-engineer` (self)**: Responsible for authoring robust pytest files, maintaining the offline mock framework, and executing verification plans.
*   **Subagent `gke-infra-specialist` (self)**: Builds the GKE bootstrap scripts, GCSFuse mounts, Spot GPU dynamic pools, and gVisor Agent Sandbox manifests.

---

## Milestones & Progress Checklist

### [x] Milestone 1: Virtual Environment & Offline Mock Testing Setup
*   **Objective**: Establish the local Python virtual environment and build a comprehensive, offline-capable pytest testing harness.
*   **Description**: Sets up `.venv`, `.env.example` config specifications, git-ignores, and the `/tests` directory structure (with pytest fixtures, config loaders, and Basic Auth middleware).
*   **Tasks**:
    - `[x]` Create Python virtual environment (`.venv`) in workspace.
    - `[x]` Create `.env.example` template and secure `.gitignore` configuration.
    - `[x]` Author `/tests/conftest.py` to manage global mock fixtures and mock FastAPI TestClient bindings.
    - `[x]` Implement `/tests/unit/test_config.py` to check environment configuration loaders.
    - `[x]` Implement `/tests/unit/test_auth.py` to test HTTP Basic Authentication checking logic.
*   **Success Criteria**:
    - Running `pytest tests/unit` executes instantly in the virtual environment, passing all configuration and auth checks.

---

### [x] Milestone 2: Persistent State & Showcase Hub Backend API
*   **Objective**: Build the central FastAPI backend with dynamic user namespace overrides, feature deletion controllers, and relational SQLite persistence.
*   **Description**: Establishes database schemas for tracking installed showcases (their custom namespaces, reach out URLs, and operational status), and mounts database files at `/data/showcase.db`. Exposes Basic Auth secured API endpoints.
*   **Tasks**:
    - `[x]` Implement SQLite session config and database schemas in `showcase_admin/app/database.py`.
    - `[x]` Build core FastAPI routes in `showcase_admin/app/main.py` with Basic Auth checkpoints, allowing custom namespace parameters on deployment (`POST /api/showcases/{name}/deploy`) and complete namespace deletion (`DELETE /api/showcases/{name}/teardown`).
    - `[x]` Author `/tests/unit/test_db.py` to verify table creations and CRUD operations.
*   **Success Criteria**:
    - Database successfully persists configurations locally or on a remounted GKE PVC.
    - Pytest unit tests pass cleanly.

---

### [x] Milestone 3: Asynchronous GKE Controller (Mock/Real Client)
*   **Objective**: Build the asynchronous GKE dynamic resource orchestrator supporting custom namespaces, deletion calls, and simulated offline states.
*   **Description**: Implements `k8s_client.py` to dynamically apply and delete templates in custom user-specified namespaces. Supports a simulated offline manager (`MODE=MOCK`) that mimics namespace lifecycle transitions and streams diagnostic logs.
*   **Tasks**:
    - `[x]` Implement `showcase_admin/app/k8s_client.py` supporting dynamic namespace provisioning and resource deletions.
    - `[x]` Build mock GKE client controllers inside `k8s_client.py` to simulate state loops for custom namespaces.
    - `[x]` Implement `/tests/integration/test_k8s_mock.py` and `/tests/integration/test_api_mock.py`.
*   **Success Criteria**:
    - Integration tests pass 100% in the virtual environment without cloud resources.
    - Confirm dynamic namespaces and resources are mapped and mocked correctly.

---

### [x] Milestone 4: Premium Showcase Hub Dashboard UI
*   **Objective**: Design the premium single-page HTML/CSS/JS dashboard frontend with user namespace inputs, delete buttons, reach out URLs, and playroom interaction overlays.
*   **Description**: Develops the dark-theme layout, adding text inputs for namespace selection, "Open Playroom" toggle overlays, "Delete Showcase" actions, and log polling frames.
*   **Tasks**:
    - `[x]` Design `showcase_admin/frontend/index.html` adding custom namespace input forms, active reach out URL links, and inline console panels.
    - `[x]` Develop `showcase_admin/frontend/style.css` featuring premium glassmorphism variables and glowing status micro-animations.
    - `[x]` Develop `showcase_admin/frontend/app.js` to handle authenticated CRUD triggers, poll namespaces, and stream diagnostic outputs.
*   **Success Criteria**:
    - Dashboard loads in mock mode showing custom namespace fields and reach-out URL hooks on each card.
    - Pressing "Tear Down" triggers confirmation alerts, fades components, and removes simulated namespaces successfully.

---

### [x] Milestone 5: Showcase Feature 1 - Dynamic GKE Agent Sandbox (WIF / local vLLM)
*   **Objective**: Package the GKE Agent Sandbox showcase with dynamic namespace creation, custom UI playroom, and inter-showcase local vLLM model routing options.
*   **Description**: Modularizes sandbox templates and router codes from `AgentSandboxExample`, enabling deployment to custom user namespaces. Implements UI toggles for WIF-Gemini vs local vLLM service communication.
*   **Tasks**:
    - `[x]` Package `features/agent-sandbox/` sources (router, demo-app, and infra templates).
    - `[x]` Implement environment variable mapping in manifests for dual LLM provider configurations.
    - `[x]` Develop an embedded sandbox playroom chat UI enabling users to spawn sandboxes and toggle between calling Cloud Gemini or local vLLM URLs.
*   **Success Criteria**:
    - Deploys successfully to user-specified namespaces.
    - Playroom correctly resolves local cluster DNS addresses (e.g. `http://vllm-service.<namespace>.svc.cluster.local`) when routing queries locally.

---

### [x] Milestone 6: Showcase Feature 2 - Spot GPU & vLLM Model Inference
*   **Objective**: Package the vLLM Inference showcase with dynamic namespaces, L4 GPU Spot configurations, GCSFuse volume mapping, and a chat playground using Vertex Model Garden.
*   **Description**: Outlines vLLM manifests, configures Spot node tolerations, structures read-only GCSFuse mounts targeting Google's public bucket `vertex-model-garden-public-us`, and designs a beautiful inline token streaming playground.
*   **Tasks**:
    - `[x]` Package the vLLM code, templates, and CSS chat client under `features/gpu-inference/`.
    - `[x]` Setup manifests in `features/gpu-inference/infra/` utilizing Spot GPU schedulers and Google's public Model Garden GCSFuse bucket configuration.
    - `[x]` Wire the model server routes to register local service targets.
*   **Success Criteria**:
    - Provisions the inference namespace and mounts the public weight storage dynamically.
    - Exposes an inline chat playroom streaming tokens, and provides a stable cluster-local service DNS.

---

### [x] Milestone 7: Production GKE Bootstrapping & Live Integration Verification
*   **Objective**: Script the real GKE cluster bootstrap, Gateway routes, persistent PVC volumes, and perform live multi-showcase validation.
*   **Description**: Develops the automated `build_infra.sh` script to create cluster and shared services, builds images using `scripts/build_and_push.sh`, and runs full end-to-end functional tests.
*   **Tasks**:
    - `[x]` Create `scripts/build_and_push.sh` building and pushing all container images.
    - `[x]` Create `build_infra.sh` bootstrapping base GKE with persistent disk PVCs and shared gateways (omitting upfront specialized node pools).
    - `[x]` Deploy the Showcase Admin Dashboard pod.
    - `[x]` Run End-to-End verification: Deploy Sandbox & GPU inference to custom namespaces, verify vLLM chat streaming, verify local sandbox-to-vLLM cluster routing, and verify teardown deletions.
*   **Success Criteria**:
    - Running `build_infra.sh` deploys the entire cluster, shared services, and dashboard cleanly.
    - Dynamic custom namespace creation, teardown, and inter-showcase service calls work perfectly under live GKE testing.
