# Control API for the substrate-overcommit playroom. Mounted by the Hub at
# /api/features/substrate-overcommit (see feature.yaml `hub_router`).
#
# Unlike substrate-basic (read-only reconcile viewer), this router MUTATES
# actor state — but only through the real ate control plane: every button in
# the playroom is a gRPC call against ate-api-server (CreateActor /
# SuspendActor / ResumeActor / DeleteActor), scoped to this feature's own
# atespace ("overcommit"). The "touch" endpoint goes through the atenet-router
# data path instead, which transparently resumes a suspended actor on connect.
#
# Auth + transport, matching what install-substrate-overcommit-prereq.sh set up:
#   - TLS: the api-server serves the static openssl-minted leaf whose SANs
#     include api.ate-system.svc; we verify with the CA published in Secret
#     ate-system/servicedns-ca (key trust-bundle.pem).
#   - Bearer: api-server runs --auth-mode=jwt, verifying any K8s SA token from
#     the cluster issuer with audience api.ate-system.svc. We mint one via the
#     TokenRequest API for the `ate-client` SA that ships with ate-install
#     (needs the serviceaccounts/token create rule added to the Hub's
#     ClusterRole in infra/main-app.yaml).
import base64
import os
import sys
import time

# The Hub loads this module via importlib.spec_from_file_location, so the
# feature dir is NOT on sys.path — insert it so the vendored ateapipb stubs
# (generated from upstream pkg/proto/ateapipb/ateapi.proto) import cleanly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import grpc
import httpx
from fastapi import APIRouter, Depends, HTTPException
from kubernetes_asyncio import client
from sqlalchemy.orm import Session

from ateapipb import ateapi_pb2, ateapi_pb2_grpc
from showcase_admin.app import config, database, k8s_client

router = APIRouter()

FEATURE_NAME = "substrate-overcommit"
ATESPACE = "overcommit"
NUM_LANES = 10
WORKER_POOL = "substrate-overcommit"
ATE_API_TARGET = "api.ate-system.svc:443"
ATE_SYSTEM_NS = "ate-system"
ATE_CLIENT_SA = "ate-client"
ATE_API_AUDIENCE = "api.ate-system.svc"
ROUTER_URL = "http://atenet-router.ate-system.svc/"
ACTOR_HOST_SUFFIX = f".{ATESPACE}.actors.resources.substrate.ate.dev"
# Touch may transparently resume a suspended actor (snapshot restore + worker
# bind), which takes tens of seconds — far longer than a plain proxy hop.
TOUCH_TIMEOUT_S = 90.0

_STATUS_NAMES = {
    ateapi_pb2.Actor.STATUS_UNSPECIFIED: "unknown",
    ateapi_pb2.Actor.STATUS_RESUMING: "resuming",
    ateapi_pb2.Actor.STATUS_RUNNING: "running",
    ateapi_pb2.Actor.STATUS_SUSPENDING: "suspending",
    ateapi_pb2.Actor.STATUS_SUSPENDED: "suspended",
    ateapi_pb2.Actor.STATUS_PAUSING: "pausing",
    ateapi_pb2.Actor.STATUS_PAUSED: "paused",
}

_LANES = [f"lane-{i}" for i in range(1, NUM_LANES + 1)]

# Process-lifetime caches. The CA is static (minted once at install); the SA
# token is re-minted before its 1h expiry; the channel + atespace survive for
# the life of the Hub process.
_ca_pem: bytes | None = None
_token: str | None = None
_token_expiry: float = 0.0
_channel: grpc.aio.Channel | None = None
_atespace_ready = False


def _lane_name(lane: int) -> str:
    if not 1 <= lane <= NUM_LANES:
        raise HTTPException(status_code=404, detail=f"lane must be 1..{NUM_LANES}")
    return f"lane-{lane}"


def _require_namespace(db: Session) -> str:
    ns = database.get_feature_namespace(db, FEATURE_NAME)
    if not ns:
        raise HTTPException(status_code=409, detail="feature is not deployed")
    return ns


async def _get_ca_pem() -> bytes:
    global _ca_pem
    if _ca_pem is None:
        await k8s_client.init_k8s_connection()
        async with client.ApiClient() as api_client:
            core = client.CoreV1Api(api_client)
            secret = await core.read_namespaced_secret("servicedns-ca", ATE_SYSTEM_NS)
        _ca_pem = base64.b64decode(secret.data["trust-bundle.pem"])
    return _ca_pem


async def _get_token() -> str:
    global _token, _token_expiry
    now = time.monotonic()
    if _token is None or now >= _token_expiry:
        await k8s_client.init_k8s_connection()
        async with client.ApiClient() as api_client:
            core = client.CoreV1Api(api_client)
            resp = await core.create_namespaced_service_account_token(
                ATE_CLIENT_SA,
                ATE_SYSTEM_NS,
                body=client.AuthenticationV1TokenRequest(
                    spec=client.V1TokenRequestSpec(
                        audiences=[ATE_API_AUDIENCE],
                        expiration_seconds=3600,
                    )
                ),
            )
        _token = resp.status.token
        # Refresh 10 minutes before the 1h expiry.
        _token_expiry = now + 3000
    return _token


