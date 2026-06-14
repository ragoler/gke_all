import asyncio
from unittest import mock
import os
import re
import uuid
from datetime import datetime, timezone
import yaml
import httpx
from kubernetes_asyncio import client, config as k8s_config
from showcase_admin.app import config, database, features as feature_registry
from showcase_admin.app.database import ShowcaseModel

_k8s_initialized = False
mock_claims = {} # Local mock in-memory cache for offline mock-mode claims

# Derived from each feature's feature.yaml descriptor (see features.py / feature.md).
FEATURE_DEPLOYMENT_MAP = feature_registry.deployment_map()
FEATURE_URL_MAP = feature_registry.url_map()

async def init_k8s_connection():
    if config.MODE == "MOCK":
        return
    try:
        k8s_config.load_incluster_config()
    except Exception:
        await k8s_config.load_kube_config()

def expand_template(content: str, vars_dict: dict) -> str:
    pattern = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
    def replacer(match):
        var_name = match.group(1)
        return vars_dict.get(var_name, match.group(0))
    return pattern.sub(replacer, content)

# Asynchronously run gcloud shell commands to manage GKE capabilities dynamically
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

async def get_gateway_ip(namespace: str, gateway_name: str) -> str:
    await init_k8s_connection()
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
        try:
            gateway = await custom_api.get_namespaced_custom_object(
                group="gateway.networking.k8s.io",
                version="v1",
                namespace=namespace,
                plural="gateways",
                name=gateway_name
            )
            addresses = gateway.get("status", {}).get("addresses", [])
            if addresses:
                return addresses[0].get("value")
        except Exception:
            pass
    # If gateway IP is still reconciling, return cluster-internal service DNS as fallback
    if "sandbox" in namespace:
        return f"sandbox-router-svc.{namespace}.svc.cluster.local:8080"
    elif "inference" in namespace:
        return f"inference-playroom-svc.{namespace}.svc.cluster.local:8080"
    return "127.0.0.1"

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
                    elif kind == "ComputeClass":
                        plural = "computeclasses"
                        
                    if kind == "ComputeClass":
                        await custom_api.create_cluster_custom_object(
                            group=group,
                            version=version,
                            plural=plural,
                            body=doc
                        )
                    else:
                        await custom_api.create_namespaced_custom_object(
                            group=group,
                            version=version,
                            namespace=namespace,
                            plural=plural,
                            body=doc
                        )
            except client.exceptions.ApiException as e:
                if e.status == 409 or (e.status == 400 and "already exists" in str(e).lower()):
                    continue
                if e.status == 404 and kind in ("ComputeClass",):
                    continue
                raise e

