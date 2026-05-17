# Master Implementation & Verification Plan: GKE Feature Showcase Hub

This plan outlines the granular milestones required to build, test, and deploy the GKE Feature Showcase Hub. Each milestone represents a decoupled engineering block that is self-contained, carries explicit automated validation tests, and can be delegated to concurrent, parallel subagents.

---

## Multi-Agent Support & Parallel Delegation
Yes! We support multi-agent orchestration. The execution of this plan is designed to be delegated across specialized subagents:
*   **Orchestrator Agent (Parent)**: Coordinates the global state, integrates components, and manages cluster deployments.
*   **Subagent `backend-developer` (self)**: Focuses on building the FastAPI API layer, SQLite database integrations, JWT authentication security, and K8s clients.
*   **Subagent `frontend-designer` (self)**: Focuses on building the premium glassmorphic HTML/CSS/JS Showcase Hub dashboard UI, embedded login screens, and telemetry tabs.
*   **Subagent `qa-engineer` (self)**: Responsible for authoring robust pytest files, maintaining the offline mock framework, and executing verification plans.
*   **Subagent `gke-infra-specialist` (self)**: Builds the GKE bootstrap scripts, GCSFuse mounts, Spot GPU dynamic pools, and decentralized Gateway manifests.

---

## Phase 1: Baseline Hub Implementation (Completed)

### [x] Milestone 1: Virtual Environment & Offline Mock Testing Setup
- `[x]` Create Python virtual environment (`.venv`) in workspace.
- `[x]` Create `.env.example` template and secure `.gitignore` configuration.
- `[x]` Author `/tests/conftest.py` to manage global mock fixtures.
- `[x]` Implement `/tests/unit/test_config.py` and `/tests/unit/test_auth.py`.

### [x] Milestone 2: Persistent State & Showcase Hub Backend API
- `[x]` Implement SQLite session config and database schemas in `showcase_admin/app/database.py`.
- `[x]` Build core FastAPI routes in `showcase_admin/app/main.py`.
- `[x]` Author `/tests/unit/test_db.py` to verify table creations and CRUD operations.

### [x] Milestone 3: Asynchronous GKE Controller (Mock/Real Client)
- `[x]` Implement `showcase_admin/app/k8s_client.py` supporting dynamic namespace provisioning and resource deletions.
- `[x]` Implement `/tests/integration/test_k8s_mock.py` and `/tests/integration/test_api_mock.py`.

### [x] Milestone 4: Premium Showcase Hub Dashboard UI
- `[x]` Design `showcase_admin/frontend/index.html` and `style.css`.
- `[x]` Develop `showcase_admin/frontend/app.js`.

### [x] Milestone 5: Showcase Feature 1 - Dynamic GKE Agent Sandbox (WIF / local vLLM)
- `[x]` Package `features/agent-sandbox/` sources (router, demo-app, and infra templates).

### [x] Milestone 6: Showcase Feature 2 - Spot GPU & vLLM Model Inference
- `[x]` Package the vLLM code, templates, and CSS chat client under `features/gpu-inference/`.

### [x] Milestone 7: Production GKE Bootstrapping & Live Integration Verification
- `[x]` Create `scripts/build_and_push.sh` and `build_infra.sh`.
- `[x]` Run full end-to-end verification.

---

## Phase 2: Architectural Evolution (In Progress)

### [ ] Milestone 8: Embedded JWT Authentication & HTML Login UI
*   **Objective**: Replace browser basic auth popups with an embedded HTML login card, JWT Bearer token authentication (`POST /api/auth/login`), and clean logout controls.
*   **Tasks**:
    - `[ ]` Add `pyjwt` to `showcase_admin/requirements-dev.txt`.
    - `[ ]` Overhaul `showcase_admin/app/auth.py` to generate and verify 24-hour signed JWT tokens.
    - `[ ]` Update `index.html` and `app.js` to display a centered glassmorphic login screen when unauthenticated, and a prominent "Logout" button in the top-right header when logged in.
    - `[ ]` Author `/tests/unit/test_jwt_auth.py` to verify token generation, expiration, and rejection of unsigned tokens.
    - `[ ]` Execute automated test suite and verify 100% passing status before completion.

### [ ] Milestone 9: Repository Modularization (Approach B)
*   **Objective**: Restructure feature folders to be 100% self-contained, housing both backend manifests and standalone frontend UI assets.
*   **Tasks**:
    - `[ ]` Create `features/agent-sandbox/frontend/` and move `showcase_admin/frontend/features/agent-sandbox/*` into it.
    - `[ ]` Create `features/gpu-inference/frontend/` and move `showcase_admin/frontend/features/gpu-inference/*` into it.
    - `[ ]` Update `showcase_admin/Dockerfile` and `scripts/build_and_push.sh` to dynamically copy `features/*/frontend/` during container compilation.
    - `[ ]` Author `/tests/unit/test_modular_build.py` to verify dynamic folder copying and static route mounting.
    - `[ ]` Execute automated test suite and verify 100% passing status before completion.

