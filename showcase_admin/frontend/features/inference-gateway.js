// ==============================================================================
// GKE Advanced Inference Gateway - Playground Controller
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    const chatBox = document.getElementById("chat-box");
    const userInput = document.getElementById("user-input");
    const prioritySelect = document.getElementById("priority-select");
    const btnSendQuery = document.getElementById("btn-send-query");
    const metricGatewayIp = document.getElementById("metric-gateway-ip");

    async function fetchWithAuth(url, options = {}) {
        const jwt = localStorage.getItem("admin_jwt");
        const headers = { ...options.headers };
        if (jwt) {
            headers["Authorization"] = `Bearer ${jwt}`;
        }
        return fetch(url, { ...options, headers });
    }

    async function fetchGatewayInfo() {
        try {
            const response = await fetchWithAuth("/api/showcases");
            if (response.ok) {
                const showcases = await response.json();
                const gatewayMeta = showcases.find(s => s.name === "inference-gateway");
                if (gatewayMeta && gatewayMeta.status === "ACTIVE") {
                    metricGatewayIp.textContent = gatewayMeta.namespace ? `Active in ${gatewayMeta.namespace}` : "Assigned & Active";
                }
            }
        } catch (err) {
            console.error("Failed to load gateway status", err);
        }
    }

    window.sendQuery = async () => {
        const text = userInput.value.trim();
        if (!text) return;

        const priority = prioritySelect.value;
        appendMessage(`[${priority.toUpperCase()}] ${text}`, "user");
        userInput.value = "";

        const aiDiv = appendMessage("...", "ai");
        btnSendQuery.disabled = true;

        try {
            const response = await fetchWithAuth("/api/gateway/request", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: text, priority: priority })
            });
            if (!response.ok) throw new Error("Failed to query Inference Gateway backend.");
            const data = await response.json();
            aiDiv.textContent = data.reply;
        } catch (err) {
            aiDiv.textContent = `[ERROR] Request failed: ${err.message}`;
        } finally {
            btnSendQuery.disabled = false;
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    };

    function appendMessage(content, sender) {
        const div = document.createElement("div");
        div.className = `message ${sender}`;
        div.textContent = content;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        return div;
    }

    fetchGatewayInfo();
});