async def _get_stub() -> ateapi_pb2_grpc.ControlStub:
    global _channel
    if _channel is None:
        ca = await _get_ca_pem()
        _channel = grpc.aio.secure_channel(
            ATE_API_TARGET,
            grpc.ssl_channel_credentials(root_certificates=ca),
        )
    return ateapi_pb2_grpc.ControlStub(_channel)


async def _auth_metadata() -> tuple:
    token = await _get_token()
    return (("authorization", f"Bearer {token}"),)


async def _ensure_atespace() -> None:
    global _atespace_ready
    if _atespace_ready:
        return
    stub = await _get_stub()
    md = await _auth_metadata()
    try:
        await stub.CreateAtespace(
            ateapi_pb2.CreateAtespaceRequest(name=ATESPACE), metadata=md
        )
    except grpc.aio.AioRpcError as e:
        if e.code() != grpc.StatusCode.ALREADY_EXISTS:
            raise
    _atespace_ready = True


def _actor_ref(lane_name: str) -> ateapi_pb2.ActorRef:
    return ateapi_pb2.ActorRef(atespace=ATESPACE, name=lane_name)


def _grpc_http_error(e: grpc.aio.AioRpcError) -> HTTPException:
    code = e.code()
    if code == grpc.StatusCode.NOT_FOUND:
        return HTTPException(status_code=404, detail=e.details())
    if code == grpc.StatusCode.ALREADY_EXISTS:
        return HTTPException(status_code=409, detail=e.details())
    if code == grpc.StatusCode.FAILED_PRECONDITION:
        return HTTPException(status_code=409, detail=e.details())
    if code == grpc.StatusCode.UNAVAILABLE:
        return HTTPException(status_code=503, detail="ate api-server unavailable")
    return HTTPException(status_code=502, detail=f"{code.name}: {e.details()}")


def _mock_state() -> dict:
    lanes = []
    for i, name in enumerate(_LANES, start=1):
        status = "running" if i <= 2 else ("suspended" if i <= 5 else "absent")
        lanes.append({"lane": i, "name": name, "status": status, "worker_pod": None})
    return {
        "mode": "MOCK",
        "lanes": lanes,
        "meter": {"executions": 5, "workers": 2, "running": 2, "suspended": 3},
        "workers": [],
    }


@router.get("/state")
async def get_state(db: Session = Depends(database.get_db)):
    """Full playroom state: 10 lanes + the overcommit meter."""
    if config.MODE == "MOCK":
        return _mock_state()
    _require_namespace(db)
    await _ensure_atespace()
    stub = await _get_stub()
    md = await _auth_metadata()

    actors = {}
    try:
        page_token = ""
        while True:
            resp = await stub.ListActors(
                ateapi_pb2.ListActorsRequest(
                    page_size=100, page_token=page_token, atespace=ATESPACE
                ),
                metadata=md,
            )
            for actor in resp.actors:
                actors[actor.actor_id] = actor
            page_token = resp.next_page_token
            if not page_token:
                break

        workers_resp = await stub.ListWorkers(
            ateapi_pb2.ListWorkersRequest(), metadata=md
        )
    except grpc.aio.AioRpcError as e:
        raise _grpc_http_error(e)

    workers = [
        {
            "pod": w.worker_pod,
            "node": w.node_name,
            "assignment": (
                w.assignment.actor.name if w.HasField("assignment") else None
            ),
        }
        for w in workers_resp.workers
        if w.worker_pool == WORKER_POOL
    ]

    lanes = []
    n_running = n_suspended = 0
    for i, name in enumerate(_LANES, start=1):
        actor = actors.get(name)
        if actor is None:
            lanes.append(
                {"lane": i, "name": name, "status": "absent", "worker_pod": None}
            )
            continue
        status = _STATUS_NAMES.get(actor.status, "unknown")
        if status in ("running", "resuming", "suspending", "pausing"):
            n_running += 1
        elif status in ("suspended", "paused"):
            n_suspended += 1
        lanes.append(
            {
                "lane": i,
                "name": name,
                "status": status,
                "worker_pod": actor.ateom_pod_name or None,
            }
        )

    return {
        "mode": config.MODE,
        "lanes": lanes,
        "meter": {
            "executions": n_running + n_suspended,
            "workers": len(workers),
            "running": n_running,
            "suspended": n_suspended,
        },
        "workers": workers,
    }


