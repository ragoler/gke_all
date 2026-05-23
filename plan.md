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

### [x] Milestone 8: Refactor GPU Model Inference to Official GKE Tutorial Architecture (Gemma 2B on vLLM)
*   **Objective**: Redesign the `gpu-inference` showcase to match Google Cloud's official production tutorial (`https://cloud.google.com/kubernetes-engine/docs/tutorials/serve-gemma-gpu-vllm`), replacing custom CSI volume mounts with direct Model Garden ID injection and `/dev/shm` IPC memory volumes.
*   **Tasks**:
    - `[x]` Refactor `features/gpu-inference/infra/vllm-deployment.yaml` to use Google Cloud's official prebuilt container (`us-docker.pkg.dev/vertex-ai/vertex-vision-model-garden-dockers/pytorch-vllm-serve:gemma`).
    - `[x]` Add an `emptyDir` volume with `medium: Memory` mounted at `/dev/shm` to provide IPC shared memory for PyTorch tensor processing.
    - `[x]` Inject `MODEL_ID: google/gemma-2b-it` directly into the container environment variables.
    - `[x]` Ensure standalone GKE Gateway API (`gke-l7-gxlb`) and CORS policies remain pristine.
    - `[x]` Author automated unit and mock validation tests confirming correct manifest generation before completion.

### [x] Milestone 9: Live GKE Integration Testing Harness (`test_live_gke.py`)
*   **Objective**: Establish a robust integration testing harness (`tests/integration/test_live_gke.py`) containing 18+ comprehensive tests designed to verify real GKE cluster operations, gateway routing, custom resource allocations, and inter-service DNS hops when `MODE=REAL`.
*   **Architectural Requirements**:
    - Configure pytest with `--run-live-gke` CLI option and `@pytest.mark.gke` marker in `tests/conftest.py`. During standard local runs (`pytest tests/`), live tests will be cleanly skipped. When executed with `pytest --run-live-gke tests/`, pytest dynamically switches `MODE = "REAL"` and connects directly to the active GKE cluster.
*   **Tasks (18 Comprehensive Live Tests)**:
    - `[x]` **System-Level Auditing (10 Tests)**:
        1. `test_gke_control_plane_connection`: Verifies real `kubernetes_asyncio` client connection against GKE control plane.
        2. `test_admin_namespace_exists`: Verifies `gke-showcase-admin` namespace active state.
        3. `test_admin_service_account_rbac`: Verifies `showcase-admin-sa` ClusterRole permissions.
        4. `test_admin_pod_running_status`: Verifies `showcase-admin-deployment` pod is `1/1 Running`.
        5. `test_admin_loadbalancer_service`: Verifies `showcase-admin-svc` external IP assignment.
        6. `test_api_root_html_response`: Verifies `GET /` returns valid glassmorphic SPA HTML.
        7. `test_api_list_showcases_endpoint`: Verifies `GET /api/showcases` returns valid JSON schema.
        8. `test_gke_node_pools_discovery`: Verifies baseline GKE node pool discovery via K8s API.
        9. `test_cluster_autoscaler_health`: Verifies kube-system autoscaler pod readiness.
        10. `test_system_healthz_probes`: Verifies `/healthz` liveness probe response.
    - `[x]` **GKE Agent Sandbox (4 Tests)**:
        11. `test_agent_sandbox_dynamic_deployment`: Audits `POST /deploy` and namespace initialization.
        12. `test_gvisor_node_pool_autoscaling`: Audits `showcase-gvisor-pool` node selector scheduling.
        13. `test_agent_sandbox_message_routing`: Audits `POST /message` routing and WIF Vertex AI fallback.
        14. `test_agent_sandbox_teardown_lock`: Audits `DELETE /teardown` and namespace de-provisioning.
    - `[x]` **vLLM GPU Inference (4 Tests)**:
        15. `test_gpu_inference_dynamic_deployment`: Audits `POST /deploy` and PROVISIONING state transitions.
        16. `test_spot_gpu_node_pool_autoscaling`: Audits Spot L4 GPU node pool scale-up requests.
        17. `test_gpu_inference_multi_container_observability`: Audits `GET /logs` multi-container aggregation.
        18. `test_dual_showcase_inter_routing`: Audits `X-Sandbox-Provider: vllm` internal cluster DNS routing.
    - `[x]` **Execution & Verification**: Run local CI (`pytest tests/`) confirming clean skip, and live verification (`pytest --run-live-gke tests/`) against the active cluster (40/40 passed).

