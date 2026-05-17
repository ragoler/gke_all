from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import os
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="vLLM GPU Inference Showcase")

VLLM_API_URL = os.environ.get("VLLM_API_URL", "http://localhost:8000/v1").strip()
MODEL_NAME = os.environ.get("MODEL_NAME", "codegemma-2b").strip()

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>vLLM GPU Playground</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Outfit:wght@400;600;800&display=swap" rel="stylesheet">
        <style>
            body {
                background-color: #090d16;
                color: #f3f4f6;
                font-family: 'Inter', sans-serif;
                margin: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                background-image: radial-gradient(circle at 50% 30%, #131a30 0%, #090d16 70%);
            }
            .chat-container {
                background: rgba(18, 26, 47, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 16px;
                width: 90%;
                max-width: 600px;
                height: 80vh;
                display: flex;
                flex-direction: column;
                backdrop-filter: blur(12px);
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
                overflow: hidden;
            }
            .header {
                padding: 1.25rem;
                border-bottom: 1px solid rgba(255, 255, 255, 0.06);
                font-family: 'Outfit', sans-serif;
                font-size: 1.25rem;
                font-weight: 600;
                color: #00e5ff;
                text-shadow: 0 0 8px rgba(0, 229, 255, 0.2);
            }
            .chat-messages {
                flex-grow: 1;
                padding: 1.5rem;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }
            .message {
                padding: 0.75rem 1.25rem;
                border-radius: 12px;
                max-width: 80%;
                font-size: 0.9rem;
                line-height: 1.4;
            }
            .message.user {
                background: #0088ff;
                color: white;
                align-self: flex-end;
            }
            .message.ai {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.06);
                color: #f3f4f6;
                align-self: flex-start;
            }
            .input-area {
                padding: 1rem;
                border-top: 1px solid rgba(255, 255, 255, 0.06);
                display: flex;
                gap: 0.75rem;
                background: rgba(0,0,0,0.15);
            }
            .input-area input {
                flex-grow: 1;
                background: #0d1322;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                padding: 0.75rem 1rem;
                color: white;
                font-size: 0.9rem;
                outline: none;
            }
            .input-area input:focus {
                border-color: #00e5ff;
            }
            .btn-send {
                background: #00e5ff;
                border: none;
                color: #090d16;
                padding: 0.75rem 1.5rem;
                font-weight: 600;
                border-radius: 8px;
                cursor: pointer;
            }
            .btn-send:hover {
                opacity: 0.9;
            }
        </style>
    </head>
    <body>
        <div class="chat-container">
            <div class="header">vLLM GPU Playground - Model: CodeGemma 2B</div>
            <div class="chat-messages" id="chat-box">
                <div class="message ai">Hello! I am a self-hosted open-source LLM running on GKE Spot GPU nodes. How can I help you today?</div>
            </div>
            <div class="input-area">
                <input type="text" id="user-input" placeholder="Ask me anything..." onkeydown="if(event.key==='Enter') sendMessage()" />
                <button class="btn-send" onclick="sendMessage()">Send</button>
            </div>
        </div>

        <script>
            const chatBox = document.getElementById("chat-box");
            const userInput = document.getElementById("user-input");

            async function sendMessage() {
                const text = userInput.value.trim();
                if (!text) return;

                // Append User message
                appendMessage(text, "user");
                userInput.value = "";

                // Placeholder AI message
                const aiDiv = appendMessage("...", "ai");

                try {
                    const response = await fetch("/inference/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ prompt: text })
                    });
                    
                    if (!response.ok) throw new Error("Model connection failed.");
                    const data = await response.json();
                    aiDiv.textContent = data.reply;
                } catch (err) {
                    aiDiv.textContent = "Error: " + err.message;
                }
                chatBox.scrollTop = chatBox.scrollHeight;
            }

            function appendMessage(content, sender) {
                const div = document.createElement("div");
                div.className = "message " + sender;
                div.textContent = content;
                chatBox.appendChild(div);
                chatBox.scrollTop = chatBox.scrollHeight;
                return div;
            }
        </script>
    </body>
    </html>
    """

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
        return {"reply": "⏳ [STATUS: MODEL LOADING] The NVIDIA L4 GPU is currently downloading model weights or initializing CUDA tensors. Please try again in a few minutes."}
