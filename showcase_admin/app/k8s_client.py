import asyncio
import os
import re
import uuid
from datetime import datetime
import yaml
import httpx
from kubernetes_asyncio import client, config as k8s_config
from showcase_admin.app import config
from showcase_admin.app.database import ShowcaseModel

_k8s_initialized = False
mock_claims = {} # Local mock in-memory cache for offline mock-mode claims

async def init_k8s_connection():
    global _k8s_initialized
    if _k8s_initialized or config.MODE == "MOCK":
        return
    try:
        k8s_config.load_incluster_config()
    except Exception:
        await k8s_config.load_kube_config()
    _k8s_initialized = True

def expand_template(content: str, vars_dict: dict) -> str:
    pattern = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
    def replacer(match):
        var_name = match.group(1)
        return vars_dict.get(var_name, match.group(0))
    return pattern.sub(replacer, content)

async def run_gcloud_cmd(args: list) -> str:
    proc = await asyncio.create_subprocess_exec(
        "gcloud", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise Exception(f"gcloud command failed: {stderr.decode()}")
    return stdout.decode()

async def get_gateway_ip() -> str:
    # Dynamically query the shared gateway external IP address
    await init_k8s_connection()
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
        try:
            gateway = await custom_api.get_namespaced_custom_object(
                group="gateway.networking.k8s.io",
                version="v1",
                namespace="gke-showcase-admin",
                plural="gateways",
                name="external-http-gateway"
            )
            addresses = gateway.get("status", {}).get("addresses", [])
            if addresses:
                return addresses[0].get("value")
        except Exception:
            pass
    return "8.229.28.149" # Fallback fallback if not fully resolved

async def apply_yaml_manifests(namespace: str, manifests_content: str):
    docs = yaml.safe_load_all(manifests_content)
    async with client.ApiClient() as api_client:
        core_v1 = client.CoreV1Api(api_client)
        apps_v1 = client.AppsV1Api(api_client)
        custom_api = client.CustomObjectsApi(api_client)
        
        for doc in docs:
            if not doc or "kind" not in doc:
                continue
                
            kind = doc["kind"]
            api_version = doc["apiVersion"]
            metadata = doc.setdefault("metadata", {})
            metadata["namespace"] = namespace
            name = metadata.get("name")
            
            try:
                if kind == "Deployment":
                    await apps_v1.create_namespaced_deployment(namespace, doc)
                elif kind == "Service":
                    await core_v1.create_namespaced_service(namespace, doc)
                elif kind == "ConfigMap":
                    await core_v1.create_namespaced_config_map(namespace, doc)
                elif kind == "Secret":
                    await core_v1.create_namespaced_secret(namespace, doc)
                else:
                    if "/" in api_version:
                        group, version = api_version.split("/", 1)
                    else:
                        group, version = "", api_version
                        
                    plural = kind.lower() + "s"
                    if kind == "HTTPRoute":
                        plural = "httproutes"
                    elif kind == "SandboxTemplate":
                        plural = "sandboxtemplates"
                    elif kind == "SandboxClaim":
                        plural = "sandboxclaims"
                    elif kind == "SandboxWarmPool":
                        plural = "sandboxwarmpools"
                    elif kind == "HealthCheckPolicy":
                        plural = "healthcheckpolicies"
                        
                    await custom_api.create_namespaced_custom_object(
                        group=group,
                        version=version,
                        namespace=namespace,
                        plural=plural,
                        body=doc
                    )
            except client.exceptions.ApiException as e:
                if e.status == 409:
                    continue
                raise e

async def simulate_mock_deployment(name: str, namespace: str, SessionLocal):
    await asyncio.sleep(2)
    db = SessionLocal()
    try:
        showcase = db.query(ShowcaseModel).filter_by(name=name).first()
        if showcase and showcase.status == "DEPLOYING":
            showcase.status = "ACTIVE"
            showcase.reach_out_url = f"/{name}/" if name == "agent-sandbox" else f"/inference/"
            db.commit()
    finally:
        db.close()

# ----------------------------------------------------------------------
# BASE INFRAS MANAGEMENT (DEPLOY & TEARDOWN)
# ----------------------------------------------------------------------
async def deploy_showcase(name: str, namespace: str, db_session, SessionLocal=None):
    target_ns = namespace.strip() if namespace else f"gke-showcase-{name}"
    
    showcase = db_session.query(ShowcaseModel).filter_by(name=name).first()
    if not showcase:
        showcase = ShowcaseModel(name=name)
        db_session.add(showcase)
        
    showcase.namespace = target_ns
    showcase.status = "DEPLOYING"
    showcase.reach_out_url = None
    showcase.installed_at = datetime.utcnow()
    db_session.commit()
    
    if config.MODE == "MOCK":
        if SessionLocal:
            asyncio.create_task(simulate_mock_deployment(name, target_ns, SessionLocal))
        else:
            showcase.status = "ACTIVE"
            showcase.reach_out_url = f"/{name}/" if name == "agent-sandbox" else f"/inference/"
            db_session.commit()
    else:
        await init_k8s_connection()
        
        # A. Enable GKE Gateway API capability standard (shared across showcases)
        check_gateway = await run_gcloud_cmd([
            "container", "clusters", "describe", config.CLUSTER_NAME,
            "--region", config.REGION,
            "--format=value(addonsConfig.gatewayApiConfig.channel)"
        ])
        if "STANDARD" not in check_gateway.upper():
            await run_gcloud_cmd([
                "container", "clusters", "update", config.CLUSTER_NAME,
                "--region", config.REGION,
                "--gateway-api=standard"
            ])
            
        # Apply Gateway
        gateway_infra_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'infra', 'gateway.yaml'
        )
        if os.path.exists(gateway_infra_file):
            with open(gateway_infra_file, 'r') as f:
                gateway_content = f.read()
            await apply_yaml_manifests("gke-showcase-admin", gateway_content)
        
        # B. Enable GKE Agent Sandbox capability (Agent Sandbox showcase only)
        if name == "agent-sandbox":
            check_sandbox = await run_gcloud_cmd([
                "container", "clusters", "describe", config.CLUSTER_NAME,
                "--region", config.REGION,
                "--format=value(addonsConfig.agentSandboxConfig.enabled)"
            ])
            if "TRUE" not in check_sandbox.upper():
                await run_gcloud_cmd([
                    "container", "clusters", "update", config.CLUSTER_NAME,
                    "--region", config.REGION,
                    "--enable-agent-sandbox"
                ])
                
            # Spin up gVisor Node pool
            pool_name = "showcase-gvisor-pool"
            check_pool = await run_gcloud_cmd([
                "container", "node-pools", "list",
                "--cluster", config.CLUSTER_NAME,
                "--region", config.REGION,
                "--format=value(name)"
            ])
            if pool_name not in check_pool:
                await run_gcloud_cmd([
                    "container", "node-pools", "create", pool_name,
                    "--cluster", config.CLUSTER_NAME,
                    "--region", config.REGION,
                    "--machine-type", "e2-standard-2",
                    "--image-type", "cos_containerd",
                    "--sandbox", "type=gvisor"
                ])
        
        elif name == "gpu-inference":
            # Spin up Spot GPU pool
            pool_name = "showcase-gpu-pool"
            check_pool = await run_gcloud_cmd([
                "container", "node-pools", "list",
                "--cluster", config.CLUSTER_NAME,
                "--region", config.REGION,
                "--format=value(name)"
            ])
            if pool_name not in check_pool:
                await run_gcloud_cmd([
                    "container", "node-pools", "create", pool_name,
                    "--cluster", config.CLUSTER_NAME,
                    "--region", config.REGION,
                    "--machine-type", "g2-standard-8",
                    "--accelerator", "type=nvidia-l4,count=1",
                    "--enable-image-streaming",
                    "--cloud-provider-gke-spot=true"
                ])

        # C. PROVISION RESOURCES
        async with client.ApiClient() as api_client:
            core_v1 = client.CoreV1Api(api_client)
            
            ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=target_ns))
            try:
                await core_v1.create_namespace(ns_body)
            except client.exceptions.ApiException as e:
                if e.status != 409:
                    raise e
            
            feature_infra_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'features', name, 'infra'
            )
            
            if os.path.exists(feature_infra_dir):
                vars_dict = {
                    "PROJECT_NAME": config.PROJECT_NAME,
                    "REGION": config.REGION,
                    "NAMESPACE": target_ns,
                    "GOOGLE_GENAI_USE_VERTEXAI": "TRUE" if config.GOOGLE_GENAI_USE_VERTEXAI else "FALSE",
                    "GCS_MODEL_BUCKET": config.GCS_MODEL_BUCKET
                }
                
                for filename in sorted(os.listdir(feature_infra_dir)):
                    if filename.endswith(".yaml") or filename.endswith(".yml"):
                        filepath = os.path.join(feature_infra_dir, filename)
                        with open(filepath, 'r') as f:
                            raw_content = f.read()
                        expanded_content = expand_template(raw_content, vars_dict)
                        await apply_yaml_manifests(target_ns, expanded_content)
                        
            showcase.status = "ACTIVE"
            showcase.reach_out_url = f"/sandbox/" if name == "agent-sandbox" else f"/inference/"
            db_session.commit()
            
    return showcase