@router.post("/lanes/{lane}/run")
async def run_lane(lane: int, db: Session = Depends(database.get_db)):
    """Create the lane's actor (idempotent — already-exists is OK)."""
    if config.MODE == "MOCK":
        return {"lane": lane, "status": "running", "mock": True}
    name = _lane_name(lane)
    ns = _require_namespace(db)
    await _ensure_atespace()
    stub = await _get_stub()
    md = await _auth_metadata()
    try:
        await stub.CreateActor(
            ateapi_pb2.CreateActorRequest(
                actor_ref=_actor_ref(name),
                actor_template_namespace=ns,
                actor_template_name=FEATURE_NAME,
                worker_selector=ateapi_pb2.Selector(
                    match_labels={"workload": WORKER_POOL}
                ),
            ),
            metadata=md,
        )
    except grpc.aio.AioRpcError as e:
        if e.code() != grpc.StatusCode.ALREADY_EXISTS:
            raise _grpc_http_error(e)
    return {"lane": lane, "name": name, "action": "run"}


@router.post("/lanes/{lane}/suspend")
async def suspend_lane(lane: int, db: Session = Depends(database.get_db)):
    """Suspend the actor to a full snapshot, freeing its worker slot."""
    if config.MODE == "MOCK":
        return {"lane": lane, "status": "suspended", "mock": True}
    name = _lane_name(lane)
    _require_namespace(db)
    stub = await _get_stub()
    md = await _auth_metadata()
    try:
        await stub.SuspendActor(
            ateapi_pb2.SuspendActorRequest(actor_ref=_actor_ref(name)), metadata=md
        )
    except grpc.aio.AioRpcError as e:
        raise _grpc_http_error(e)
    return {"lane": lane, "name": name, "action": "suspend"}


@router.post("/lanes/{lane}/resume")
async def resume_lane(lane: int, db: Session = Depends(database.get_db)):
    """Resume the actor from its snapshot (memory state intact)."""
    if config.MODE == "MOCK":
        return {"lane": lane, "status": "running", "mock": True}
    name = _lane_name(lane)
    _require_namespace(db)
    stub = await _get_stub()
    md = await _auth_metadata()
    try:
        await stub.ResumeActor(
            ateapi_pb2.ResumeActorRequest(actor_ref=_actor_ref(name), boot=False),
            metadata=md,
        )
    except grpc.aio.AioRpcError as e:
        raise _grpc_http_error(e)
    return {"lane": lane, "name": name, "action": "resume"}


@router.post("/lanes/{lane}/touch")
async def touch_lane(
    lane: int, auto_suspend: bool = True, db: Session = Depends(database.get_db)
):
    """Bump the actor's in-RAM counter via the atenet-router data path.

    This is the state-preservation proof: the router proxies to the actor
    (transparently resuming it if suspended), the actor increments its
    in-memory counter and returns {"count": N}. After suspend -> resume the
    count continues the sequence.

    With auto_suspend (the default), the lane is suspended as soon as the
    counter bump completes — the worker slot frees immediately, so rapid
    touches across many lanes show live slot churn on a 2-worker pool.
    The suspend is best-effort: a lane already suspending/deleted doesn't
    fail the touch that succeeded.
    """
    if config.MODE == "MOCK":
        return {"lane": lane, "count": 42, "auto_suspended": auto_suspend, "mock": True}
    name = _lane_name(lane)
    _require_namespace(db)
    host = f"{name}{ACTOR_HOST_SUFFIX}"
    try:
        async with httpx.AsyncClient(timeout=TOUCH_TIMEOUT_S) as http:
            resp = await http.get(ROUTER_URL, headers={"Host": host})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"router request failed: {e}")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"router returned {resp.status_code} for {name}",
        )
    try:
        count = resp.json()["count"]
    except Exception:
        raise HTTPException(
            status_code=502, detail="actor returned a non-counter response"
        )

    auto_suspended = False
    if auto_suspend:
        stub = await _get_stub()
        md = await _auth_metadata()
        try:
            await stub.SuspendActor(
                ateapi_pb2.SuspendActorRequest(actor_ref=_actor_ref(name)),
                metadata=md,
            )
            auto_suspended = True
        except grpc.aio.AioRpcError as e:
            if e.code() not in (
                grpc.StatusCode.FAILED_PRECONDITION,
                grpc.StatusCode.NOT_FOUND,
                grpc.StatusCode.ALREADY_EXISTS,
            ):
                raise _grpc_http_error(e)

    return {"lane": lane, "name": name, "count": count, "auto_suspended": auto_suspended}


@router.delete("/lanes/{lane}")
async def delete_lane(lane: int, db: Session = Depends(database.get_db)):
    """Delete the lane's actor (reset — next run starts the count over)."""
    if config.MODE == "MOCK":
        return {"lane": lane, "status": "absent", "mock": True}
    name = _lane_name(lane)
    _require_namespace(db)
    stub = await _get_stub()
    md = await _auth_metadata()
    try:
        await stub.DeleteActor(
            ateapi_pb2.DeleteActorRequest(actor_ref=_actor_ref(name)), metadata=md
        )
    except grpc.aio.AioRpcError as e:
        if e.code() != grpc.StatusCode.NOT_FOUND:
            raise _grpc_http_error(e)
    return {"lane": lane, "name": name, "action": "delete"}
