"""Hub integration router for the Agent Substrate feature.

The Hub auto-discovers this module via ``hub_router`` in feature.yaml and mounts
``router`` under ``/api/features/substrate-basic`` (see showcase_admin/app/features.py).
Each feature owns its own router so its data-plane API is fully independent: adding
or removing the feature adds/removes these endpoints with no edits to Hub core, and
the per-feature mount prefix guarantees features can never collide.

This router is READ-ONLY: it lists the ``ate.dev`` custom resources (WorkerPool +
ActorTemplate) and reads the reconciled worker Deployment so the playroom can show
desired-vs-reconciled state live. It creates and mutates nothing. It reuses only the
Hub's generic plumbing — ``config.MODE`` for the offline guard, ``init_k8s_connection``
for cluster auth, and ``database.get_feature_namespace`` for namespace resolution —
plus the stock ``kubernetes_asyncio`` client. It adds NO helpers to Hub core.
"""

from fastapi import APIRouter, Depends
from kubernetes_asyncio import client
from sqlalchemy.orm import Session

from showcase_admin.app import config, database, k8s_client

router = APIRouter()

FEATURE_NAME = "substrate-basic"

# The ate.dev reconcile CRs this feature declares (see infra/). The ate-controller
# reconciles the WorkerPool into a Deployment named "<workerpool>-deployment", so the
# reconciled worker Deployment is "substrate-basic-deployment" (== feature.yaml
# deployment_name) — reading it IS reading the reconcile result.
ATE_GROUP = "ate.dev"
ATE_VERSION = "v1alpha1"
WORKERPOOL_PLURAL = "workerpools"
ACTORTEMPLATE_PLURAL = "actortemplates"
RECONCILED_DEPLOYMENT = "substrate-basic-deployment"


def _workerpool_view(wp: dict) -> dict:
    """Desired vs. reconciled worker count for one WorkerPool CR."""
    meta = wp.get("metadata", {}) or {}
    spec = wp.get("spec", {}) or {}
    status = wp.get("status", {}) or {}
    return {
        "name": meta.get("name", ""),
        "desiredReplicas": spec.get("replicas"),
        "sandboxClass": spec.get("sandboxClass", "gvisor"),
        "ateomImage": spec.get("ateomImage", ""),
        # status shape is controller-defined and may be absent early in reconcile;
        # surface whatever readiness/replica fields the controller has published.
        "readyReplicas": status.get("readyReplicas"),
        "reconciledReplicas": status.get("replicas"),
        "conditions": status.get("conditions", []),
    }


def _actortemplate_view(at: dict) -> dict:
    """The actor workload declaration bound to the pool's workers."""
    meta = at.get("metadata", {}) or {}
    spec = at.get("spec", {}) or {}
    containers = [
        {"name": c.get("name", ""), "image": c.get("image", "")}
        for c in (spec.get("containers", []) or [])
    ]
    return {
        "name": meta.get("name", ""),
        "pauseImage": spec.get("pauseImage", ""),
        "containers": containers,
        "workerSelector": (spec.get("workerSelector", {}) or {}).get("matchLabels", {}),
    }


def _mock_state() -> dict:
    """Offline reconcile snapshot so the playroom renders without a cluster."""
    return {
        "mode": "MOCK",
        "workerPools": [
            {
                "name": "substrate-basic",
                "desiredReplicas": 2,
                "sandboxClass": "gvisor",
                "ateomImage": "…/ateom-gvisor:latest",
                "readyReplicas": 2,
                "reconciledReplicas": 2,
                "conditions": [{"type": "Ready", "status": "True"}],
            }
        ],
        "actorTemplates": [
            {
                "name": "substrate-basic",
                "pauseImage": "registry.k8s.io/pause:3.10.2",
                "containers": [{"name": "actor", "image": "registry.k8s.io/busybox:1.36"}],
                "workerSelector": {"workload": "substrate-basic"},
            }
        ],
        "reconciledDeployment": {
            "name": RECONCILED_DEPLOYMENT,
            "desiredReplicas": 2,
            "readyReplicas": 2,
            "reconciled": True,
        },
    }


@router.get("/state", summary="Live WorkerPool/Actor reconcile state (read-only)")
async def get_reconcile_state(db: Session = Depends(database.get_db)) -> dict:
    """Return desired-vs-reconciled state: WorkerPool CRs, ActorTemplate CRs, and the
    reconciled worker Deployment. Read-only — lists and reads, never mutates."""
    if config.MODE == "MOCK":
        return _mock_state()

    ns = database.get_feature_namespace(db, FEATURE_NAME)
    await k8s_client.init_k8s_connection()
    async with client.ApiClient() as api_client:
        custom_api = client.CustomObjectsApi(api_client)
        apps_v1 = client.AppsV1Api(api_client)

        wp_resp = await custom_api.list_namespaced_custom_object(
            group=ATE_GROUP, version=ATE_VERSION, namespace=ns, plural=WORKERPOOL_PLURAL,
        )
        at_resp = await custom_api.list_namespaced_custom_object(
            group=ATE_GROUP, version=ATE_VERSION, namespace=ns, plural=ACTORTEMPLATE_PLURAL,
        )

        deployment = {"name": RECONCILED_DEPLOYMENT, "reconciled": False}
        try:
            dep = await apps_v1.read_namespaced_deployment(RECONCILED_DEPLOYMENT, ns)
            ready = getattr(dep.status, "ready_replicas", 0) or 0
            desired = (
                getattr(dep.status, "replicas", None)
                or getattr(dep.spec, "replicas", 0)
                or 0
            )
            deployment = {
                "name": RECONCILED_DEPLOYMENT,
                "desiredReplicas": desired,
                "readyReplicas": ready,
                "reconciled": ready > 0 and ready == desired,
            }
        except client.exceptions.ApiException as e:
            # 404 = the controller has not created the Deployment yet (reconcile in
            # flight). Report not-yet-reconciled rather than erroring the whole view.
            if e.status != 404:
                raise

    return {
        "mode": "REAL",
        "workerPools": [_workerpool_view(w) for w in wp_resp.get("items", [])],
        "actorTemplates": [_actortemplate_view(a) for a in at_resp.get("items", [])],
        "reconciledDeployment": deployment,
    }
