# GKE Feature Showcase Hub

The **GKE Feature Showcase Hub** is a modular, production-grade demonstration platform and administrative hub running on Google Kubernetes Engine (GKE). It serves as an interactive, single-user playground designed to dynamically deploy, experience, and tear down advanced GKE capabilities (e.g., isolated gVisor runtime sandboxes, Spot L4 GPU clusters, GCSFuse storage drivers, and Gateway routing policies).

### Key Architectural Principles
*   **Decentralized Gateways**: Every deployed showcase stands completely by itself. The Showcase Admin Hub has its own Gateway and external IP, and every deployed showcase provisions its own dedicated Kubernetes `Gateway` and external IP. If one feature crashes or is deleted, it has zero impact on other features or the Admin Hub.
*   **Embedded JWT Authentication**: The dashboard features a premium embedded HTML login screen secured by signed OAuth2 / Bearer JWT tokens, completely eliminating native browser popup credential prompts.
*   **Modular Approach B Structure**: Each showcase feature (`/features/<name>/`) is 100% self-contained, co-locating both its backend Kubernetes manifests (`/infra`) and standalone frontend UI assets (`/frontend`).
*   **Cluster Telemetry**: Includes an advanced cluster statistics collector querying the Kubernetes API directly to report live compute nodes, namespaces, workload statuses, and hardware accelerator counts.

To support rapid, zero-cost developer loops, the Showcase Hub includes a comprehensive, offline **Mock Mode** driven by dynamic simulated state engines and an extensive pytest validation suite.

---

## 📂 Repository Directory Structure

The project is structured to be completely modular and plug-and-play:

```
├── README.md                       # Project documentation & setup instructions
├── design.md                       # High-fidelity architectural specifications
├── plan.md                         # Granular milestones and task checklists
├── agent.md                        # Mandatory AI agent operational & quality rules
├── build_infra.sh                  # Master GKE cluster bootstrapper script
├── scripts/
│   └── build_and_push.sh           # Centralized multi-container build and push engine
├── infra/
│   ├── gateway.yaml                # Admin Hub external GKE HTTP Gateway manifest
│   └── main-app.yaml               # Showcase Admin PVC, Service, RBAC, and Deployment
├── showcase_admin/
│   ├── Dockerfile                  # Multi-stage container compiling Admin Hub & UI assets
│   ├── requirements-dev.txt        # Shared python packages requirements
│   ├── app/
│   │   ├── auth.py                 # Embedded JWT authentication & security controllers
│   │   ├── config.py               # Precedence environment loaders
│   │   ├── database.py             # Relational SQLite PV storage connector
│   │   ├── k8s_client.py           # Async GKE namespace orchestrator (Mock/Real)
│   │   └── main.py                 # FastAPI backend REST controllers
│   └── frontend/
│       ├── index.html              # Beautiful geometric SPA dashboard
│       ├── style.css               # Modern glassmorphic dark styling sheet
│       └── app.js                  # Client polling, auth token management, and telemetry
├── features/
│   ├── agent-sandbox/              # FEATURE 1: Dynamic gVisor sandbox workload
│   │   ├── demo-app/               # Isolated workload FastAPI container code
│   │   ├── frontend/               # Standalone Sandbox UI playroom (HTML/CSS/JS)
│   │   └── infra/                  # Standalone Gateway, Route, Template manifests
│   └── gpu-inference/              # FEATURE 2: Spot NVIDIA L4 GPU + GCSFuse vLLM model
│       ├── app/                    # Chat playground client container code
│       ├── frontend/               # Standalone Chat UI playroom (HTML/CSS/JS)
│       └── infra/                  # Standalone Gateway, vLLM Deployment, GCSFuse manifests
└── tests/                          # Automated Testing Suite
    ├── conftest.py                 # Global mock environment parameters
    ├── unit/                       # Unit tests for Config, JWT Auth, and SQLite CRUD
    └── integration/                # Integration tests for REST APIs, Gateways, and Telemetry
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
*   `ADMIN_AUTHENTICATION_ENABLED=TRUE` (secures the app behind embedded JWT auth)
*   `ADMIN_USERNAME=admin`
*   `ADMIN_PASSWORD=your-mock-pass`

### 3. Launch Uvicorn Server
Run the FastAPI backend locally using Uvicorn:
```bash
uvicorn showcase_admin.app.main:app --reload
```

### 4. Experience and Test!
*   **Dashboard UI**: Open **`http://127.0.0.1:8000/`** in your browser. You will be greeted by a centered glassmorphic login card. Log in with your configured credentials to access the main dashboard, view live cluster statistics in the telemetry tab, and deploy showcases!
*   **REST APIs**: Open **`http://127.0.0.1:8000/docs`** to view and execute endpoints dynamically in the interactive Swagger UI.

---

## 🧪 Automated Testing Suite

The Showcase Hub includes a robust pytest suite covering environment loaders, SQLite transactions, JWT issuance, manifest expansion interpolators, Gateway routing, and telemetry aggregation under mocked states.

To run the entire automated suite inside the virtual environment:
```bash
.venv/bin/python3 -m pytest tests/
```

---

## 🚀 Deploying to Real GKE Cluster

When you are ready to deploy to Google Cloud Platform, follow these steps:

### Step 1: Build and Push Containers (on Build Server / Machine)
Configure `.env` with `MODE=REAL` and your target Artifact Registry configuration. Then, run the centralized build script:
```bash
./scripts/build_and_push.sh
```
*   **What this does**: Automatically creates your Artifact Registry repository if missing, authenticates Docker to GCP, compiles all container targets (Showcase Hub Admin, Sandbox Demo workload, Sandbox Router, and GPU Inference Chat Client), copies all feature UI assets into the Admin container, and uploads them to GCP.
*   *Optimization*: You can build a specific image using the `--feature` flag (e.g., `./scripts/build_and_push.sh --feature admin`).

### Step 2: Bootstrap GKE Cluster & Base Configurations
Run the bootstrapping automation script:
```bash
./build_infra.sh
```
*   **What this does**: Provisions a 2-node base GKE cluster for the Admin Hub pod with Workload Identity enabled, deploys the Admin Gateway, and mounts SQLite storage to a PersistentDisk PVC. 
*   *Note*: Specialized node pools (gVisor and Spot L4 GPU pools) are **not** created here; they are provisioned dynamically when individual features are deployed.

### Step 3: Access and Dynamic Showcase Installation
1. Find the external IP address of the Admin Gateway:
   ```bash
   kubectl get gateway external-http-gateway -n gke-showcase-admin
   ```
2. Open the external IP address in your browser and log in using your credentials.
3. **Deploy Showcases**: Input a custom namespace and click **"Deploy"**. GKE will dynamically provision a dedicated external Gateway IP for the feature.
4. **Interact Directly**: Click "Open Showcase" to launch the feature's standalone UI. Browser requests communicate directly with the feature's external Gateway IP.
5. **Tear Down**: Click **"Tear Down Showcase"** to perform a clean, cascading deletion of the feature's namespace and external Gateway, freeing up all compute resources instantly.
