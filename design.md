# Design Specification: GKE Feature Showcase Hub

## 1. Executive Summary
The **GKE Feature Showcase Hub** is a modular demonstration platform running on Google Kubernetes Engine (GKE). It is designed to run different showcase samples inside the same cluster, providing a hands-on playground of advanced GKE capabilities. 

The platform is **single-user/administrator-driven**—it does not serve multiple end-users creating separate workspace instances. Instead, a single administrator uses the **Showcase Admin Dashboard** (a FastAPI application with a high-fidelity web UI) to selectively build, deploy, interact with, and tear down various technical showcases (e.g., Agent Sandbox, vLLM Inference, Distributed Ray).

To support rapid local developer loops, the architecture includes a first-class **Local/Mock mode** running offline via Docker Compose or local python processes.

---

## 2. Conceptual Architecture & Multi-Sample Topology

The system segregates different showcases in the same cluster by provisioning them into dedicated Kubernetes Namespaces. A single shared gateway handles external traffic routing.

```mermaid
graph TD
    subgraph User Access [User Access]
        Client([Web Browser])
    end

    subgraph GKE Cluster [GKE Showcase Cluster]
        subgraph Gateway Layer [GKE Gateway API]
            CoreGateway[external-http-gateway]
        end

        subgraph Admin Namespace [Namespace: gke-showcase-admin]
            DashboardApp[Showcase Admin FastAPI Backend]
            DashboardUI[Showcase Hub Premium UI]
            LocalDB[(SQLite on Persistent Disk /data/showcase.db)]
            
            DashboardApp --- DashboardUI
            DashboardApp -->|Reads/Writes| LocalDB
        end

        subgraph Sandbox Showcase [Namespace: gke-showcase-sandbox]
            SandboxRouter[Sandbox Router]
            WarmPool[SandboxWarmPool]
            SandboxClaim[Dynamic SandboxClaim]
            SandboxPod[gVisor Sandbox Pod]
            SandboxRouter -->|Routes to| SandboxPod
        end

        subgraph Inference Showcase [Namespace: gke-showcase-inference]
            vLLM[vLLM Model Server]
            GCSFuse[GCS FUSE CSI Driver]
            InferenceGateway[Inference Gateway Routing]
            vLLM --> GCSFuse
            InferenceGateway --> vLLM
        end
    end

    subgraph External Services [Google Cloud Platform]
        VertexAI[Vertex AI / Gemini API]
        ArtifactRegistry[Artifact Registry: gke-showcase-repo]
        GCSWeights[(GCS Model Weights Bucket)]
    end

    %% Routing
    Client -->|HTTP/HTTPS| CoreGateway
    CoreGateway -->|Route: /| DashboardApp
    CoreGateway -->|Route: /sandbox/*| SandboxRouter
    CoreGateway -->|Route: /inference/*| InferenceGateway

    %% Controllers
    DashboardApp -->|K8s API: Orchestrate Namespaces| GKE_Control[GKE Control Plane]
    GKE_Control -->|Deploys/Tears Down| Sandbox Showcase
    GKE_Control -->|Deploys/Tears Down| Inference Showcase

    %% External integrations
    SandboxPod -->|WIF| VertexAI
    vLLM -->|Mount weights| GCSWeights
```

---

## 3. Core Components & Architectural Enhancements

### 3.1. Persistent Database & State Layer
To preserve administrative configuration and state (e.g., which showcases are installed, custom settings, user preferences, audit logs) across pod crashes or cluster restarts, a state layer is integrated.

*   **Storage Media**: SQLite database file (`showcase.db`). SQLite provides a zero-overhead relational schema that fits the single-user, low-throughput requirements perfectly.
*   **GKE Persistence**: 
    *   A `PersistentVolumeClaim` (PVC) named `showcase-admin-pvc` requesting `ReadWriteOnce` storage from the standard GKE Persistent Disk StorageClass (`standard-rwo`).
    *   The GKE node holding the Admin Pod mounts this PD to `/data`.
    *   FastAPI initializes SQLite at `/data/showcase.db`.
    *   If the pod crashes or restarts, GKE remounts the same PD to the replacement pod, guaranteeing full database preservation.
*   **Local Persistence**: In local/mock mode, SQLite writes to a local file path (`./data/showcase.db`), which is git-ignored.

---

### 3.2. Security & Authentication (Future Lock)
To allow the dashboard to be secured in sensitive environments, a simple Basic Authentication guard is architected.

*   **Credentials**: Configuration is loaded directly from the `.env` file:
    ```env
    ADMIN_AUTHENTICATION_ENABLED=TRUE
    ADMIN_USERNAME=admin
    ADMIN_PASSWORD=your-secure-password-12345
    ```
