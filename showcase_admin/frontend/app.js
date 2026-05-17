// ==============================================================================
// GKE Feature Showcase Hub - Administrative Client Controller SPA
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    // Local Cache
    let showcasesCache = [];
    let logsPollingInterval = null;

    // DOM Selectors
    const featuresGrid = document.getElementById("features-grid");
    const activeCountMetric = document.getElementById("metric-active-count");
    const clusterModeMetric = document.getElementById("metric-cluster-mode");
    
    const consoleModal = document.getElementById("console-modal");
    const closeConsoleBtn = document.getElementById("close-console-btn");
    const consoleLogStream = document.getElementById("console-log-stream");
    const consoleShowcaseTitle = document.getElementById("console-showcase-title");
    const consoleNamespaceMeta = document.getElementById("console-namespace-meta");
    const refreshLogsBtn = document.getElementById("refresh-logs-btn");

    // Fetch and Render Showcases from Backend REST API
    async function fetchShowcases() {
        try {
            const response = await fetch("/api/showcases");
            if (response.status === 401) {
                // Native basic auth prompt will be requested automatically by browser
                featuresGrid.innerHTML = `<div class="card-skeleton">🔒 Authentication required. Please refresh and enter credentials.</div>`;
                return;
            }
            if (!response.ok) throw new Error("Failed to fetch showcase list.");
            
            const showcases = await response.json();
            showcasesCache = showcases;
            renderFeatures(showcases);
        } catch (err) {
            featuresGrid.innerHTML = `<div class="card-skeleton" style="color: #ff4444;">Error loading showcases: ${err.message}</div>`;
        }
    }

    // Helper to calculate and format elapsed time strings
    function getElapsedTimeString(installedAtStr) {
        if (!installedAtStr) return "";
        const installedAt = new Date(installedAtStr);
        const now = new Date();
        const diffMs = now - installedAt;
        if (diffMs < 0) return "0s";
        
        const totalSecs = Math.floor(diffMs / 1000);
        const mins = Math.floor(totalSecs / 60);
        const secs = totalSecs % 60;
        return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
    }

    // Render dynamic GKE showcases grid
    function renderFeatures(showcases) {
        featuresGrid.innerHTML = "";
        let activeCount = 0;

        showcases.forEach(item => {
            const card = document.createElement("div");
            card.className = "feature-card";

            // Tag list compiler
            let featuresLi = "";
            item.gke_features.forEach(feat => {
                featuresLi += `<li>${feat}</li>`;
            });

            // Dynamic card content template based on deployment status
            let statusControlHtml = "";
            
            if (item.status === "DORMANT") {
                statusControlHtml = `
                    <div class="deployment-config">
                        <div class="input-group">
                            <label for="ns-${item.name}">Target Namespace</label>
                            <input type="text" id="ns-${item.name}" placeholder="Default: gke-showcase-${item.name}" />
                        </div>
                    </div>
                    <button class="btn-deploy" data-name="${item.name}">Deploy Showcase</button>
                `;
            } else {
                activeCount++;
                const statusClass = item.status.toLowerCase();
                
                // Inject dynamic elapsed timer if in DEPLOYING state
                const statusText = item.status === "DEPLOYING" 
                    ? `DEPLOYING (<span class="elapsed-timer" data-start="${item.installed_at}">${getElapsedTimeString(item.installed_at)}</span>)` 
                    : item.status;
                
                statusControlHtml = `
                    <div class="active-panel">
                        <div class="status-row">
                            <span class="status-text">Namespace: <strong>${item.namespace}</strong></span>
                            <span class="status-badge ${statusClass}">${statusText}</span>
                        </div>
                        <div class="action-buttons">
                            <button class="btn-secondary btn-logs" data-name="${item.name}">Logs</button>
                            ${item.status === "ACTIVE" ? `
                                <a href="${item.reach_out_url}" class="btn-secondary">Feature dashboard</a>
                            ` : `
                                <button class="btn-secondary" disabled>${item.status === "TERMINATING" ? "Terminating..." : "Provisioning..."}</button>
                            `}
                        </div>
                        <button class="btn-deploy btn-teardown" data-name="${item.name}" ${item.status === "TERMINATING" ? "disabled style=\"opacity: 0.6; cursor: not-allowed;\"" : ""}>
                            ${item.status === "TERMINATING" ? "<span class=\"spinner\"></span> Terminating..." : "Tear Down Showcase"}
                        </button>
                    </div>
                `;
            }

            card.innerHTML = `
                <span class="card-badge">GKE SHOWCASE</span>
                <h2 class="card-title">${item.title}</h2>
                <p class="card-description">${item.description}</p>
                <ul class="gke-features-list">
                    ${featuresLi}
                </ul>
                ${statusControlHtml}
            `;

            featuresGrid.appendChild(card);
        });

        // Update KPI counters
        activeCountMetric.textContent = activeCount;
        
        // Detect mode from first response cache
        if (showcases.length > 0) {
            // Backend can dynamically pass mode, let's fetch from configuration or use mock mode indicator
            // We will extract a default fallback
            clusterModeMetric.textContent = showcasesCache[0].name ? "HYBRID STATE" : "MOCK";
        }
    }

    // Handle dynamic button clicks
    featuresGrid.addEventListener("click", async (e) => {
        const target = e.target;
        const name = target.getAttribute("data-name");

        if (!name) return;

        if (target.classList.contains("btn-deploy") && !target.classList.contains("btn-teardown")) {
            // Deployment sequence
            const nsInput = document.getElementById(`ns-${name}`);
            const namespaceValue = nsInput ? nsInput.value.strip ? nsInput.value.strip() : nsInput.value.trim() : "";
            
            target.textContent = "Initiating...";
            target.disabled = true;

            try {
                const response = await fetch(`/api/showcases/${name}/deploy`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ namespace: namespaceValue })
                });
                
                if (!response.ok) throw new Error("Failed to initiate deployment.");
                
                await fetchShowcases();
            } catch (err) {
                alert(`Deployment failed: ${err.message}`);
                fetchShowcases();
            }
        } 
        
        else if (target.classList.contains("btn-teardown")) {
            // Teardown sequence

            target.textContent = "Terminating...";
            target.disabled = true;

            try {
                const response = await fetch(`/api/showcases/${name}/teardown`, {
                    method: "DELETE"
                });
                
                if (!response.ok) throw new Error("Failed to tear down showcase.");
                
                await fetchShowcases();
            } catch (err) {
                alert(`Teardown failed: ${err.message}`);
                fetchShowcases();
            }
        } 
        
        else if (target.classList.contains("btn-logs")) {
            // Open console logs modal
            const matchedItem = showcasesCache.find(i => i.name === name);
            if (!matchedItem) return;

            consoleShowcaseTitle.textContent = `${matchedItem.title} Diagnostics`;
            consoleNamespaceMeta.textContent = `Namespace: ${matchedItem.namespace || 'N/A'}`;
            consoleLogStream.textContent = "[SYSTEM] Retrieving live logs...";
            
            // Set current active target on refresh button for quick pulls
            refreshLogsBtn.setAttribute("data-name", name);
            
            consoleModal.classList.add("open");
            await loadLogs(name);
        }
    });

    // Retrieve dynamic container logs from API
    async function loadLogs(name) {
        try {
            const response = await fetch(`/api/showcases/${name}/logs`);
            if (!response.ok) throw new Error("Failed to load diagnostic logs.");
            
            const data = await response.json();
            consoleLogStream.textContent = data.logs;
            
            // Autoscroll to bottom
            consoleLogStream.scrollTop = consoleLogStream.scrollHeight;
        } catch (err) {
            consoleLogStream.textContent = `[ERROR] Log retrieval failed: ${err.message}`;
        }
    }

    // Refresh logs action
    refreshLogsBtn.addEventListener("click", async () => {
        const name = refreshLogsBtn.getAttribute("data-name");
        if (name) {
            consoleLogStream.textContent = "[SYSTEM] Refreshing logs...";
            await loadLogs(name);
        }
    });

    // Close logs modal
    closeConsoleBtn.addEventListener("click", () => {
        consoleModal.classList.remove("open");
    });

    // Auto refresh/polling loop to sync DEPLOYING states
    setInterval(() => {
        const needsSync = showcasesCache.some(item => item.status === "DEPLOYING" || item.status === "TERMINATING");
        if (needsSync) {
            fetchShowcases();
        }
    }, 2000);

    // Active 1s interval updating elapsed timer values in real-time
    setInterval(() => {
        const timers = document.querySelectorAll(".elapsed-timer");
        timers.forEach(t => {
            const startStr = t.getAttribute("data-start");
            if (startStr) {
                t.textContent = getElapsedTimeString(startStr);
            }
        });
    }, 1000);

    // Bootstrap Setup
    fetchShowcases();
});