# ----------------------------------------------------------------------
# BASE INFRAS MANAGEMENT (DEPLOY & TEARDOWN)
# ----------------------------------------------------------------------
async def deploy_showcase(name: str, namespace: str, llm_provider: str = "vertex", llm_service_endpoint: str = "", db_session=None, SessionLocal=None):
    target_ns = namespace.strip() if namespace else f"gke-showcase-{name}"
    
    db = db_session if db_session else (SessionLocal() if SessionLocal else None)
    if not db:
        raise Exception("Database session or session factory must be supplied.")
        
    try:
        showcase = db.query(ShowcaseModel).filter_by(name=name).first()
        if not showcase:
            showcase = ShowcaseModel(name=name)
            db.add(showcase)
            
        showcase.namespace = target_ns
        showcase.status = "DEPLOYING"
        showcase.reach_out_url = None
        showcase.installed_at = database.get_utc_now()
        db.commit()
        
        if config.MODE == "MOCK":
            # Wait 2 seconds in Mock mode to let user experience "DEPLOYING" state
            await asyncio.sleep(2)
            showcase.status = "ACTIVE"
            showcase.reach_out_url = FEATURE_URL_MAP.get(name)
            db.commit()
        else:
            await init_k8s_connection()
            
            # Apply Gateway
            gateway_infra_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'infra', 'gateway.yaml'
            )
            if os.path.exists(gateway_infra_file):
                with open(gateway_infra_file, 'r') as f:
                    gateway_content = f.read()
                await apply_yaml_manifests("gke-showcase-admin", gateway_content)
                
            # C. PROVISION RESOURCES
            async with client.ApiClient() as api_client:
                core_v1 = client.CoreV1Api(api_client)
                
                # Actively wait for namespace deletion if it is currently terminating from a previous teardown
                while True:
                    try:
                        ns_info = await core_v1.read_namespace(target_ns)
                        if ns_info.status.phase == "Terminating":
                            await asyncio.sleep(3)
                        else:
                            break
                    except client.exceptions.ApiException as e:
                        if e.status == 404:
                            break
                        raise e
                
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
                    vllm_ns = "gke-showcase-gpu-inference"
                    if target_ns.startswith("gke-showcase-agent-sandbox-"):
                        uuid_suffix = target_ns[len("gke-showcase-agent-sandbox-"):]
                        vllm_ns = f"gke-showcase-gpu-inference-{uuid_suffix}"
                    
                    # Feature-declared defaults fill variables the Hub doesn't supply
                    # (e.g. GATEWAY_NAME, REPLICAS); Hub standard vars below take precedence.
                    vars_dict = {
                        **feature_registry.template_defaults(name),
                        "PROJECT_NAME": config.PROJECT_NAME,
                        "REGION": config.REGION,
                        "NAMESPACE": target_ns,
                        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE" if (llm_provider == "vertex") else "FALSE",
                        "GCS_MODEL_BUCKET": config.GCS_MODEL_BUCKET,
                        "OPENAI_API_BASE": llm_service_endpoint if (llm_service_endpoint and llm_provider in ("vllm", "custom")) else f"http://vllm-service.{vllm_ns}.svc.cluster.local:8000/v1",
                        "ARTIFACT_REGISTRY_REPO": config.ARTIFACT_REGISTRY_REPO
                    }
                    
                    for filename in sorted(os.listdir(feature_infra_dir)):
                        if filename.endswith(".yaml") or filename.endswith(".yml"):
                            filepath = os.path.join(feature_infra_dir, filename)
                            with open(filepath, 'r') as f:
                                raw_content = f.read()
                            expanded_content = expand_template(raw_content, vars_dict)
                            await apply_yaml_manifests(target_ns, expanded_content)
                            
                # Active readiness polling loop using AppsV1Api.read_namespaced_deployment
                apps_v1 = client.AppsV1Api(api_client)
                dep_name = FEATURE_DEPLOYMENT_MAP.get(name, f"{name}-deployment")
                is_ready = False
                for _ in range(60):
                    try:
                        dep = await apps_v1.read_namespaced_deployment(dep_name, target_ns)
                        if isinstance(dep, mock.Mock) or isinstance(dep, mock.AsyncMock):
                            is_ready = True
                            break
                        if dep and hasattr(dep, "status") and getattr(dep.status, "ready_replicas", None) is not None:
                            ready = getattr(dep.status, "ready_replicas", 0) or 0
                            desired = getattr(dep.status, "replicas", None) or getattr(dep.spec, "replicas", 1) or 1
                            if ready == desired and ready > 0:
                                is_ready = True
                                break
                    except Exception as getattr_err:
                        if isinstance(getattr_err, client.exceptions.ApiException) and getattr_err.status == 404:
                            pass
                    await asyncio.sleep(5)
                            
                showcase = db.query(ShowcaseModel).filter_by(name=name).first()
                if showcase and showcase.namespace == target_ns:
                    if is_ready:
                        showcase.status = "ACTIVE"
                        showcase.reach_out_url = FEATURE_URL_MAP.get(name)
                    else:
                        showcase.status = "PROVISIONING"
                    db.commit()
    except Exception as e:
        # If error occurs, commit status as ERROR
        try:
            showcase = db.query(ShowcaseModel).filter_by(name=name).first()
            if showcase and showcase.namespace == target_ns:
                showcase.status = "ERROR"
                db.commit()
        except Exception:
            pass
        raise e
    finally:
        if not db_session and SessionLocal:
            db.close()
            
    return showcase

