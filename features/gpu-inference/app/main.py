from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
import os
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="vLLM GPU Inference Showcase")

VLLM_API_URL = os.environ.get("VLLM_API_URL", "http://localhost:8000/v1").strip()
MODEL_NAME = os.environ.get("MODEL_NAME", "codegemma-7b-it").strip()

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


class ChatPayload(BaseModel):
    prompt: str

@app.post("/chat")
async def chat_api(payload: ChatPayload):
    logger.info(f"Received inference request for prompt: {payload.prompt[:50]}...")
    
    try:
        async with httpx.AsyncClient() as client:
            # Call internal vLLM endpoint
            url = f"{VLLM_API_URL.rstrip('/')}/chat/completions"
            body = {
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": payload.prompt}],
                "max_tokens": 200
            }
            response = await client.post(url, json=body, timeout=30.0)
            if response.status_code != 200:
                raise Exception(f"vLLM returned error: {response.text}")
                
            data = response.json()
            reply = data["choices"][0]["message"]["content"].strip()
            return {"reply": reply}
    except Exception as e:
        logger.error(f"Inference failed: {e}")
        # Hardware-agnostic (the CCC fallback may land on L4/G2 or RTX PRO 6000/G4) and honest:
        # this catch-all fires for any backend error, not just weight loading.
        return {"reply": "⏳ The model server is starting up or temporarily unavailable (provisioning / reload). Please try again in a moment."}
