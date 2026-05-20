# GKE Feature Showcase Hub: Candidate Features Roadmap

This document provides an analytical survey of advanced capabilities, tutorials, and operational patterns documented in the official Google Kubernetes Engine (GKE) documentation. Each candidate feature is evaluated for architectural feasibility and its strategic value as a modular demonstration showcase within the **GKE Feature Showcase Hub**.

---

## 1. AI/ML & Accelerator Serving

### 1.1. GKE Inference Gateway (`llm-d`)
*   **Official Documentation**: [Deploy GKE Inference Gateway](https://cloud.google.com/kubernetes-engine/docs/how-to/deploy-gke-inference-gateway)
*   **Explanation**: Google Cloud's AI-aware L7 load balancing controller designed specifically for Large Language Model (LLM) model servers. It introduces Custom Resource Definitions (CRDs) such as `InferencePool`, `InferenceObjective`, and `InferenceModelOverride` to manage token-aware load balancing, prompt prefix caching optimization, request priority queuing, and graceful shedding.
*   **Showcase Suitability**: **Highly Recommended (Approved as Milestone 18)**. This is the state-of-the-art networking pattern for production AI on GKE. Introducing this as a dedicated showcase (`features/inference-gateway/`) perfectly complements the baseline vLLM feature by demonstrating advanced AI traffic management and queuing without mutating existing workloads.

---

### 1.2. Distributed AI Ingest & Training with Ray (KubeRay)
*   **Official Documentation**: [Deploy Ray on GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/ray-gke) | [Multislice TPU Training with Ray](https://cloud.google.com/kubernetes-engine/docs/tutorials)
*   **Explanation**: Ray is the industry-standard open-source framework for scaling Python and AI/ML applications across compute clusters. On GKE, the KubeRay operator dynamically spins up Ray head and worker pods across specialized node pools (GPUs or TPUs), enabling multi-node model fine-tuning, distributed embeddings generation, and batch inference.
*   **Showcase Suitability**: **Recommended (Future Phase)**. Excellent candidate to demonstrate distributed multi-node compute. In a single-user Hub environment, a lightweight Ray showcase could deploy KubeRay, spawn a minimal Ray cluster on Spot CPU/GPU nodes, and execute a distributed PyTorch or data processing script inside an interactive web notebook UI.

---

## 2. Batch & Queue Orchestration

### 2.1. Job Queueing & Quota Management with Kueue
*   **Official Documentation**: [Kueue Overview & Setup](https://cloud.google.com/kubernetes-engine/docs/concepts/kueue) | [Dynamic Workload Scheduler](https://cloud.google.com/kubernetes-engine/docs/how-to/dynamic-workload-scheduler)
*   **Explanation**: Kueue is a Kubernetes-native job queueing controller that acts as a resource manager. It intercepts batch workloads (Kubernetes Jobs, RayJobs, JobSets) and holds them in queues until cluster quota (e.g., spot GPU limits) is available. It integrates seamlessly with GKE's **Dynamic Workload Scheduler (DWS)** for queued provisioning of specialized hardware (Flex Start mode).
*   **Showcase Suitability**: **Highly Recommended**. In an experimentation playground, demonstrating how Kueue prevents cluster oversubscription and handles queued GPU provisioning provides immense educational value. The showcase could feature a visual queue dashboard where users dispatch multiple batch AI training jobs and watch Kueue throttle and release them as node capacity scales.

---

### 2.2. Coordinated Multi-Pod Batch Workloads with JobSet
*   **Official Documentation**: [JobSet Concepts](https://cloud.google.com/kubernetes-engine/docs/concepts/jobset)
*   **Explanation**: A Kubernetes API controller designed to group multiple distinct Kubernetes Jobs into a unified single entity. It is critical for distributed AI training (e.g., PyTorch DDP) that requires coordinated startup and failure handling across leader and worker pods. If one worker pod crashes, JobSet can restart the entire distributed training ring.
*   **Showcase Suitability**: **Moderate**. While highly relevant for AI Hypercomputer architectures, it is best implemented as a sub-component alongside the Kueue showcase rather than a standalone feature, demonstrating how Kueue and JobSet manage distributed training jobs together.

---

## 3. Advanced Security & Sandboxing

### 3.1. GKE Agent Sandbox (gVisor Runtime Isolation)
*   **Official Documentation**: [Install GKE Agent Sandbox](https://cloud.google.com/kubernetes-engine/docs/how-to/how-install-agent-sandbox)
*   **Explanation**: Employs Google’s gVisor container runtime (`sandbox.gke.io/runtime: gvisor`) combined with custom CRDs (`SandboxClaim`, `SandboxTemplate`, `SandboxWarmPool`) to provision sub-second, kernel-isolated pod environments. It is explicitly designed to safely execute untrusted, AI-generated code.
*   **Showcase Suitability**: **Already Implemented (Baseline Showcase 1)**. Fully integrated and currently undergoing continuous validation and enhancement within the Hub.

---

### 3.2. Confidential GKE Nodes (Hardware Memory Encryption)
*   **Official Documentation**: [Confidential GKE Nodes](https://cloud.google.com/kubernetes-engine/docs/how-to/confidential-gke-nodes)
*   **Explanation**: Leverages AMD SEV or Intel TDX hardware capabilities to encrypt data in use while it is being processed in RAM. This isolates workloads from the underlying hypervisor and host OS, guaranteeing that cloud administrators or compromised node kernels cannot inspect sensitive data in memory.
*   **Showcase Suitability**: **Selective (Low Priority for Local Hub)**. While highly secure, hardware memory encryption is completely transparent to applications (no visible code or manifest changes other than node pool flags). Because its effects are invisible at the UI layer, it offers limited visual interactivity for a show-and-tell playground.

---

## 4. Storage & Data Persistence

### 4.1. Filestore CSI Driver (Multi-Writer Shared Storage)
*   **Official Documentation**: [Access Filestore from GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/persistent-volumes/filestore-csi-driver)
*   **Explanation**: Mounts Google Cloud Filestore (NFS) instances into GKE pods using the standard CSI driver. Unlike standard PersistentDisks (which are ReadWriteOnce and can only be mounted to one node), Filestore provides `ReadWriteMany` (RWX) access, allowing dozens of pods across different nodes to simultaneously read and write to the same shared file directory.
*   **Showcase Suitability**: **Recommended**. Perfect for demonstrating shared state across distributed workloads (e.g., multi-pod media processing, shared ML checkpoint saving). A showcase could feature a multi-node cluster where separate pods concurrently write logs or images to a shared network mount viewable in real-time.

---

### 4.2. Cloud Storage FUSE CSI Driver
*   **Official Documentation**: [GCS FUSE CSI Driver](https://cloud.google.com/kubernetes-engine/docs/how-to/persistent-volumes/cloud-storage-fuse-csi-driver)
*   **Explanation**: Mounts Google Cloud Storage buckets directly as local file systems inside pods.
*   **Showcase Suitability**: **Already Implemented (Baseline Showcase 2)**. Utilized successfully in our `gpu-inference` showcase to mount large model weights directly from GCS buckets into the vLLM container without requiring massive local persistent disks.

---

## 5. Enterprise Networking & Resiliency

### 5.1. Kubernetes Network Policies (Dataplane V2 / Cilium)
*   **Official Documentation**: [GKE Network Policy](https://cloud.google.com/kubernetes-engine/docs/how-to/network-policy)
*   **Explanation**: Acts as an internal virtual firewall inside the Kubernetes cluster. Leveraging GKE Dataplane V2 (eBPF/Cilium), network policies restrict pod-to-pod communication (ingress and egress) at L3/L4 based on namespace labels and port rules.
*   **Showcase Suitability**: **Recommended**. Excellent security demonstration. A showcase could feature a "Secure Banking App" with Frontend, API, and Database pods. Users could toggle Network Policies on and off in the UI, instantly demonstrating how unauthorized cross-namespace lateral movement is blocked by the GKE dataplane.

---

### 5.2. Multi-Cluster Ingress (MCI)
*   **Official Documentation**: [Multi-Cluster Ingress](https://cloud.google.com/kubernetes-engine/docs/how-to/multi-cluster-ingress)
*   **Explanation**: Manages external HTTP load balancing across multiple GKE clusters spanning different global GCP regions. It routes user traffic to the closest healthy cluster (geo-routing) and provides instant failover if an entire regional cluster experiences an outage.
*   **Showcase Suitability**: **Unsuitable for Single-Cluster Hub**. The Showcase Admin Hub is specifically architected to orchestrate showcases inside a single GKE cluster (`gke-showcase-cluster`). Requiring multi-cluster bootstrapping would introduce extreme cost and operational overhead that violates our single-cluster developer loop principles.

---

## 6. Summary Roadmap & Recommendations Matrix

| Candidate Feature | Tech Category | Strategic Priority | Recommended Action |
| :--- | :--- | :--- | :--- |
| **GKE Inference Gateway** | AI/ML Networking | **High** | Approved for Phase 2 (Milestone 18) |
| **Kueue + DWS** | Batch Scheduling | **High** | Add to Phase 3 Roadmap |
| **Filestore Shared RWX** | Storage / Data | **Medium** | Add to Phase 3 Roadmap |
| **Network Policies** | Security / Net | **Medium** | Add to Phase 3 Roadmap |
| **Ray on GKE** | Distributed AI | **Medium** | Add to Phase 3 Roadmap |
| **Confidential GKE** | Security / Enclaves| **Low** | Monitor (Lacks UI interactivity) |
| **Multi-Cluster Ingress** | Global Networking | **None** | Exclude (Incompatible with single-cluster design) |
