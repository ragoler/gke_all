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
        const response = await fetch("/chat", {
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
