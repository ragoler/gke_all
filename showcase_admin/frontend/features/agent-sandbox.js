// ==============================================================================
// GKE Agent Sandbox - Playroom Controller (Static / features)
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    // Local state
    let activeClaims = [];
    let chatHistories = {};

    function escapeHtml(str) {
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    function renderChatHistory(id) {
        if (!chatHistories[id] || chatHistories[id].length === 0) {
            return `<div class="chat-msg ai">[SYSTEM] Isolated secure terminal workspace ready. Send dynamic code/queries instantly.</div>`;
        }
        return chatHistories[id].map(msg => `<div class="chat-msg ${msg.sender}">${escapeHtml(msg.text)}</div>`).join("");
    }
    
    // DOM Elements
    const sandboxGrid = document.getElementById("sandbox-grid");
    const btnClaimSandbox = document.getElementById("btn-claim-sandbox");
    const claimsCountMetric = document.getElementById("metric-claims-count");
    
    // Fetch active claims from Admin backend
    async function fetchClaims() {
        try {
            const response = await fetch("/api/sandboxes");
            if (!response.ok) throw new Error("Failed to load claimed sandboxes.");
            const data = await response.json();
            activeClaims = data;
            renderClaims(data);
        } catch (err) {
            sandboxGrid.innerHTML = `<div class="card-skeleton" style="color: #ff4444;">Error loading sandboxes: ${err.message}</div>`;
        }
    }
    
    // Render dynamic claims list
    function renderClaims(claims) {
        claimsCountMetric.textContent = claims.length;
        
        if (claims.length === 0) {
            sandboxGrid.innerHTML = `<div class="card-skeleton">No active isolated sandboxes claimed. Click allocate to start.</div>`;
            return;
        }
        
        sandboxGrid.innerHTML = "";
        claims.forEach(item => {
            const card = document.createElement("div");
            card.className = "sandbox-item-card";
            
            card.innerHTML = `
                <div class="sandbox-item-header">
                    <span class="sandbox-id-badge">${item.id}</span>
                    <span class="sandbox-state">RUNNING (gVisor)</span>
                </div>
                
                <!-- LLM Provider Select -->
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span class="status-text" style="font-size: 0.8rem; color: var(--text-muted);">LLM Routing Provider:</span>
                    <select class="select-provider" id="provider-${item.id}" data-id="${item.id}">
                        <option value="vertex">Cloud Vertex AI (Gemini)</option>
                        <option value="vllm">Local GKE vLLM Showcase</option>
                    </select>
                </div>
                
                <!-- Chat Playroom window -->
                <div class="sandbox-chat-box" id="chat-box-${item.id}">
                    ${renderChatHistory(item.id)}
                </div>
                
                <!-- Chat input controls -->
                <div class="sandbox-controls">
                    <input type="text" id="input-${item.id}" placeholder="Type sandbox prompt..." onkeydown="if(event.key==='Enter') sendPrompt('${item.id}')" />
                    <button onclick="sendPrompt('${item.id}')" id="btn-send-${item.id}">Run</button>
                </div>
                
                <!-- Secondary controls -->
                <div style="display: flex; gap: 0.5rem; border-top: 1px solid var(--border-standard); padding-top: 0.75rem;">
                    <button class="btn-secondary btn-teardown" onclick="requestQuote('${item.id}')" style="flex-grow: 1; font-size: 0.75rem; padding: 0.4rem;">Get Inspired Quote</button>
                    <button class="btn-secondary btn-teardown" onclick="deleteClaim('${item.id}')" style="background: rgba(239,68,68,0.1); color: #ef4444; font-size: 0.75rem; padding: 0.4rem;">Release Sandbox</button>
                </div>
            `;
            
            sandboxGrid.appendChild(card);
        });
    }
    
    // Claim a new isolated sandbox from warmpool
    btnClaimSandbox.addEventListener("click", async () => {
        btnClaimSandbox.textContent = "Allocating...";
        btnClaimSandbox.disabled = true;
        
        try {
            const response = await fetch("/api/sandboxes", {
                method: "POST"
            });
            if (!response.ok) throw new Error("Failed to allocate sandbox claim.");
            
            await fetchClaims();
        } catch (err) {
            alert(`Allocation failed: ${err.message}`);
        } finally {
            btnClaimSandbox.textContent = "+ Allocate Sandbox Claim (under 0.5s)";
            btnClaimSandbox.disabled = false;
        }
    });
    
    // Delete/Release Sandbox Claim
    window.deleteClaim = async (id) => {
        
        try {
            const response = await fetch(`/api/sandboxes/${id}`, {
                method: "DELETE"
            });
            if (!response.ok) throw new Error("Failed to release sandbox claim.");
            await fetchClaims();
        } catch (err) {
            alert(`Release failed: ${err.message}`);
        }
    };
    
    // Send prompt message to custom sandbox
    window.sendPrompt = async (id) => {
        const inputField = document.getElementById(`input-${id}`);
        const text = inputField.value.trim();
        if (!text) return;
        
        // Append User message
        appendChatMessage(id, text, "user");
        inputField.value = "";
        
        const { div: aiDiv, msgObj: aiMsg } = appendChatMessage(id, "Executing inside gVisor...", "ai");
        const provider = document.getElementById(`provider-${id}`).value;
        
        try {
            const response = await fetch(`/api/sandboxes/${id}/message`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, provider: provider })
            });
            if (!response.ok) throw new Error("Sandbox routing failed.");
            const data = await response.json();
            aiDiv.textContent = data.reply;
            aiMsg.text = data.reply;
        } catch (err) {
            aiDiv.textContent = `[ERROR] Request failed: ${err.message}`;
            aiMsg.text = `[ERROR] Request failed: ${err.message}`;
        }
    };
    
    // Request inspiriting quote from sandbox Gemini / local model
    window.requestQuote = async (id) => {
        const { div: aiDiv, msgObj: aiMsg } = appendChatMessage(id, "Calling sandbox models...", "ai");
        const provider = document.getElementById(`provider-${id}`).value;
        
        try {
            const response = await fetch(`/api/sandboxes/${id}/quote`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider: provider })
            });
            if (!response.ok) throw new Error("Failed to retrieve quotes.");
            const data = await response.json();
            aiDiv.textContent = data.quote;
            aiMsg.text = data.quote;
        } catch (err) {
            aiDiv.textContent = `[ERROR] Model call failed: ${err.message}`;
            aiMsg.text = `[ERROR] Model call failed: ${err.message}`;
        }
    };
    
    function appendChatMessage(id, text, sender) {
        if (!chatHistories[id]) chatHistories[id] = [];
        const msgObj = { text, sender };
        chatHistories[id].push(msgObj);
        
        const chatBox = document.getElementById(`chat-box-${id}`);
        if (!chatBox) return { div: null, msgObj };
        
        const div = document.createElement("div");
        div.className = `chat-msg ${sender}`;
        div.textContent = text;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        return { div, msgObj };
    }
    
    // Initial bootstrap loading
    fetchClaims();
});
