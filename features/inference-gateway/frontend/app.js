const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const prioritySelect = document.getElementById("priority-select");

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    const priority = prioritySelect.value;
    appendMessage(`[${priority.toUpperCase()}] ${text}`, "user");
    userInput.value = "";

    const aiDiv = appendMessage("...", "ai");

    try {
        const response = await fetch("/request", {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                "X-Inference-Priority": priority
            },
            body: JSON.stringify({ prompt: text, priority: priority })
        });
        
        if (!response.ok) throw new Error("Gateway connection failed.");
        const data = await response.json();
        aiDiv.textContent = data.reply;
    } catch (err) {
        aiDiv.textContent = "[ERROR] " + err.message;
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