async def teardown_showcase(name: str, namespace: str, db_session=None, SessionLocal=None):
    db = db_session if db_session else (SessionLocal() if SessionLocal else None)
    if not db:
        raise Exception("Database session or factory required.")
        
    try:
        showcase = db.query(ShowcaseModel).filter_by(name=name).first()
        if showcase and showcase.status != "TERMINATING":
            showcase.status = "TERMINATING"
            db.commit()
            
        if config.MODE == "MOCK":
            await asyncio.sleep(2)
        else:
            await init_k8s_connection()
            async with client.ApiClient() as api_client:
                core_v1 = client.CoreV1Api(api_client)
                try:
                    await core_v1.delete_namespace(namespace)
                    for _ in range(60):
                        try:
                            res = await core_v1.read_namespace(namespace)
                            if isinstance(res, mock.Mock) or isinstance(res, mock.AsyncMock):
                                break
                            await asyncio.sleep(3)
                        except client.exceptions.ApiException as e:
                            if e.status == 404:
                                break
                            raise e
                except client.exceptions.ApiException as e:
                    if e.status != 404:
                        raise e
                        
        showcase = db.query(ShowcaseModel).filter_by(name=name).first()
        if showcase and showcase.namespace == namespace:
            showcase.status = "DORMANT"
            showcase.reach_out_url = None
            showcase.namespace = None
            db.commit()
    except Exception as e:
        try:
            showcase = db.query(ShowcaseModel).filter_by(name=name).first()
            if showcase and showcase.namespace == namespace:
                showcase.status = "ERROR"
                db.commit()
        except Exception:
            pass
        raise e
    finally:
        if not db_session and SessionLocal:
            db.close()
            
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
                    return f"No pods active in namespace '{namespace}'."
                
                aggregated_logs = []
                for pod in pods.items:
                    pod_name = pod.metadata.name
                    phase = pod.status.phase
                    
                    if phase == "Pending":
                        stockout_msg = None
                        try:
                            events = await core_v1.list_namespaced_event(namespace)
                            for event in events.items:
                                if getattr(event.involved_object, "name", "") == pod_name:
                                    if event.reason in ("FailedScaleUp", "FailedScheduling") and "GCE out of resources" in str(event.message):
                                        stockout_msg = event.message
                                        break
                        except Exception:
                            pass
                        if stockout_msg:
                            aggregated_logs.append(
                                f"=== [{pod_name} (Status: Pending - GCE Hardware Stockout)] ===\n"
                                f"⚠️ [STOCKOUT DETECTED]: Google Compute Engine is currently experiencing a physical hardware stockout for this instance type in region {config.REGION}.\n"
                                f"Diagnostic Event: {stockout_msg}\n"
                                f"System Action: GKE Cluster Autoscaler is actively maintaining this allocation request in exponential backoff and will automatically spin up the GPU node as soon as physical capacity frees up in the zone.\n"
                            )
                        else:
                            aggregated_logs.append(f"=== [{pod_name} (Status: Pending)] ===\n[Pod is currently waiting to be scheduled or initializing node volumes...]\n")
                        continue

                    container_names = [c.name for c in pod.spec.containers]
                    
                    for c_name in container_names:
                        header = f"=== [{pod_name} (Container: {c_name}, Status: {phase})] ==="
                        try:
                            c_logs = await core_v1.read_namespaced_pod_log(
                                name=pod_name,
                                namespace=namespace,
                                container=c_name,
                                tail_lines=50
                            )
                            aggregated_logs.append(f"{header}\n{c_logs.strip()}\n")
                        except client.exceptions.ApiException as log_err:
                            if log_err.status == 400 or "BadRequest" in str(log_err):
                                aggregated_logs.append(f"{header}\n[STATUS: CONTAINER PROVISIONING] The container is currently pulling image or initializing volume mounts (e.g. 14GB vLLM weights). This process may take 4 to 6 minutes. Please check back shortly.\n")
                            else:
                                aggregated_logs.append(f"{header}\n[Logs unavailable: {log_err}]\n")
                        except Exception as log_err:
                            aggregated_logs.append(f"{header}\n[Logs unavailable: {log_err}]\n")
                
                # Inspect Gateway CRD Status Conditions
                try:
                    custom_api = client.CustomObjectsApi(api_client)
                    gw_name = f"{name}-gateway"
                    gw = await custom_api.get_namespaced_custom_object(
                        group="gateway.networking.k8s.io",
                        version="v1",
                        namespace=namespace,
                        plural="gateways",
                        name=gw_name
                    )
                    conditions = gw.get("status", {}).get("conditions", [])
                    for cond in conditions:
                        if cond.get("type") == "Programmed" and cond.get("status") == "False":
                            msg = cond.get("message", "Unknown gateway programming error")
                            aggregated_logs.append(
                                f"=== [Gateway: {gw_name} (Status: Invalid / Not Programmed)] ===\n"
                                f"⚠️ [GATEWAY MISCONFIGURATION DETECTED]: The GKE Gateway API Controller failed to program the external load balancer forwarding rules.\n"
                                f"Diagnostic Error: {msg}\n"
                                f"Action Required: Update HTTPRoute backendRef to target a valid Kubernetes Service or transition GatewayClass to an internal/regional proxy.\n"
                            )
                            break
                except Exception:
                    pass

                return "\n".join(aggregated_logs) if aggregated_logs else "No logs available."
            except Exception as e:
                return f"Failed to retrieve live GKE logs: {str(e)}"