### [ ] Milestone 10: Decentralized Gateways & CORS
*   **Objective**: Decouple feature networking by assigning dedicated external Gateway IPs to each deployed showcase and enabling CORS.
*   **Tasks**:
    - `[ ]` Add `gateway.yaml` and `http-route.yaml` to `features/agent-sandbox/infra/` and `features/gpu-inference/infra/`.
    - `[ ]` Add FastAPI `CORSMiddleware` (`allow_origins=["*"]`) to Sandbox router and GPU inference workloads.
    - `[ ]` Update `k8s_client.py` to discover and persist each feature's unique external Gateway IP upon deployment.
    - `[ ]` Update `app.js` to route feature playroom interactions directly to the feature's standalone Gateway IP.
    - `[ ]` Author `/tests/integration/test_gateway_routing.py` verifying Gateway IP extraction and CORS header presence under mock state.
    - `[ ]` Execute automated test suite and verify 100% passing status before completion.

### [ ] Milestone 11: Global Cluster Telemetry & Statistics
*   **Objective**: Build a real-time cluster statistics engine querying the Kubernetes API directly for compute, workload, and accelerator metrics.
*   **Tasks**:
    - `[ ]` Implement `GET /api/stats` in `main.py` and `k8s_client.py` invoking k8s API object listings (`list_node`, `list_namespace`, `list_pod_for_all_namespaces`).
    - `[ ]` Aggregate Node counts, Namespace counts, Pod statuses, and active GPU/gVisor accelerator counts.
    - `[ ]` Build a dedicated **Cluster Telemetry** tab in `index.html` and `app.js` displaying live cluster diagnostic health.
    - `[ ]` Author `/tests/integration/test_telemetry_api.py` verifying accurate node/workload aggregation and mock API responses.
    - `[ ]` Execute automated test suite and verify 100% passing status before completion.

### [ ] Milestone 12: Soft Dependencies & Runtime IP Injection
*   **Objective**: Enable showcases to dynamically reference one another via runtime IP injection during deployment.
*   **Tasks**:
    - `[ ]` Add LLM provider selection dropdown (Gemini Cloud vs Deployed GPU Inference Gateway IP) to Admin UI deployment modal.
    - `[ ]` Pass selected connection string into manifest template rendering (`${LLM_SERVICE_ENDPOINT}`).
    - `[ ]` Author `/tests/unit/test_manifest_injection.py` verifying dynamic variable replacement and template expansion.
    - `[ ]` Execute automated test suite and verify 100% passing status before completion.

### [ ] Milestone 13: Comprehensive Test Suite Expansion & Code Coverage Optimization
*   **Objective**: Significantly expand automated testing across all layers of the repository to achieve >90% test coverage.
*   **Tasks**:
    - `[ ]` Install `pytest-cov` to measure test coverage metrics across the virtual environment.
    - `[ ]` Expand SQLite database unit tests (`/tests/unit/test_db.py`) to test edge cases (e.g. duplicate showcase names, invalid status transitions).
    - `[ ]` Expand GKE mock client tests (`/tests/integration/test_k8s_mock.py`) to simulate API timeouts and gateway resolution fallbacks.
    - `[ ]` Author longevity and resilience mock tests simulating repeated deploy/teardown cycles across multiple concurrent showcases.
    - `[ ]` Execute full coverage report (`pytest --cov=showcase_admin --cov=features tests/`) and verify >90% code coverage.

### [ ] Milestone 14: Refactor GPU Inference Playroom (Separation of Concerns)
*   **Objective**: Eliminate the embedded HTML/CSS/JS string in `features/gpu-inference/app/main.py` by refactoring the UI into standalone frontend assets (`index.html`, `style.css`, `app.js`).
*   **Tasks**:
    - `[ ]` Extract hardcoded HTML string from `main.py` and author `features/gpu-inference/frontend/index.html`.
    - `[ ]` Extract CSS styles into `features/gpu-inference/frontend/style.css`.
    - `[ ]` Extract client-side JavaScript into `features/gpu-inference/frontend/app.js`.
    - `[ ]` Refactor `main.py` to mount `StaticFiles` and return `FileResponse("index.html")`.
    - `[ ]` Verify standalone UI rendering and REST API communication (`POST /chat`) in local mock environment.

### [ ] Milestone 15: Live GKE Integration Testing Harness
*   **Objective**: Establish a robust integration testing harness (`/tests/integration/test_live_gke.py`) that verifies real GKE cluster operations, gateway routing, and custom resource allocations when `MODE=REAL`.
*   **Tasks**:
    - `[ ]` Author `test_live_gke_connection.py` verifying real `kubernetes_asyncio` API authorization against the active GKE control plane.
    - `[ ]` Author live showcase deployment tests verifying real namespace creation and Gateway external IP assignment on GKE.
    - `[ ]` Author live teardown tests verifying complete namespace termination and Cluster Autoscaler node pool scale-down to 0.
    - `[ ]` Configure pytest markers (`@pytest.mark.gke`) to cleanly distinguish between local offline mock tests and live cloud integration runs.
