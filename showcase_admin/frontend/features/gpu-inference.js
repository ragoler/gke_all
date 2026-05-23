// ==============================================================================
// vLLM GPU Inference - Playground Controller (Static / features)
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const chatBox = document.getElementById("chat-box");
    const userInput = document.getElementById("user-input");
    const btnSendQuery = document.getElementById("btn-send-query");
    const metricModelName = document.getElementById("metric-model-name");

    async function fetchWithAuth(url, options = {}) {
        const jwt = localStorage.getItem("admin_jwt");
        const headers = { ...options.headers };
        if (jwt) {
            headers["Authorization"] = `Bearer ${jwt}`;
        }
        return fetch(url, { ...options, headers });
    }

    // Fetch active model info
    async function fetchModelInfo() {
        try {
            const response = await fetchWithAuth("/api/showcases");
            if (response.ok) {
                const showcases = await response.json();
                // Check if we have custom model metadata or custom GCS buckets
                const hasInference = showcases.find(s => s.name === "gpu-inference");
                if (hasInference && hasInference.namespace) {
                    // Load metadata settings if applicable
                }
            }
        } catch (err) {
            console.error("Failed to load model metadata", err);
        }
    }

    // Send Chat message prompt
    window.sendQuery = async () => {
        const text = userInput.value.trim();
        if (!text) return;

        // Append user message
        appendMessage(text, "user");
        userInput.value = "";

        const aiDiv = appendMessage("...", "ai");
        btnSendQuery.disabled = true;

        try {
            const response = await fetchWithAuth("/api/inference/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: text })
            });
            if (!response.ok) throw new Error("Failed to establish connection to model server.");
            const data = await response.json();
            aiDiv.textContent = data.reply;
        } catch (err) {
            aiDiv.textContent = `[ERROR] Completion failed: ${err.message}`;
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

    // Bootstrap Setup
    fetchModelInfo();
});
