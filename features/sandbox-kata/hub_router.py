"""Hub integration router for the Kata / MicroVM Agent Sandbox feature.

The Hub auto-discovers this module via ``hub_router`` in feature.yaml and mounts
``router`` under ``/api/features/sandbox-kata`` (see showcase_admin/app/features.py).
Each feature owns its own router so its data-plane API is fully independent: adding
or removing the feature adds/removes these endpoints with no edits to Hub core, and
the per-feature mount prefix guarantees features can never collide.

The router calls the Hub's shared Kubernetes SDK (``k8s_client``) for generic
plumbing (claim CRUD, gateway resolution, retrying HTTP) and resolves namespaces
through ``database`` — it never imports Hub request-routing or auth internals.
"""

import uuid

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from showcase_admin.app import database, k8s_client

router = APIRouter()

FEATURE_NAME = "sandbox-kata"
VLLM_FEATURE_NAME = "gpu-inference"


@router.get("/sandboxes", summary="List active Kata MicroVM sandbox claims")
async def list_sandbox_claims(db: Session = Depends(database.get_db)) -> list:
    ns = database.get_feature_namespace(db, FEATURE_NAME)
    return await k8s_client.list_sandbox_claims(ns)


@router.post("/sandboxes", summary="Allocate a new isolated sandbox claim")
async def create_sandbox_claim(db: Session = Depends(database.get_db)) -> dict:
    ns = database.get_feature_namespace(db, FEATURE_NAME)
    claim_id = f"sb-{uuid.uuid4().hex[:8]}"
    return await k8s_client.create_sandbox_claim(ns, claim_id)


@router.delete("/sandboxes/{claim_id}", summary="Release a sandbox claim")
async def delete_sandbox_claim(claim_id: str, db: Session = Depends(database.get_db)) -> dict:
    ns = database.get_feature_namespace(db, FEATURE_NAME)
    await k8s_client.delete_sandbox_claim(ns, claim_id)
    return {"status": "released", "id": claim_id}


@router.post("/sandboxes/{claim_id}/message", summary="Send a prompt into a sandbox")
async def message_sandbox(
    claim_id: str,
    body: dict = Body(...),
    db: Session = Depends(database.get_db),
) -> dict:
    ns = database.get_feature_namespace(db, FEATURE_NAME)
    prompt = body.get("message", "")
    provider = body.get("provider", "vertex")  # 'vertex' or 'vllm'
    vllm_ns = database.get_feature_namespace(db, VLLM_FEATURE_NAME)

    reply = await k8s_client.message_sandbox_claim(
        namespace=ns,
        claim_id=claim_id,
        message=prompt,
        provider=provider,
        vllm_namespace=vllm_ns,
    )
    return {"reply": reply}


@router.post("/sandboxes/{claim_id}/quote", summary="Request an inspiring quote from a sandbox")
async def quote_sandbox(
    claim_id: str,
    body: dict = Body(default={"provider": "vertex"}),
    db: Session = Depends(database.get_db),
) -> dict:
    ns = database.get_feature_namespace(db, FEATURE_NAME)
    provider = body.get("provider", "vertex")
    vllm_ns = database.get_feature_namespace(db, VLLM_FEATURE_NAME)

    quote = await k8s_client.quote_sandbox_claim(
        namespace=ns,
        claim_id=claim_id,
        provider=provider,
        vllm_namespace=vllm_ns,
    )
    return {"quote": quote}
