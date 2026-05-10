import asyncio
import os
import re
from datetime import datetime
import yaml
from kubernetes_asyncio import client, config as k8s_config
from showcase_admin.app import config
from showcase_admin.app.database import ShowcaseModel

_k8s_initialized = False

async def init_k8s_connection():
    global _k8s_initialized
    if _k8s_initialized or config.MODE == "MOCK":
        return
    try:
        # Try in-cluster load first (if running on GKE)
        k8s_config.load_incluster_config()
    except Exception:
        # Fallback to kubeconfig (for local real GKE development)
        await k8s_config.load_kube_config()
    _k8s_initialized = True

def expand_template(content: str, vars_dict: dict) -> str:
    pattern = re.compile(r'\$\{([A-Za-z0-9_]+)\}')
    def replacer(match):
        var_name = match.group(1)
        return vars_dict.get(var_name, match.group(0))
    return pattern.sub(replacer, content)

async def apply_yaml_manifests(namespace: str, manifests_content: str):
    # Parse multiple yaml documents
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
                    # Fallback to CustomObjectsApi
                    if "/" in api_version:
                        group, version = api_version.split("/", 1)
                    else:
                        group, version = "", api_version
                        
                    # Resolve plural
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
                # If already exists, skip or log (in production, we could patch or update)
                if e.status == 409:
                    continue
                raise e

# Mock background simulation
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

async def deploy_showcase(name: str, namespace: str, db_session, SessionLocal=None):
    target_ns = namespace.strip() if namespace else f"gke-showcase-{name}"
    
    # Retrieve or create database record
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
        async with client.ApiClient() as api_client:
            core_v1 = client.CoreV1Api(api_client)
            
            # Create dynamic Namespace
            ns_body = client.V1Namespace(metadata=client.V1ObjectMeta(name=target_ns))
            try:
                await core_v1.create_namespace(ns_body)
            except client.exceptions.ApiException as e:
                # 409 means namespace already exists, which is fine
                if e.status != 409:
                    raise e
            
            # Read and apply all manifests under feature/infra directory
            feature_infra_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'features', name, 'infra'
            )
            
            if os.path.exists(feature_infra_dir):
                # Interpolate variables dictionary
                vars_dict = {
                    "PROJECT_NAME": config.PROJECT_NAME,
                    "REGION": config.REGION,
                    "NAMESPACE": target_ns,
                    "GOOGLE_GENAI_USE_VERTEXAI": "TRUE" if config.GOOGLE_GENAI_USE_VERTEXAI else "FALSE"
                }
                
                for filename in sorted(os.listdir(feature_infra_dir)):
                    if filename.endswith(".yaml") or filename.endswith(".yml"):
                        filepath = os.path.join(feature_infra_dir, filename)
                        with open(filepath, 'r') as f:
                            raw_content = f.read()
                        expanded_content = expand_template(raw_content, vars_dict)
                        await apply_yaml_manifests(target_ns, expanded_content)
                        
            # Set status to ACTIVE
            showcase.status = "ACTIVE"
            showcase.reach_out_url = f"/{name}/" if name == "agent-sandbox" else f"/inference/"
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
                # Deleting the namespace automatically cascade deletes all resources inside it
                await core_v1.delete_namespace(namespace)
            except client.exceptions.ApiException as e:
                # If namespace already gone (404), ignore
                if e.status != 404:
                    raise e
    return showcase

async def get_showcase_logs(name: str, namespace: str) -> str:
    if config.MODE == "MOCK":
        return (
            f"[SYSTEM - {datetime.utcnow().isoformat()}] Initializing namespace: {namespace}\n"
            f"[SYSTEM] Validating Pod Security Standards (PSA: restricted)\n"
            f"[DOCKER] Pulling image: showcase-repo/{name}:latest\n"
            f"[DOCKER] Image successfully resolved from Artifact Registry\n"
            f"[KUBERNETES] Creating deployment service resources...\n"
            f"[APP] Running migrations & binding web frameworks...\n"
            f"[SYSTEM] Dynamic GKE routes updated. Ready for connections."
        )
    else:
        await init_k8s_connection()
        async with client.ApiClient() as api_client:
            core_v1 = client.CoreV1Api(api_client)
            try:
                # Get all pods in target namespace
                pods = await core_v1.list_namespaced_pod(namespace)
                if not pods.items:
                    return "No pods found in showcase namespace."
                    
                # Read logs of first active pod found
                target_pod = pods.items[0].metadata.name
                logs = await core_v1.read_namespaced_pod_log(target_pod, namespace, tail_lines=150)
                return logs
            except Exception as e:
                return f"Failed to retrieve live GKE logs: {str(e)}"
