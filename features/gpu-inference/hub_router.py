"""Hub integration router for the vLLM GPU Inference feature.

The Hub auto-discovers this module via ``hub_router`` in feature.yaml and mounts
``router`` under ``/api/features/gpu-inference`` (see showcase_admin/app/features.py).
The feature owns its own router, so its chat API is independent of the Hub core and
of every other feature.
"""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from showcase_admin.app import database, k8s_client

router = APIRouter()

FEATURE_NAME = "gpu-inference"


@router.post("/chat", summary="Run a chat completion against the self-hosted vLLM model")
async def chat(body: dict = Body(...), db: Session = Depends(database.get_db)) -> dict:
    prompt = body.get("prompt", "")
    ns = database.get_feature_namespace(db, FEATURE_NAME)
    reply = await k8s_client.query_gpu_inference_server(ns, prompt)
    return {"reply": reply}