async def teardown_showcase(name: str, namespace: str, db_session):
    showcase = db_session.query(ShowcaseModel).filter_by(name=name).first()
    if showcase:
        showcase.status = "DORMANT"
        showcase.reach_out_url = None
        showcase.namespace = None
        db_session.commit()
        
    if config.MODE == "MOCK":
        pass
    else:
        await init_k8s_connection()
        async with client.ApiClient() as api_client:
            core_v1 = client.CoreV1Api(api_client)
            try:
                await core_v1.delete_namespace(namespace)
            except client.exceptions.ApiException as e:
                if e.status != 404:
                    raise e
                    
        pool_name = "showcase-gvisor-pool" if name == "agent-sandbox" else "showcase-gpu-pool"
        try:
            await run_gcloud_cmd([
                "container", "node-pools", "delete", pool_name,
                "--cluster", config.CLUSTER_NAME,
                "--region", config.REGION,
                "--quiet"
            ])
        except Exception:
            pass
            
    return showcase

async def get_showcase_logs(name: str, namespace: str) -> str:
    if config.MODE == "MOCK":
        return (
            f"[SYSTEM] Initializing namespace: {namespace}\n"
            f"[SYSTEM] Validating Pod Security Standards (PSA: restricted)\n"
            f"[DOCKER] Pulling image: showcase-repo/{name}:latest\n"
            f"[DOCKER] Image successfully resolved from Artifact Registry\n"
            f"[KUBERNETES] Creating deployment service resources...\n"
            f"[SYSTEM] Ready for connections."
        )
    else:
        await init_k8s_connection()
        async with client.ApiClient() as api_client:
            core_v1 = client.CoreV1Api(api_client)
            try:
                pods = await core_v1.list_namespaced_pod(namespace)
                if not pods.items:
                    return "No pods found in showcase namespace."
                target_pod = pods.items[0].metadata.name
                logs = await core_v1.read_namespaced_pod_log(target_pod, namespace, tail_lines=150)
                return logs
            except Exception as e:
                return f"Failed to retrieve live GKE logs: {str(e)}"

