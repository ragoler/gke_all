// ==============================================================================
// GKE Agent Sandbox - Playroom Controller (Static / features)
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    // Local state
    let activeClaims = [];
    
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
                    <div class="chat-msg ai">[SYSTEM] Isolated secure terminal workspace ready. Send dynamic code/queries instantly.</div>
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
        if (!confirm(`Are you sure you want to release and destroy sandbox claim '${id}'?`)) return;
        
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
        
        const aiDiv = appendChatMessage(id, "...", "ai");
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
        } catch (err) {
            aiDiv.textContent = `[ERROR] Request failed: ${err.message}`;
        }
    };
    
    // Request inspiriting quote from sandbox Gemini / local model
    window.requestQuote = async (id) => {
        const chatBox = document.getElementById(`chat-box-${id}`);
        const aiDiv = appendChatMessage(id, "Calling sandbox models...", "ai");
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
        } catch (err) {
            aiDiv.textContent = `[ERROR] Model call failed: ${err.message}`;
        }
    };
    
    function appendChatMessage(id, text, sender) {
        const chatBox = document.getElementById(`chat-box-${id}`);
        if (!chatBox) return null;
        
        const div = document.createElement("div");
        div.className = `chat-msg ${sender}`;
        div.textContent = text;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        return div;
    }
    
    // Initial bootstrap loading
    fetchClaims();
});
