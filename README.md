# GKE Feature Showcase Hub

The **GKE Feature Showcase Hub** is a modular, production-grade demonstration platform and administrative hub running on Google Kubernetes Engine (GKE). It serves as an interactive, single-user playground designed to dynamically deploy, experience, and tear down advanced GKE capabilities (e.g., isolated runtime sandboxes, Spot L4 GPU clusters, GCSFuse storage drivers, and Gateway routing policies).

The platform segregates showcases by dynamically provisioning each target feature into its own **dedicated Kubernetes Namespace** with custom namespace inputs, cascading teardown controls, exposed reach-out URLs, and real-time logs/playroom interaction consoles.

To support rapid, zero-cost developer loops, the Showcase Hub includes a comprehensive, offline **Mock Mode** driven by dynamic simulated state engines and an extensive pytest validation suite.

---

## 📂 Repository Directory Structure

The project is structured to be completely modular and plug-and-play:

```
├── README.md                       # Project documentation
├── design.md                       # High-fidelity architectural specifications
├── plan.md                         # Granular milestones and checklists
├── build_infra.sh                  # Master GKE cluster bootstrapper script
├── scripts/
│   └── build_and_push.sh           # Centralized multi-container build and push engine
├── infra/
│   ├── gateway.yaml                # Shared external GKE HTTP Gateway manifest
│   └── main-app.yaml               # Showcase Admin PVC, Service, RBAC, and Deployment
├── showcase_admin/
│   ├── Dockerfile                  # Multi-stage container file for Admin Hub
│   ├── requirements-dev.txt        # Shared python packages requirements
│   ├── app/
│   │   ├── auth.py                 # HTTP Basic Auth security middleware
│   │   ├── config.py               # Precedence environment loaders
│   │   ├── database.py             # Relational SQLite PV storage connector
│   │   ├── k8s_client.py           # Async GKE namespace orchestrator (Mock/Real)
│   │   └── main.py                 # FastAPI backend REST controllers
│   └── frontend/
│       ├── index.html              # Beautiful geometric SPA dashboard
│       ├── style.css               # Modern glassmorphic dark styling sheet
│       └── app.js                  # Client polling and logs console coordinator
├── features/
│   ├── agent-sandbox/              # FEATURE 1: Dynamic gVisor sandbox workload
│   │   ├── demo-app/               # Isolated workload FastAPI container code
│   │   └── infra/                  # SandboxTemplates, WarmPool, Router, and HTTPRoutes
│   └── gpu-inference/              # FEATURE 2: Spot NVIDIA L4 GPU + GCSFuse vLLM model
│       ├── app/                    # Chat playground client container code
│       └── infra/                  # vLLM server deployments, GCSFuse, and Route manifests
└── tests/                          # Automated Testing Suite
    ├── conftest.py                 # Global mock environment parameters
    ├── unit/                       # Unit tests for Config, Auth, and database SQLite CRUD
    └── integration/                # Integration tests for REST APIs and GKE controllers
```

---

## ⚙️ Prerequisites

To run or deploy the Showcase Hub, ensure the following are installed locally:
*   **Python 3.11 or 3.13** (for local testing and development)
*   **Docker** (for compiling container images)
*   **Google Cloud SDK (`gcloud`)** authenticated to your target GCP Project
*   **`kubectl`** installed and mapped to your terminal paths

---

## 💻 Local Development & Mock Mode (Fast Iteration)

You can run the entire Showcase Hub dashboard locally on your workstation without incurring GCP costs or needing a running cluster.