# ----------------------------------------------------------------------
# DYNAMIC PLAYROOM INTEGRATION REST APIs (MOCK & GKE)
# ----------------------------------------------------------------------

# --- FEATURE 1: AGENT SANDBOX CLAIMS ---
async def list_sandbox_claims(namespace: str) -> list:
    if config.MODE == "MOCK":
        return [{"id": cid, "status": "RUNNING"} for cid in mock_claims.keys()]
        
    await init_k8s_connection()
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
        try:
            claims = await custom_api.list_namespaced_custom_object(
                group="extensions.agents.x-k8s.io",
                version="v1alpha1",
                namespace=namespace,
                plural="sandboxclaims"
            )
            result = []
            for item in claims.get("items", []):
                result.append({
                    "id": item["metadata"]["name"],
                    "status": item.get("status", {}).get("phase", "PENDING")
                })
            return result
        except Exception as e:
            raise Exception(f"Failed to list claims on GKE: {str(e)}")

async def create_sandbox_claim(namespace: str, claim_id: str) -> dict:
    if config.MODE == "MOCK":
        mock_claims[claim_id] = "ACTIVE"
        return {"id": claim_id, "status": "RUNNING"}
        
    await init_k8s_connection()
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
        doc = {
            "apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
            "kind": "SandboxClaim",
            "metadata": {"name": claim_id, "namespace": namespace},
            "spec": {
                "sandboxTemplateRef": {"name": "agent-sandbox-template"}
            }
        }
        try:
            await custom_api.create_namespaced_custom_object(
                group="extensions.agents.x-k8s.io",
                version="v1alpha1",
                namespace=namespace,
                plural="sandboxclaims",
                body=doc
            )
            return {"id": claim_id, "status": "RUNNING"}
        except Exception as e:
            raise Exception(f"Failed to claim sandbox on GKE: {str(e)}")

