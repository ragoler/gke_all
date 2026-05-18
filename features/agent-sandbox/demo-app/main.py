import os
import time
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from google import genai
import httpx
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GKE Sandbox Demo Workload")

# Inter-showcase dual model routing check
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "").strip()
MODEL_NAME = os.environ.get("MODEL_NAME", "gemma-2b-it").strip()

# Initialize Gemini Client only if calling cloud API
USE_VERTEXAI = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").upper() == "TRUE"
gemini_client = None

if USE_VERTEXAI:
    try:
        gemini_client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location="us-central1",
        )
        logger.info("Gemini client initialized with Vertex AI (Workload Identity)")
    except Exception as e:
        logger.warning(f"Failed to initialize Vertex AI client: {e}")
else:
    try:
        gemini_client = genai.Client()
        logger.info("Gemini client initialized with local API key")
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini API key client: {e}")
class MessagePayload(BaseModel):
    message: str

@app.post("/message")
async def reply_message(payload: MessagePayload, x_sandbox_id: str = Header(default="UNKNOWN_SANDBOX")):
    logger.info(f"Received message request for sandbox {x_sandbox_id}")
    return {"reply": f"[{x_sandbox_id}] {payload.message}"}

@app.get("/quote")
async def get_quote(x_sandbox_provider: str = Header(default="vertex")):
    logger.info(f"Received request for quote (provider: {x_sandbox_provider})")
    start_time = time.time()
    
    try:
        if OPENAI_API_BASE and x_sandbox_provider.lower() == "vllm":
            # Option 2: Query local self-hosted vLLM service via GKE cluster internal DNS
            logger.info(f"Calling self-hosted vLLM model at {OPENAI_API_BASE}")
            async with httpx.AsyncClient() as http_client:
                payload = {
                    "model": MODEL_NAME,
                    "messages": [{"role": "user", "content": "Provide a short, inspiring quote of the day."}],
                    "max_tokens": 100
                }
                url = f"{OPENAI_API_BASE.rstrip('/')}/chat/completions"
                response = await http_client.post(url, json=payload, timeout=30.0)
                if response.status_code != 200:
                    raise Exception(f"vLLM server returned status {response.status_code}: {response.text}")
                data = response.json()
                quote = data["choices"][0]["message"]["content"].strip()
                logger.info(f"vLLM responded successfully. Took {time.time() - start_time:.2f}s")
                return {"quote": quote}
        else:
            # Option 1: Call Vertex AI Gemini APIs (using WIF/API Key)
            logger.info("Calling Gemini Cloud API generate_content...")
            if not gemini_client:
                raise Exception("Gemini client not initialized.")
                
            loop = asyncio.get_running_loop()
            def call_gemini():
                return gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents="Provide a short, inspiring quote of the day."
                )
            response = await asyncio.wait_for(
                loop.run_in_executor(None, call_gemini),
                timeout=30.0
            )
            logger.info(f"Gemini responded successfully. Took {time.time() - start_time:.2f}s")
            return {"quote": response.text.strip()}
            
    except asyncio.TimeoutError:
        logger.error(f"Request timed out after {time.time() - start_time:.2f}s")
        raise HTTPException(status_code=504, detail="Model request timed out")
    except Exception as e:
        logger.error(f"Error generating quote: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