### 1. Setup Local Environment & Virtual Environment
Create a virtual environment and install the required development packages:
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install requirements from standard PyPI index
pip install --index-url https://pypi.org/simple -r showcase_admin/requirements-dev.txt
```

### 2. Configure Environment Settings
Copy `.env.example` to `.env` in the root directory:
```bash
cp .env.example .env
```
Configure the variables:
*   `MODE=MOCK` (enables local offline simulated state loops)
*   `ADMIN_AUTHENTICATION_ENABLED=TRUE` (secures the app behind basic auth)
*   `ADMIN_USERNAME=admin`
*   `ADMIN_PASSWORD=your-mock-pass`

### 3. Launch Uvicorn Server
Run the FastAPI backend locally using Uvicorn:
```bash
uvicorn showcase_admin.app.main:app --reload
```

### 4. Experience and Test!
*   **Dashboard UI**: Open **`http://127.0.0.1:8000/`** in your browser, log in using your credentials, and interact with the showcases! You can input custom namespaces, trigger deployments, view animated state indicators, stream diagnostic logs, and tear features down cleanly.
*   **REST APIs**: Open **`http://127.0.0.1:8000/docs`** to view and execute endpoints dynamically in the interactive Swagger UI.

---

## 🧪 Automated Testing Suite

The Showcase Hub includes a robust pytest suite covering environment loaders, SQLite transactions, auth middlewares, manifest expansion interpolators, and GKE client controllers under mocked states.

To run the entire automated suite inside the virtual environment:
```bash
pytest tests/
```

---

## 🚀 Deploying to Real GKE Cluster

When you are ready to deploy to Google Cloud Platform, follow these steps:

### Step 1: Build and Push Containers (on Build Server / Machine)
Configure `.env` with `MODE=REAL` and your target Artifact Registry configuration. Then, run the centralized build script:
```bash
./scripts/build_and_push.sh
```
*   **What this does**: Automatically creates your Artifact Registry repository if missing, authenticates Docker to GCP, clones the upstream `google-agent-sandbox` repository, compiles all container targets (Showcase Hub Admin, Sandbox Demo workload, Sandbox Router, and GPU Inference Chat Client), and uploads them to GCP.
*   *Optimization*: You can build a specific image using the `--feature` flag (e.g., `./scripts/build_and_push.sh --feature agent-sandbox-demo`).

### Step 2: Bootstrap GKE Cluster & Base Configurations
Run the bootstrapping automation script:
```bash
./build_infra.sh
```
*   **What this does**: 
    1. Provisions a **GKE base Cluster** (with standard node pool for the Admin Hub pod) and Workload Identity enabled.
    2. Enables Gateway API standard controllers and GKE Agent Sandbox add-ons.
    3. Configures Workload Identity IAM bindings linking showcase ServiceAccounts to Vertex AI roles.
    4. Creates a **Persistent Volume Claim (PVC)** backed by standard Persistent Disks.
    5. Deploys the shared **GKE HTTP Gateway** and the **Showcase Admin Dashboard** mapped to PVC storage.
    *   *Note*: Specialized node pools (gVisor and Spot NVIDIA L4 GPU pools) are **not** created here; they are provisioned dynamically when the features are deployed.

### Step 3: Access and Dynamic Showcase Installation
1. Find the external IP address of the shared GKE HTTP Gateway:
   ```bash
   kubectl get gateway external-http-gateway -n gke-showcase-admin
   ```
2. Open the external IP address in your browser and input your configured administrative credentials.
3. **Deploy the GKE Agent Sandbox Showcase**:
   * Input a custom namespace (e.g., `agent-sandbox-playground`) and click **"Deploy"**.
   * The GKE controller will create the namespace, apply SandboxTemplate resources, configure warmpools, mount routers, and route routes.
   * Open the monospaced logs overlay to see standard output logs stream in real-time!
   * Open the playroom console to spawn gVisor-isolated pods under 1 second and toggle calling Gemini cloud APIs or local self-hosted vLLM model endpoints!
4. **Deploy the GPU Model Inference Showcase**:
   * Input a custom namespace (e.g., `vllm-inference-playground`) and click **"Deploy"**.
   * GKE will schedule Spot L4 GPU instances, mount model weight buckets dynamically using GCSFuse, and deploy the completions server.
   * Chat with your model in real-time inside the custom chat playground client playroom!
5. **Tear Down**: Click **"Tear Down Showcase"** to perform a cascading deletion of the namespace and completely free up all cluster compute resources!
