"""Hub integration router for the vLLM GPU Inference feature.

The Hub auto-discovers this module via ``hub_router`` in feature.yaml and mounts
``router`` under ``/api/features/gpu-inference`` (see showcase_admin/app/features.py).
The feature owns its own router, so its chat API is independent of the Hub core and
of every other feature.
"""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from showcase_admin.app import config, database, k8s_client

router = APIRouter()

FEATURE_NAME = "gpu-inference"


# User-facing replies for when the model server is not servable yet. Keyed by Hub status so
# the chat explains *why* it can't answer instead of erroring (the playroom is co-located
# with vLLM in one pod, so on a Spot reclaim both die — only the Hub can report this).
_NOT_READY_REPLIES = {
    "PROVISIONING": "⏳ Provisioning GPU compute and loading the model (~14GB) — please try again shortly.",
    "DEPLOYING": "⏳ The GPU showcase is still deploying — please try again shortly.",
    "REPROVISIONING": "⏳ The GPU was reclaimed (Spot) and is being re-provisioned via the fallback "
                      "compute class. The model will be back in a few minutes.",
}


@router.post("/chat", summary="Run a chat completion against the self-hosted vLLM model")
async def chat(body: dict = Body(...), db: Session = Depends(database.get_db)) -> dict:
    prompt = body.get("prompt", "")
    ns = database.get_feature_namespace(db, FEATURE_NAME)

    # Short-circuit with a clear status message when the backend can't serve yet, rather than
    # firing a request that will fail. ACTIVE falls through to the real inference call. Skipped
    # in MOCK mode, which has no real backend and always returns a simulated reply.
    if config.MODE != "MOCK":
        showcase = db.query(database.ShowcaseModel).filter_by(name=FEATURE_NAME).first()
        status = showcase.status if showcase else "DORMANT"
        if status != "ACTIVE":
            return {"reply": _NOT_READY_REPLIES.get(status, "⏳ The GPU model server is not ready yet — please try again shortly.")}

    reply = await k8s_client.query_gpu_inference_server(ns, prompt)
    return {"reply": reply}