### [x] Milestone 10: Embedded JWT Authentication & HTML Login UI
*   **Objective**: Replace browser basic auth popups with an embedded HTML login card, JWT Bearer token authentication (`POST /api/auth/login`), and clean logout controls.
*   **Architectural Specifications**:
    - **Backend (`showcase_admin`)**: Add `pyjwt>=2.8.0` to `requirements-dev.txt`. Overhaul `auth.py` to issue signed JWT tokens using `JWT_SECRET_KEY` and `HS256` algorithm with 24-hour expiration. Transition `security` dependency from `HTTPBasic` to `HTTPBearer(auto_error=False)`. In `main.py`, unprotect `GET /` to allow unauthenticated browser loading, and author `POST /api/auth/login` validating credentials against `config.ADMIN_USERNAME` / `PASSWORD`.
    - **Frontend (`showcase_admin/frontend`)**: Update `index.html` with a dedicated header container for the Logout button. In `style.css`, author premium cosmic cyberpunk glassmorphic CSS styles for `.login-card`, `.login-header`, `.login-form`, and `.btn-logout`. In `app.js`, implement `localStorage.getItem("admin_jwt")` management, `fetchWithAuth(url, options)` wrappers attaching Bearer tokens to protected API queries, dynamic login screen injection upon HTTP 401, and clean logout click handlers.
    - **Automated Verification (`tests/unit/test_jwt_auth.py`)**: Author robust async unit tests verifying token generation, signature verification, expiration rejection, successful vs failed login routes, and protected API access.
*   **Tasks**:
    - `[x]` Core Backend Authentication Upgrade
        - `[x]` Add `pyjwt>=2.8.0` to `showcase_admin/requirements-dev.txt`.
        - `[x]` Implement JWT encoding/decoding and `HTTPBearer` verification in `showcase_admin/app/auth.py`.
        - `[x]` Unprotect `GET /` and implement `POST /api/auth/login` in `showcase_admin/app/main.py`.
    - `[x]` Premium Frontend SPA UI Upgrade
        - `[x]` Add Logout button container to `showcase_admin/frontend/index.html`.
        - `[x]` Add glassmorphic login card and logout button styles to `showcase_admin/frontend/style.css`.
        - `[x]` Refactor `showcase_admin/frontend/app.js` with `localStorage` token management, auth fetch wrappers, and login screen rendering.
    - `[x]` Automated Testing & Verification
        - `[x]` Author `tests/unit/test_jwt_auth.py` verifying token generation, verification, and API route protection.
        - `[x]` Execute `pytest tests/` confirming 100% passing unit/integration tests.
        - `[x]` Rebuild container (`./scripts/build_and_push.sh --feature admin`) and rollout restart live GKE deployment.
        - `[x]` Update `walkthrough.md` and mark Milestone 10 as completed `[x]` in `plan.md`.

### [x] Milestone 11: Robust Showcase Lifecycle State Synchronization
*   **Objective**: Ensure instantaneous status synchronization during deployment and teardown transitions, adding active K8s readiness and deletion polling loops.
*   **Tasks**:
    - `[x]` Create symlink to master virtual environment.
    - `[x]` Refactor `main.py` to instantly transition `status = "TERMINATING"`.
    - `[x]` Refactor `k8s_client.py` to include active readiness polling in `deploy_showcase` and 404 polling in `teardown_showcase`.
    - `[x]` Update `index.html`, `app.js`, and `style.css` to lock/disable Deploy/Teardown buttons and show a spinning indicator during termination.
    - `[x]` Author automated unit test `/tests/unit/test_lifecycle_sync.py` verifying correct status transitions under mock mode.

### [x] Milestone 11.1: Cloud Gateway Resilience & HTTP 502/503 Retries
*   **Objective**: Ensure backend feature endpoints (`message_sandbox_claim`, `quote_sandbox_claim`, `query_gpu_inference_server`) automatically retry with exponential backoff when encountering temporary GCP Global LoadBalancer 502/503 synchronization errors during NEG initialization.
*   **Tasks**:
    - `[x]` Implement `execute_http_with_retry` helper in `k8s_client.py` to handle exponential backoff retries on HTTP 502, 503, and 504.
    - `[x]` Refactor feature HTTP calls in `k8s_client.py` to use the retry helper.
    - `[x]` Author automated integration test `/tests/unit/test_http_retry.py` verifying mock retry success and backoff behavior.
    - `[x]` Execute automated test suite and verify 100% passing status before completion.

