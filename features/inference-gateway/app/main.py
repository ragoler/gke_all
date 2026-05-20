from fastapi import FastAPI, HTTPException, Header, Request, Body
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import os
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GKE Advanced Inference Gateway Standalone Playroom")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

current_dir = Path(__file__).resolve().parent
if (current_dir / "frontend").exists():
    frontend_dir = str(current_dir / "frontend")
else:
    frontend_dir = str(current_dir.parent / "frontend")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="index.html not found.")


class GatewayRequest(BaseModel):
    prompt: str
    priority: Optional[str] = "default"

@app.post("/request")
async def process_gateway_request(
    payload: GatewayRequest, 
    request: Request
):
    header_priority = request.headers.get("X-Inference-Priority")
    effective_priority = header_priority or payload.priority or "default"
    logger.info(f"Processing gateway request with effective priority [{effective_priority.upper()}]: {payload.prompt[:50]}")

    # Return a simulated response demonstrating token-aware load balancing and priority queuing
    reply = (
        f"[GKE INFERENCE GATEWAY (Pod backend)] Token-Aware load balancing routed prompt: '{payload.prompt}' "
        f"via priority queue [{effective_priority.upper()}]."
    )
    return {"reply": reply}