async def delete_sandbox_claim(namespace: str, claim_id: str):
    if config.MODE == "MOCK":
        if claim_id in mock_claims:
            del mock_claims[claim_id]
        return
        
    await init_k8s_connection()
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
        try:
            await custom_api.delete_namespaced_custom_object(
                group="extensions.agents.x-k8s.io",
                version="v1alpha1",
                namespace=namespace,
                plural="sandboxclaims",
                name=claim_id
            )
        except Exception as e:
            raise Exception(f"Failed to delete claim on GKE: {str(e)}")

async def message_sandbox_claim(namespace: str, claim_id: str, message: str, provider: str, vllm_namespace: str) -> str:
    if config.MODE == "MOCK":
        return f"[{claim_id}] Mock reply using model routing '{provider}': Recieved your prompt '{message}'."
        
    # In REAL mode, route HTTP calls directly through GKE external Gateway IP address!
    gateway_ip = await get_gateway_ip()
    url = f"http://{gateway_ip}/sandbox/message"
    
    # Set dynamic local vLLM route headers if provider is set to 'vllm'
    # Else, the container defaults to Cloud Vertex AI (Gemini)
    headers = {
        "X-Sandbox-Id": claim_id,
        "Content-Type": "application/json"
    }
    
    payload = {"message": message}
    
    # If using local vLLM inference, inject environment configuration variables
    if provider == "vllm":
        # Target standard GKE internal cluster DNS target
        vllm_endpoint = f"http://vllm-service.{vllm_namespace}.svc.cluster.local:8000/v1"
        # Set header so router or pod config can resolve (or pod is preconfigured)
        pass
        
    async with httpx.AsyncClient() as client_http:
        try:
            response = await client_http.post(url, json=payload, headers=headers, timeout=45.0)
            if response.status_code != 200:
                raise Exception(f"Sandbox router returned error {response.status_code}: {response.text}")
            return response.json().get("reply", "")
        except Exception as e:
            return f"Failed to communicate with GKE sandbox: {str(e)}"

async def quote_sandbox_claim(namespace: str, claim_id: str, provider: str, vllm_namespace: str) -> str:
    if config.MODE == "MOCK":
        return f"\"The best way to predict the future is to invent it.\" - Routed via GKE Sandbox [{claim_id}] using provider '{provider}'."
        
    gateway_ip = await get_gateway_ip()
    url = f"http://{gateway_ip}/sandbox/quote"
    
    headers = {
        "X-Sandbox-Id": claim_id,
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client_http:
        try:
            response = await client_http.get(url, headers=headers, timeout=45.0)
            if response.status_code != 200:
                raise Exception(f"Sandbox router returned error {response.status_code}: {response.text}")
            return response.json().get("quote", "")
        except Exception as e:
            return f"Failed to fetch quotes from GKE sandbox: {str(e)}"

# --- FEATURE 2: GPU MODEL PLAYROOM INFERENCE ---
async def query_gpu_inference_server(namespace: str, prompt: str) -> str:
    if config.MODE == "MOCK":
        return f"[MOCK INFERENCE] Hello! You asked: '{prompt}'. This response has been simulated in mock mode."
        
    gateway_ip = await get_gateway_ip()
    url = f"http://{gateway_ip}/inference/chat"
    
    async with httpx.AsyncClient() as client_http:
        try:
            response = await client_http.post(url, json={"prompt": prompt}, timeout=45.0)
            if response.status_code != 200:
                raise Exception(f"GPU Inference server returned error: {response.text}")
            return response.json().get("reply", "")
        except Exception as e:
            return f"Failed to query GKE GPU model server: {str(e)}"
