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

### [ ] Milestone 1: Core Configurations & Multi-Tier Offline Testing Setup
*   **Objective**: Establish repository configurations and build a comprehensive pytest testing harness to allow 100% offline local development.
*   **Description**: Sets up `.env.example` contracts, git-ignores, and the `/tests` structure (with pytest conftest, basic auth unit tests, and config loaders).
*   **Tasks**:
    - `[ ]` Create `.env.example` template and secure `.gitignore` config.
    - `[ ]` Author `/tests/conftest.py` to manage global mock fixtures and mock FastAPI TestClient bindings.
    - `[ ]` Implement `/tests/unit/test_config.py` to check environment configuration loaders.
    - `[ ]` Implement `/tests/unit/test_auth.py` to test HTTP Basic Authentication checks.
*   **Success Criteria**:
    - Running `pytest tests/unit` executes instantly, resolving dependencies and passing all configuration and basic auth validation checks.

---

### [ ] Milestone 2: Persistent State & Showcase Hub Backend API
*   **Objective**: Build the central FastAPI backend with relational SQLite state persistence on-disk, secured behind optional HTTP Basic Auth.
*   **Description**: Establishes database schemas, models, connection handlers (remountable to `/data/showcase.db` on GKE PD PVC), and CRUD controllers managing active showcases.
*   **Tasks**:
    - `[ ]` Implement SQLite session configuration and database ORM schemas in `showcase-admin/app/database.py`.
    - `[ ]` Build core FastAPI routes in `showcase-admin/app/main.py` with Basic Auth checkpoints.
    - `[ ]` Author `/tests/unit/test_db.py` to verify persistent CRUD operations.
*   **Success Criteria**:
    - Running `pytest tests/unit/test_db.py` passes, proving table creation, state updates, and persistence checks are functional.
    - Accessing administrative endpoints `/api/showcases` requires authenticated headers when enabled in the configuration.

---

### [ ] Milestone 3: Asynchronous GKE Controller (Mock/Real Client)
*   **Objective**: Build the asynchronous GKE resources orchestrator driven by `kubernetes_asyncio` with complete simulated behavior for local iteration.
*   **Description**: Implements `k8s_client.py` which handles dynamic namespace creations, deletes, and template manifest expansions. Supports a simulated offline manager (`MODE=MOCK`) that mimics K8s state transitions and streams logs.
*   **Tasks**:
    - `[ ]` Implement `showcase-admin/app/k8s_client.py` supporting dynamic YAML interpolation and non-blocking namespace handlers.
    - `[ ]` Build mock client handlers inside `k8s_client.py` to simulate state transitions (Dormant -> Deploying -> Active).
    - `[ ]` Implement `/tests/integration/test_k8s_mock.py` and `/tests/integration/test_api_mock.py`.
*   **Success Criteria**:
    - Running `pytest tests/integration` passes 100% without a real GKE connection.
    - The API endpoints cleanly return simulated status changes and mock deployment logs.

---

### [ ] Milestone 4: Premium Showcase Hub Dashboard UI
*   **Objective**: Design and implement a premium, highly interactive single-page dashboard UI featuring state loops, live console streams, and high-fidelity animations.
*   **Description**: Creates the static HTML, premium dark-theme CSS (glassmorphic cards, glowing status badges, smooth hover responses), and asynchronous JavaScript modules.
*   **Tasks**:
    - `[ ]` Design `showcase-admin/frontend/index.html` geometric layout using Outfit and Inter typography.
    - `[ ]` Develop `showcase-admin/frontend/style.css` with vibrant, modern custom variables and keyframe micro-animations.
    - `[ ]` Develop `showcase-admin/frontend/app.js` to poll showcase statuses and pipe SSE log outputs to the terminal overlay.
*   **Success Criteria**:
    - Opening the local dashboard page in a browser displays a premium, state-of-the-art card grid.
    - Deploying and tearing down showcases triggers visual animations, pulsing indicators, and streams console outputs beautifully in real-time.

---

### [ ] Milestone 5: Showcase Feature 1 - Dynamic GKE Agent Sandbox
*   **Objective**: Adapt and modularize the GKE Agent Sandbox demo as an on-demand showcase component deployed into its own isolated namespace.
*   **Description**: Ports the demo-app and sandbox router container specifications from `/Users/ragoler/Documents/JetSki/AgentSandboxExample`, and adapts the manifests (`sandbox-template.yaml`, `sandbox-warmpool.yaml`, `sandbox-router.yaml`) to be rendered dynamically by the Admin app.
*   **Tasks**:
    - `[ ]` Package `features/agent-sandbox/` with modular router and demo app source codes.
    - `[ ]` Structure standard sandbox manifests under `features/agent-sandbox/infra/`.
    - `[ ]` Wire Agent Sandbox installation routines to the Admin Dashboard GKE controller.
*   **Success Criteria**:
    - The Admin Dashboard dynamically deploys the entire Sandbox showcase into a clean namespace (`gke-showcase-sandbox`) on-demand.
    - Automated integration checks confirm successful SandboxTemplate loading and correct warmpool configurations.

---

### [ ] Milestone 6: Showcase Feature 2 - Spot GPU & vLLM Model Inference
*   **Objective**: Design the GPU Showcase illustrating cost-efficient LLM inference via Nvidia L4 Spot GPUs, GCSFuse bucket mounting, and a chat playground.
*   **Description**: Builds manifests for vLLM server provisioning, sets up Spot GPU toleration structures, configures read-only GCSFuse CSI volumes mapping, and develops a sleek chat interface.
*   **Tasks**:
    - `[ ]` Package the vLLM setup and playground frontend under `features/gpu-inference/`.
    - `[ ]` Author standard manifests in `features/gpu-inference/infra/` featuring Spot GPU node pool selectors, GCSFuse mounts, and ingress route bindings.
    - `[ ]` Integrate GPU Inference installation loops in the Showcase Admin engine.
*   **Success Criteria**:
    - The GKE controller dynamically instantiates the `gke-showcase-inference` namespace.
    - Validates successful GCSFuse storage mapping and L4 GPU scheduling requests.
    - Streams model responses through the designated routing gateway.

---

### [ ] Milestone 7: Production GKE Bootstrapping & Live Verification
*   **Objective**: Automate GKE cluster creation, shared gateway layouts, PVC persistent disks, and verify the entire Showcase Hub end-to-end.
*   **Description**: Implements `build_infra.sh` and dynamic image building scripts, creating a robust, secure, and fully automated path from local command-line bootstrap to live production.
*   **Tasks**:
    - `[ ]` Author `scripts/build_and_push.sh` automating multi-container builds to Artifact Registry.
    - `[ ]` Implement `build_infra.sh` cluster provisioning script (with gVisor nodes, Spot GPU nodes, persistent disk PVCs, and gateway routes).
    - `[ ]` Deploy the Showcase Admin pod to the real GKE cluster.
    - `[ ]` Execute end-to-end live validation: Deploy Agent Sandbox, claim gVisor pods, verify Gemini AI responses, deploy vLLM, verify chat streaming, and execute dynamic namespace cleanups.
*   **Success Criteria**:
    - A single run of `./build_infra.sh` successfully provisions the entire working cluster and dashboard from scratch.
    - All showcase deployments and communication channels are fully functional, secure, and cleanly removable from GKE.