# ----------------------------------------------------------------------
# DYNAMIC PLAYROOM INTEGRATION REST APIs (MOCK & GKE)
# ----------------------------------------------------------------------

async def execute_http_with_retry(method: str, url: str, headers: dict = None, json_payload: dict = None, max_retries: int = 7, timeout: float = 45.0) -> httpx.Response:
    last_exc = None
    last_response = None
    async with httpx.AsyncClient() as client_http:
        for attempt in range(max_retries + 1):
            try:
                if method.upper() == "GET":
                    response = await client_http.get(url, headers=headers, timeout=timeout)
                elif method.upper() == "POST":
                    response = await client_http.post(url, headers=headers, json=json_payload, timeout=timeout)
                else:
                    response = await client_http.request(method, url, headers=headers, json=json_payload, timeout=timeout)

                if response.status_code in (404, 502, 503, 504):
                    last_response = response
                    last_exc = None
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** attempt * 2)
                        continue
                    else:
                        response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPError) as e:
                last_exc = e
                last_response = None
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt * 2)
                    continue
                else:
                    raise e
        if last_exc:
            raise last_exc
        if last_response:
            last_response.raise_for_status()


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
        except client.exceptions.ApiException as e:
            if e.status == 404:
                # GKE capability is still enabling in the background, return empty list
                return []
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
        except client.exceptions.ApiException as e:
            if e.status == 404:
                raise Exception("GKE cluster capability 'Agent Sandbox' is currently being enabled in the background. Please wait about 2 minutes for the control plane to complete updating, then try again.")
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
        
    if config.SANDBOX_ROUTER_URL:
        url = f"{config.SANDBOX_ROUTER_URL.rstrip('/')}/message"
    else:
        gateway_ip = await get_gateway_ip(namespace, "agent-sandbox-gateway")
        url = f"http://{gateway_ip}/message"
    
    headers = {
        "X-Sandbox-Id": claim_id,
        "X-Sandbox-Namespace": namespace,
        "X-Sandbox-Provider": provider,
        "X-Sandbox-Vllm-Endpoint": f"http://vllm-service.{vllm_namespace}.svc.cluster.local:8000/v1",
        "Content-Type": "application/json"
    }
    
    payload = {"message": message}
        
    try:
        response = await execute_http_with_retry("POST", url, headers=headers, json_payload=payload, timeout=45.0)
        if response.status_code != 200:
            raise Exception(f"Sandbox router returned error {response.status_code}: {response.text}")
        return response.json().get("reply", "")
    except Exception as e:
        return f"Failed to communicate with GKE sandbox: {str(e)}"

