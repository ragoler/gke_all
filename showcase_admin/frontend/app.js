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
    
    const loginModal = document.getElementById("login-modal");
    const loginForm = document.getElementById("login-form");
    const loginErrorMessage = document.getElementById("login-error-message");
    const btnLogout = document.getElementById("btn-logout");

    // Fetch wrapper attaching JWT authorization header
    async function fetchWithAuth(url, options = {}) {
        const token = localStorage.getItem("admin_jwt");
        const headers = { ...(options.headers || {}) };
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }
        const newOptions = { ...options, headers };
        const response = await fetch(url, newOptions);
        
        if (response.status === 401) {
            if (loginModal) {
                loginModal.style.display = "flex";
                loginModal.classList.add("open");
            }
            if (btnLogout) btnLogout.style.display = "none";
        } else {
            if (token && btnLogout && loginModal && !loginModal.classList.contains("open")) {
                btnLogout.style.display = "block";
            }
        }
        return response;
    }

    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const usernameInput = document.getElementById("login-username");
            const passwordInput = document.getElementById("login-password");
            
            try {
                const res = await fetch("/api/auth/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        username: usernameInput.value,
                        password: passwordInput.value
                    })
                });
                
                if (res.ok) {
                    const data = await res.json();
                    localStorage.setItem("admin_jwt", data.access_token);
                    if (loginModal) {
                        loginModal.style.display = "none";
                        loginModal.classList.remove("open");
                    }
                    if (loginErrorMessage) loginErrorMessage.style.display = "none";
                    if (btnLogout) btnLogout.style.display = "block";
                    passwordInput.value = "";
                    fetchShowcases();
                } else {
                    const errData = await res.json();
                    if (loginErrorMessage) {
                        loginErrorMessage.textContent = errData.detail || "Invalid credentials";
                        loginErrorMessage.style.display = "block";
                    }
                }
            } catch (err) {
                if (loginErrorMessage) {
                    loginErrorMessage.textContent = "Network error during login";
                    loginErrorMessage.style.display = "block";
                }
            }
        });
    }

    if (btnLogout) {
        btnLogout.addEventListener("click", () => {
            localStorage.removeItem("admin_jwt");
            btnLogout.style.display = "none";
            if (loginModal) {
                loginModal.style.display = "flex";
                loginModal.classList.add("open");
            }
            featuresGrid.innerHTML = `<div class="card-skeleton">🔒 Authentication required. Please enter credentials.</div>`;
        });
    }

    // Fetch and Render Showcases from Backend REST API
    async function fetchShowcases() {
        try {
            const response = await fetchWithAuth("/api/showcases");
            if (response.status === 401) {
                featuresGrid.innerHTML = `<div class="card-skeleton">🔒 Authentication required. Please enter credentials.</div>`;
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
                let extraConfig = "";
                if (item.name === "agent-sandbox") {
                    extraConfig = `
                        <div class="input-group" style="margin-top: 0.5rem;">
                            <label for="provider-${item.name}">LLM Backend Provider</label>
                            <select id="provider-${item.name}" class="provider-select">
                                <option value="vertex">Vertex AI</option>
                                <option value="vllm">Deployed vLLM Gateway</option>
                                <option value="custom">Custom Endpoint</option>
                            </select>
                        </div>
                        <div class="input-group endpoint-group" id="endpoint-group-${item.name}" style="display: none; margin-top: 0.5rem;">
                            <label for="endpoint-${item.name}">Custom LLM URL</label>
                            <input type="text" id="endpoint-${item.name}" placeholder="http://external-vllm:8000/v1" />
                        </div>
                    `;
                }
                statusControlHtml = `
                    <div class="deployment-config">
                        <div class="input-group">
                            <label for="ns-${item.name}">Target Namespace</label>
                            <input type="text" id="ns-${item.name}" placeholder="Default: gke-showcase-${item.name}" />
                        </div>
                        ${extraConfig}
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
            clusterModeMetric.textContent = showcasesCache[0].name ? "HYBRID STATE" : "MOCK";
        }
    }

    // Handle dynamic button clicks
    featuresGrid.addEventListener("change", (e) => {
        const target = e.target;
        if (target.classList.contains("provider-select")) {
            const name = target.id.replace("provider-", "");
            const endpointGroup = document.getElementById(`endpoint-group-${name}`);
            if (endpointGroup) {
                if (target.value === "custom") {
                    endpointGroup.style.display = "block";
                } else {
                    endpointGroup.style.display = "none";
                }
            }
        }
    });

    featuresGrid.addEventListener("click", async (e) => {
        const target = e.target;
        const name = target.getAttribute("data-name");

        if (!name) return;

        if (target.classList.contains("btn-deploy") && !target.classList.contains("btn-teardown")) {
            const nsInput = document.getElementById(`ns-${name}`);
            const namespaceValue = nsInput ? (nsInput.value.strip ? nsInput.value.strip() : nsInput.value.trim()) : "";
            const providerSelect = document.getElementById(`provider-${name}`);
            const llm_provider = providerSelect ? providerSelect.value : "vertex";
            const endpointInput = document.getElementById(`endpoint-${name}`);
            const llm_service_endpoint = (endpointInput && llm_provider === "custom") ? endpointInput.value.trim() : "";
            
            target.textContent = "Initiating...";
            target.disabled = true;

            try {
                const response = await fetchWithAuth(`/api/showcases/${name}/deploy`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ namespace: namespaceValue, llm_provider, llm_service_endpoint })
                });
                
                if (!response.ok && response.status !== 401) throw new Error("Failed to initiate deployment.");
                
                await fetchShowcases();
            } catch (err) {
                alert(`Deployment failed: ${err.message}`);
                fetchShowcases();
            }
        } 
        
        else if (target.classList.contains("btn-teardown")) {
            target.textContent = "Terminating...";
            target.disabled = true;

            try {
                const response = await fetchWithAuth(`/api/showcases/${name}/teardown`, {
                    method: "DELETE"
                });
                
                if (!response.ok && response.status !== 401) throw new Error("Failed to tear down showcase.");
                
                await fetchShowcases();
            } catch (err) {
                alert(`Teardown failed: ${err.message}`);
                fetchShowcases();
            }
        } 
        
        else if (target.classList.contains("btn-logs")) {
            const matchedItem = showcasesCache.find(i => i.name === name);
            if (!matchedItem) return;

            consoleShowcaseTitle.textContent = `${matchedItem.title} Diagnostics`;
            consoleNamespaceMeta.textContent = `Namespace: ${matchedItem.namespace || 'N/A'}`;
            consoleLogStream.textContent = "[SYSTEM] Retrieving live logs...";
            
            refreshLogsBtn.setAttribute("data-name", name);
            
            consoleModal.classList.add("open");
            await loadLogs(name);
        }
    });

    // Retrieve dynamic container logs from API
    async function loadLogs(name) {
        try {
            const response = await fetchWithAuth(`/api/showcases/${name}/logs`);
            if (response.status === 401) return;
            if (!response.ok) throw new Error("Failed to load diagnostic logs.");
            
            const data = await response.json();
            consoleLogStream.textContent = data.logs;
            consoleLogStream.scrollTop = consoleLogStream.scrollHeight;
        } catch (err) {
            consoleLogStream.textContent = `[ERROR] Log retrieval failed: ${err.message}`;
        }
    }

    refreshLogsBtn.addEventListener("click", async () => {
        const name = refreshLogsBtn.getAttribute("data-name");
        if (name) {
            consoleLogStream.textContent = "[SYSTEM] Refreshing logs...";
            await loadLogs(name);
        }
    });

    closeConsoleBtn.addEventListener("click", () => {
        consoleModal.classList.remove("open");
    });

    setInterval(() => {
        const needsSync = showcasesCache.some(item => item.status === "DEPLOYING" || item.status === "TERMINATING");
        if (needsSync) {
            fetchShowcases();
        }
    }, 2000);

    setInterval(() => {
        const timers = document.querySelectorAll(".elapsed-timer");
        timers.forEach(t => {
            const startStr = t.getAttribute("data-start");
            if (startStr) {
                t.textContent = getElapsedTimeString(startStr);
            }
        });
    }, 1000);

    // ==============================================================================
    // Tab Navigation & Telemetry Polling
    // ==============================================================================
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabViews = document.querySelectorAll(".tab-view");
    let telemetryInterval = null;

    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            const targetId = btn.getAttribute("data-tab");
            tabViews.forEach(view => {
                if (view.id === targetId) {
                    view.style.display = "block";
                } else {
                    view.style.display = "none";
                }
            });

            if (targetId === "telemetry-view") {
                fetchTelemetry();
                if (!telemetryInterval) {
                    telemetryInterval = setInterval(fetchTelemetry, 5000);
                }
            } else {
                if (telemetryInterval) {
                    clearInterval(telemetryInterval);
                    telemetryInterval = null;
                }
            }
        });
    });

    async function fetchTelemetry() {
        try {
            const res = await fetchWithAuth("/api/stats");
            if (!res.ok) return;
            const data = await res.json();

            const nodesTotal = document.getElementById("telemetry-nodes-total");
            const nodesReady = document.getElementById("telemetry-nodes-ready");
            const namespaces = document.getElementById("telemetry-namespaces");
            const podsTotal = document.getElementById("telemetry-pods-total");
            const podsDetails = document.getElementById("telemetry-pods-details");
            const gpuVal = document.getElementById("telemetry-gpu");
            const gvisorVal = document.getElementById("telemetry-gvisor");

            if (nodesTotal && data.nodes) {
                nodesTotal.textContent = data.nodes.total;
                nodesReady.textContent = `Ready: ${data.nodes.ready}`;
            }
            if (namespaces && data.namespaces) {
                namespaces.textContent = data.namespaces.total;
            }
            if (podsTotal && data.pods) {
                podsTotal.textContent = data.pods.total;
                podsDetails.textContent = `Running: ${data.pods.running} | Pending: ${data.pods.pending} | Failed: ${data.pods.failed}`;
            }
            if (gpuVal && data.accelerators) {
                gpuVal.textContent = data.accelerators.nvidia_l4;
            }
            if (gvisorVal && data.accelerators) {
                gvisorVal.textContent = data.accelerators.gvisor;
            }
        } catch (err) {
            console.error("Failed to fetch cluster telemetry:", err);
        }
    }

    // Bootstrap Setup
    fetchShowcases();
});