### [x] Milestone 12: Repository Modularization (Approach B)
*   **Objective**: Restructure feature folders to be 100% self-contained, housing both backend manifests and standalone frontend UI assets.
*   **Tasks**:
    - `[x]` Create `features/agent-sandbox/frontend/` and move `showcase_admin/frontend/features/agent-sandbox/*` into it.
    - `[x]` Create `features/gpu-inference/frontend/` and move `showcase_admin/frontend/features/gpu-inference/*` into it.
    - `[x]` Update `showcase_admin/Dockerfile` and `scripts/build_and_push.sh` to dynamically copy `features/*/frontend/` during container compilation.
    - `[x]` Author `/tests/unit/test_modular_build.py` to verify dynamic folder copying and static route mounting.
    - `[x]` Execute automated test suite and verify 100% passing status before completion.

### [x] Milestone 13: Decentralized Gateways & CORS
*   **Objective**: Decouple feature networking by assigning dedicated external Gateway IPs to each deployed showcase and enabling CORS.
*   **Tasks**:
    - `[x]` Add `gateway.yaml` and `http-route.yaml` to `features/agent-sandbox/infra/` and `features/gpu-inference/infra/`.
    - `[x]` Add FastAPI `CORSMiddleware` (`allow_origins=["*"]`) to Sandbox router and GPU inference workloads.
    - `[x]` Update `k8s_client.py` to discover and persist each feature's unique external Gateway IP upon deployment.
    - `[x]` Update `app.js` to route feature playroom interactions directly to the feature's standalone Gateway IP.
    - `[x]` Author `/tests/integration/test_gateway_routing.py` verifying Gateway IP extraction and CORS header presence under mock state.
    - `[x]` Execute automated test suite and verify 100% passing status before completion.

### [x] Milestone 14: Global Cluster Telemetry & Statistics
*   **Objective**: Build a real-time cluster statistics engine querying the Kubernetes API directly for compute, workload, and accelerator metrics.
*   **Tasks**:
    - `[x]` Implement `GET /api/stats` in `main.py` and `k8s_client.py` invoking k8s API object listings (`list_node`, `list_namespace`, `list_pod_for_all_namespaces`).
    - `[x]` Aggregate Node counts, Namespace counts, Pod statuses, and active GPU/gVisor accelerator counts.
    - `[x]` Build a dedicated **Cluster Telemetry** tab in `index.html` and `app.js` displaying live cluster diagnostic health.
    - `[x]` Author `/tests/integration/test_telemetry_api.py` verifying accurate node/workload aggregation and mock API responses.
    - `[x]` Execute automated test suite and verify 100% passing status before completion.

### [x] Milestone 15: Soft Dependencies & Runtime IP Injection
*   **Objective**: Enable showcases to dynamically reference one another via runtime IP injection during deployment.
*   **Tasks**:
    - `[x]` Add LLM provider selection dropdown (Gemini Cloud vs Deployed GPU Inference Gateway IP) to Admin UI deployment modal.
    - `[x]` Pass selected connection string into manifest template rendering (`${LLM_SERVICE_ENDPOINT}`).
    - `[x]` Author `/tests/unit/test_manifest_injection.py` verifying dynamic variable replacement and template expansion.
    - `[x]` Execute automated test suite and verify 100% passing status before completion.

### [x] Milestone 16: Comprehensive Test Suite Expansion & Code Coverage Optimization
*   **Objective**: Significantly expand automated testing across all layers of the repository to achieve >90% test coverage.
*   **Tasks**:
    - `[x]` Install `pytest-cov` to measure test coverage metrics across the virtual environment.
    - `[x]` Expand SQLite database unit tests (`/tests/unit/test_db.py`) to test edge cases (e.g. duplicate showcase names, invalid status transitions).
    - `[x]` Expand GKE mock client tests (`/tests/integration/test_k8s_mock.py`) to simulate API timeouts and gateway resolution fallbacks.
    - `[x]` Author longevity and resilience mock tests simulating repeated deploy/teardown cycles across multiple concurrent showcases.
    - `[x]` Execute full coverage report (`pytest --cov=showcase_admin --cov=features tests/`) and verify >90% code coverage.

### [x] Milestone 17: Refactor GPU Inference Playroom (Separation of Concerns)
*   **Objective**: Eliminate the embedded HTML/CSS/JS string in `features/gpu-inference/app/main.py` by refactoring the UI into standalone frontend assets (`index.html`, `style.css`, `app.js`).
*   **Tasks**:
    - `[x]` Extract hardcoded HTML string from `main.py` and author `features/gpu-inference/frontend/index.html`.
    - `[x]` Extract CSS styles into `features/gpu-inference/frontend/style.css`.
    - `[x]` Extract client-side JavaScript into `features/gpu-inference/frontend/app.js`.
    - `[x]` Refactor `main.py` to mount `StaticFiles` and return `FileResponse("index.html")`.
    - `[x]` Verify standalone UI rendering and REST API communication (`POST /chat`) in local mock environment.