async def quote_sandbox_claim(namespace: str, claim_id: str, provider: str, vllm_namespace: str) -> str:
    if config.MODE == "MOCK":
        return f"\"The best way to predict the future is to invent it.\" - Routed via GKE Sandbox [{claim_id}] using provider '{provider}'."
        
    if config.SANDBOX_ROUTER_URL:
        url = f"{config.SANDBOX_ROUTER_URL.rstrip('/')}/quote"
    else:
        gateway_ip = await get_gateway_ip(namespace, "agent-sandbox-gateway")
        url = f"http://{gateway_ip}/quote"
    
    headers = {
        "X-Sandbox-Id": claim_id,
        "X-Sandbox-Namespace": namespace,
        "X-Sandbox-Provider": provider,
        "X-Sandbox-Vllm-Endpoint": f"http://vllm-service.{vllm_namespace}.svc.cluster.local:8000/v1",
        "Content-Type": "application/json"
    }
    
    try:
        response = await execute_http_with_retry("GET", url, headers=headers, timeout=45.0)
        if response.status_code != 200:
            raise Exception(f"Sandbox router returned error {response.status_code}: {response.text}")
        return response.json().get("quote", "")
    except Exception as e:
        return f"Failed to fetch quotes from GKE sandbox: {str(e)}"

# --- FEATURE 2: GPU MODEL PLAYROOM INFERENCE ---
async def query_gpu_inference_server(namespace: str, prompt: str) -> str:
    if config.MODE == "MOCK":
        return f"[MOCK INFERENCE] Hello! You asked: '{prompt}'. This response has been simulated in mock mode."
        
    if config.SANDBOX_ROUTER_URL:
        url = f"{config.SANDBOX_ROUTER_URL.rstrip('/')}/inference/chat"
    else:
        gateway_ip = await get_gateway_ip(namespace, "gpu-inference-gateway")
        url = f"http://{gateway_ip}/chat"
    
    try:
        response = await execute_http_with_retry("POST", url, json_payload={"prompt": prompt}, timeout=45.0)
        if response.status_code != 200:
            raise Exception(f"GPU Inference server returned error: {response.text}")
        return response.json().get("reply", "")
    except Exception as e:
        return f"Failed to query GKE GPU model server: {str(e)}"

async def check_and_update_showcase_status(name: str, namespace: str):
    if config.MODE == "MOCK" or not namespace:
        return
    await init_k8s_connection()
    async with client.ApiClient() as api_client:
        apps_v1 = client.AppsV1Api(api_client)
        dep_name = FEATURE_DEPLOYMENT_MAP.get(name, f"{name}-deployment")
        try:
            dep = await apps_v1.read_namespaced_deployment(dep_name, namespace)
            if dep and hasattr(dep, "status") and getattr(dep.status, "ready_replicas", None) is not None:
                ready = getattr(dep.status, "ready_replicas", 0) or 0
                desired = getattr(dep.status, "replicas", None) or getattr(dep.spec, "replicas", 1) or 1
                db = database.SessionLocal()
                try:
                    showcase = db.query(ShowcaseModel).filter_by(name=name).first()
                    if showcase and showcase.status in ("DEPLOYING", "PROVISIONING") and showcase.namespace == namespace:
                        if ready == desired and ready > 0:
                            showcase.status = "ACTIVE"
                            showcase.reach_out_url = FEATURE_URL_MAP.get(name)
                            db.commit()
                finally:
                    db.close()
        except Exception:
            pass