*   **FastAPI Middleware**:
    *   An optional security dependency (`fastapi.security.HTTPBasic`) checks incoming requests.
    *   If `ADMIN_AUTHENTICATION_ENABLED` is `TRUE`, all HTML routing and API endpoints require the matching username and password.
    *   Supports password hashing (e.g., using `passlib` or `bcrypt`) to avoid plain-text memory matching.

---

### 3.3. Test Framework & Automated Testing (`/tests`)
Quality control is managed via an extensive automated testing suite running under `pytest`.

*   **Directory Structure**:
    ```
    /tests
      /unit
        test_auth.py          # Verifies Basic Auth logic and security middleware
        test_config.py        # Verifies environment loader configurations
        test_db.py            # Verifies SQLite migrations and ORM operations
      /integration
        test_api_mock.py      # Verifies FastAPI endpoints using mocked K8s client
        test_k8s_mock.py      # Verifies dynamic manifest rendering and mock deployments
      conftest.py             # Standard Pytest fixtures, FastAPI TestClient initialization
    ```
*   **Mocking Philosophy**: Tests use unit mock bindings (`unittest.mock`) to intercept all calls to the Kubernetes API, ensuring the test suite runs instantly in local environments without a GKE connection.

---

### 3.4. Showcase Modules Specification (`/features`)

#### Feature 1: GKE Agent Sandbox
*   **Goal**: Demonstrate secure runtimes for untrusted code execution (like custom LLM-driven agents).
*   **Deployment Flow**: 
    *   This showcase is **not** deployed during cluster creation. 
    *   The user triggers building the images, and deploys the showcase using the Admin Dashboard.
    *   The shared GKE HTTP Gateway and Workload Identity bindings (Vertex AI role allocations) *are* configured during cluster setup, but the Agent Sandbox custom resources, warmpools, and router are created on-demand in the namespace `gke-showcase-sandbox`.
*   **Details**: Reuses the custom resources (`SandboxTemplate`, `SandboxClaims`, `SandboxWarmPool`) and router architecture adopted from `AgentSandboxExample`.

#### Feature 2: vLLM GPU Model Inference
*   **Goal**: Deploy a small open-source LLM (e.g., Gemma 2B or Llama 3 8B) using vLLM behind an inference routing gateway.
*   **Key GKE Features Illustrated**:
    1.  **GKE Spot GPU Pools**: Uses highly cost-effective Spot NVIDIA L4 GPUs.
    2.  **GKE GCSFuse CSI Driver**: Mounts a Cloud Storage bucket directly to the container to load model weights dynamically without baking them into docker images.
    3.  **Inference Gateway API Route**: Dynamic HTTP routing from the gateway to the inference service.
*   **Architecture**:
    *   *FastAPI Model Server (vLLM)*: Serves standard OpenAI-compatible completion APIs.
    *   *GCS Weights Mount*: High-performance read-only volume mapping of `gs://gke-showcase-weights/gemma-2b-it` to `/data/model`.
    *   *Playground Frontend*: A simple, beautiful chat workspace accessible via `/inference` showing direct token streaming and latency metrics.

---

## 4. Execution Modes

To support both high-speed local coding and real cluster deployments, the system operates in two distinct modes:

| Feature / Dimension | Local / Mock Mode (`MODE=MOCK`) | Real GKE Mode (`MODE=REAL`) |
| :--- | :--- | :--- |
| **Target Environment** | Local Developer PC (macOS/Linux) | Production GKE Cluster |
| **Runtime Tooling** | Uvicorn / Docker Compose | kubectl / gcloud / GKE Gateway |
| **Orchestration Client** | Simulated Python state loops | Asynchronous `kubernetes_asyncio` API |
| **Data Persistence** | Local SQLite file (`./data/showcase.db`) | SQLite on Compute Engine Persistent Disk PVC |
| **External Gateways** | Mocked localhost ports | GKE standard Gateway API |

---

## 5. Infrastructure Setup Script (`build_infra.sh`)

This script handles the bootstrap sequence of the GKE cluster. The first showcase (Agent Sandbox) is left dormant, ready for dynamic user installation:

1.  **Validation**: Reads `.env` parameters and ensures `gcloud` context is set.
2.  **Shared Base Provisioning**:
    *   Creates the GKE Cluster with Workload Identity enabled.
    *   Enables the GKE Gateway API and deploys the central `external-http-gateway`.
    *   Configures the gVisor-enabled node pool (required for Feature 1).
    *   Configures GPU node pools (required for Feature 2).
    *   Configures direct IAM principal bindings for Vertex AI WIF.
3.  **Admin Pod Deployment**:
    *   Deploys the PersistentVolumeClaim (`showcase-admin-pvc`).
    *   Deploys the Showcase Admin Dashboard pod in namespace `gke-showcase-admin`, mounting the persistent disk to `/data`.
    *   Deploys the matching GKE LoadBalancer Service or Gateway route pointing to the Admin pod.