### [x] Milestone 18: Showcase Feature 3 - Advanced GKE Inference Gateway (`inference-gateway`)
*   **Objective**: Introduce a brand new showcase feature (`features/inference-gateway/`) demonstrating Google Cloud's AI-aware GKE Inference Gateway (`llm-d`), providing request priority queueing, token-aware load balancing, and serving criticality as documented at https://docs.cloud.google.com/kubernetes-engine/docs/how-to/deploy-gke-inference-gateway.
*   **Tasks**:
    - `[x]` Package a standalone showcase structure under `features/inference-gateway/` (co-locating `app/`, `frontend/`, and `infra/`).
    - `[x]` Author `InferencePool` manifest (`inference.networking.k8s.io/v1`) referencing the model server target ports and compute configuration.
    - `[x]` Author `InferenceObjective` manifest (`inference.networking.x-k8s.io/v1alpha2`) to configure request priority queueing and serving criticality.
    - `[x]` Author standalone `gateway.yaml` and `http-route.yaml` routing incoming traffic directly to the backend `InferencePool` custom resource.
    - `[x]` Update `AVAILABLE_SHOWCASES` in `main.py` and `k8s_client.py` to register and manage the new `inference-gateway` showcase lifecycle.
    - `[x]` Author `/tests/integration/test_inference_gateway_showcase.py` verifying manifest expansion and CRD handling under mock state.
    - `[x]` Execute automated test suite and verify 100% passing status before completion.

### [x] Milestone 19: Comprehensive Production Bug Fixes & Resilience Hardening
*   **Objective**: Address the 4 critical production issues discovered during live GKE cluster validation, hardening the Admin Hub and showcase feature manifests against RBAC restrictions, async provisioning latencies, and routing dependencies.
*   **Tasks**:
    - `[x]` Remove `dependencies=api_dependencies` from playroom UI serving routes (`/sandbox/`, `/inference/`, `/gateway/`) in `showcase_admin/app/main.py` to allow unauthenticated initial HTML page loads.
    - `[x]` Update `get_cluster_stats()` in `showcase_admin/app/k8s_client.py` to catch `list_node()` 403 RBAC exceptions gracefully, ensuring namespace, pod, and accelerator telemetry aggregation continues flawlessly.
    - `[x]` Update `get_showcase_logs()` in `showcase_admin/app/k8s_client.py` to catch `read_namespaced_pod_log()` 400 BadRequest exceptions during `ContainerCreating` / `Pending` phases, returning a human-readable provisioning status message.
    - `[x]` Correct `features/inference-gateway/infra/deployment.yaml` image path to include `${REGION}-docker.pkg.dev/${PROJECT_NAME}/` for Artifact Registry resolution.
    - `[x]` Rebuild containers (`./scripts/build_and_push.sh --feature inference-gateway` and `--feature admin`) and rollout restart live GKE deployment.
    - `[x]` Verify 100% passing test suite and mark Milestone 19 as completed `[x]` in `plan.md`.

### [ ] Milestone 20: Advanced Client-Side Auth & Gateway RBAC Hardening
*   **Objective**: Address the client-side HTTP 401 failures in standalone playroom JavaScript files by injecting JWT Bearer tokens into REST API fetch requests, and resolve the Kubernetes RBAC 403 Forbidden error during `InferencePool` and `InferenceObjective` CRD deployment by expanding `showcase-admin-sa` permissions in `main-app.yaml`.
*   **Tasks**:
    - `[ ]` Update `showcase_admin/frontend/features/agent-sandbox.js` to retrieve `localStorage.getItem("admin_jwt")` and attach `Authorization: Bearer <jwt>` headers to all `fetch()` calls (`/api/sandboxes`, `/api/sandboxes/{id}`, `/message`, `/quote`).
    - `[ ]` Update `showcase_admin/frontend/features/gpu-inference.js` to attach JWT Bearer headers to `/api/showcases` and `/api/inference/chat` fetch requests.
    - `[ ]` Update `showcase_admin/frontend/features/inference-gateway.js` to attach JWT Bearer headers to `/api/showcases` and `/api/gateway/request` fetch requests.
    - `[ ]` Expand `showcase-admin-role` ClusterRole in `infra/main-app.yaml` to include `apiGroups: ["inference.networking.k8s.io", "inference.networking.x-k8s.io"]` with resources `["inferencepools", "inferenceobjectives"]`.
    - `[ ]` Reapply `infra/main-app.yaml` to the active GKE cluster (`kubectl apply -f infra/main-app.yaml`).
    - `[ ]` Rebuild Admin container (`./scripts/build_and_push.sh --feature admin`) and rollout restart live GKE deployment.
    - `[ ]` Verify 100% passing test suite and mark Milestone 20 as completed `[x]` in `plan.md`.