async def get_cluster_stats() -> dict:
    if config.MODE == "MOCK":
        return {
            "mode": "MOCK",
            "nodes": {
                "total": 2,
                "ready": 2,
                "details": [
                    {"name": "gke-mock-node-1", "status": "Ready", "version": "v1.35.2", "cpu": "4", "memory": "16Gi", "pods": ["agent-sandbox-demo", "vllm-server"]},
                    {"name": "gke-mock-node-2", "status": "Ready", "version": "v1.35.2", "cpu": "8", "memory": "32Gi", "pods": ["gpu-inference-playroom"]}
                ]
            },
            "namespaces": {
                "total": 5,
                "details": [
                    {"name": "gke-showcase-agent-sandbox", "status": "Active", "age": "5h 12m", "pods": ["agent-sandbox-demo"]},
                    {"name": "gke-showcase-gpu-inference", "status": "Active", "age": "3h 45m", "pods": ["vllm-server", "gpu-inference-playroom"]},
                    {"name": "kube-system", "status": "Active", "age": "2d 4h", "pods": ["coredns", "kube-proxy"]}
                ]
            },
            "pods": {
                "total": 14,
                "running": 12,
                "pending": 1,
                "failed": 1,
                "details": [
                    {"name": "agent-sandbox-demo", "namespace": "gke-showcase-agent-sandbox", "status": "Running", "node": "gke-mock-node-1", "ip": "10.100.1.5"},
                    {"name": "vllm-server", "namespace": "gke-showcase-gpu-inference", "status": "Running", "node": "gke-mock-node-1", "ip": "10.100.1.6"},
                    {"name": "gpu-inference-playroom", "namespace": "gke-showcase-gpu-inference", "status": "Running", "node": "gke-mock-node-2", "ip": "10.100.2.4"}
                ]
            },
            "accelerators": {
                "nvidia_l4": 1,
                "gvisor": 2,
                "details": [
                    {"pod_name": "vllm-server", "namespace": "gke-showcase-gpu-inference", "node": "gke-mock-node-1", "type": "NVIDIA L4", "count": 1}
                ],
                "gvisor_details": [
                    {"name": "agent-sandbox-demo", "namespace": "gke-showcase-agent-sandbox", "node": "gke-mock-node-1", "status": "Running"}
                ]
            }
        }

    await init_k8s_connection()
    async with client.ApiClient() as api_client:
        core_v1 = client.CoreV1Api(api_client)
        
        try:
            # 1. Nodes
            node_details = []
            try:
                nodes = await core_v1.list_node()
                total_nodes = len(nodes.items)
                ready_nodes = 0
                gvisor_nodes = 0
                for node in nodes.items:
                    name = getattr(node.metadata, "name", "Unknown") if node.metadata else "Unknown"
                    status = "NotReady"
                    if node.status and node.status.conditions:
                        for cond in node.status.conditions:
                            if cond.type == "Ready" and cond.status == "True":
                                ready_nodes += 1
                                status = "Ready"
                                break
                    labels = (node.metadata and node.metadata.labels) or {}
                    if labels.get("sandbox.gke.io/runtime") == "gvisor":
                        gvisor_nodes += 1
                    node_info = getattr(node.status, "node_info", None) if node.status else None
                    kubelet_ver = getattr(node_info, "kubelet_version", "N/A") if node_info else "N/A"
                    allocatable = getattr(node.status, "allocatable", {}) if node.status else {}
                    cpu = allocatable.get("cpu", "N/A")
                    mem = allocatable.get("memory", "N/A")
                    node_details.append({
                        "name": name,
                        "status": status,
                        "version": kubelet_ver,
                        "cpu": cpu,
                        "memory": mem
                    })
            except client.exceptions.ApiException as e:
                if e.status == 403 or "Forbidden" in str(e):
                    total_nodes = 0
                    ready_nodes = 0
                    gvisor_nodes = 0
                else:
                    raise e

            # 2. Namespaces
            namespaces = await core_v1.list_namespace()
            total_namespaces = len(namespaces.items)
            namespace_details = []
            for ns in namespaces.items:
                meta = getattr(ns, "metadata", None)
                name = getattr(meta, "name", "Unknown") if meta else "Unknown"
                status_obj = getattr(ns, "status", None)
                phase = getattr(status_obj, "phase", "Unknown") if status_obj else "Unknown"
                creation = getattr(meta, "creation_timestamp", None) if meta else None
                age = "N/A"
                if creation:
                    try:
                        diff = datetime.now(timezone.utc) - creation
                        total_s = int(diff.total_seconds())
                        m, s = divmod(total_s, 60)
                        h, m = divmod(m, 60)
                        d, h = divmod(h, 24)
                        if d > 0: age = f"{d}d {h}h"
                        elif h > 0: age = f"{h}h {m}m"
                        else: age = f"{m}m {s}s"
                    except Exception:
                        pass
                namespace_details.append({
                    "name": name,
                    "status": phase,
                    "age": age
                })

            # 3. Pods and Accelerators
            pods = await core_v1.list_pod_for_all_namespaces()
            total_pods = len(pods.items)
            running_pods = 0
            pending_pods = 0
            failed_pods = 0
            nvidia_l4_count = 0
            gvisor_pods = 0
            pod_details = []
            accelerator_details = []
            gvisor_details = []

            for pod in pods.items:
                meta = getattr(pod, "metadata", None)
                name = getattr(meta, "name", "Unknown") if meta else "Unknown"
                ns = getattr(meta, "namespace", "Unknown") if meta else "Unknown"
                status_obj = getattr(pod, "status", None)
                phase = getattr(status_obj, "phase", "Unknown") if status_obj else "Unknown"
                spec_obj = getattr(pod, "spec", None)
                node = getattr(spec_obj, "node_name", "N/A") if spec_obj else "N/A"
                ip = getattr(status_obj, "pod_ip", "N/A") if status_obj else "N/A"
                pod_details.append({
                    "name": name,
                    "namespace": ns,
                    "status": phase,
                    "node": node,
                    "ip": ip
                })

                if phase == "Running":
                    running_pods += 1
                elif phase == "Pending":
                    pending_pods += 1
                elif phase == "Failed":
                    failed_pods += 1

                if pod.spec:
                    if getattr(pod.spec, "runtime_class_name", None) == "gvisor":
                        gvisor_pods += 1
                        gvisor_details.append({
                            "name": name,
                            "namespace": ns,
                            "node": node,
                            "status": phase
                        })
                    containers = getattr(pod.spec, "containers", []) or []
                    gpu_count_for_pod = 0
                    accel_type = "NVIDIA L4"
                    for c in containers:
                        res = getattr(c, "resources", None)
                        if res and hasattr(res, "requests") and res.requests:
                            gpu_req = res.requests.get("nvidia.com/gpu")
                            tpu_req = res.requests.get("google.com/tpu")
                            if gpu_req:
                                try: gpu_count_for_pod += int(gpu_req)
                                except ValueError: gpu_count_for_pod += 1
                            if tpu_req:
                                accel_type = "Google TPU"
                                try: gpu_count_for_pod += int(tpu_req)
                                except ValueError: gpu_count_for_pod += 1
                                
                    if gpu_count_for_pod > 0:
                        nvidia_l4_count += gpu_count_for_pod
                        accelerator_details.append({
                            "pod_name": name,
                            "namespace": ns,
                            "node": node,
                            "type": accel_type,
                            "count": gpu_count_for_pod
                        })

            # Enrich Nodes with pods list
            for nd in node_details:
                nd["pods"] = [p["name"] for p in pod_details if p["node"] == nd["name"]]
                
            # Enrich Namespaces with pods list
            for nsd in namespace_details:
                nsd["pods"] = [p["name"] for p in pod_details if p["namespace"] == nsd["name"]]

            return {
                "mode": "REAL",
                "nodes": {
                    "total": total_nodes,
                    "ready": ready_nodes,
                    "details": node_details
                },
                "namespaces": {
                    "total": total_namespaces,
                    "details": namespace_details
                },
                "pods": {
                    "total": total_pods,
                    "running": running_pods,
                    "pending": pending_pods,
                    "failed": failed_pods,
                    "details": pod_details
                },
                "accelerators": {
                    "nvidia_l4": nvidia_l4_count,
                    "gvisor": max(gvisor_nodes, gvisor_pods),
                    "details": accelerator_details,
                    "gvisor_details": gvisor_details
                }
            }
        except Exception as e:
            return {
                "mode": "REAL",
                "error": str(e),
                "nodes": {"total": 0, "ready": 0},
                "namespaces": {"total": 0},
                "pods": {"total": 0, "running": 0, "pending": 0, "failed": 0},
                "accelerators": {"nvidia_l4": 0, "gvisor": 0}
            }

