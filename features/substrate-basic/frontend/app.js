// ==============================================================================
// Agent Substrate (WorkerPool / Actor reconcile) — Playroom Controller
//
// READ-ONLY: polls /api/features/substrate-basic/state and renders desired-vs-
// reconciled state. It never POSTs/DELETEs — there is nothing to allocate here,
// only the live reconcile loop to observe.
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    const POLL_MS = 5000;

    function escapeHtml(str) {
        return String(str ?? "")
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    async function fetchWithAuth(url, options = {}) {
        const jwt = localStorage.getItem("admin_jwt");
        const headers = { ...options.headers };
        if (jwt) headers["Authorization"] = `Bearer ${jwt}`;
        return fetch(url, { ...options, headers });
    }

    const el = (id) => document.getElementById(id);
    const wpCard = el("workerpool-card");
    const depCard = el("deployment-card");
    const atCard = el("actortemplate-card");

    function kvRow(k, v) {
        return `<div class="kv-row"><span class="k">${escapeHtml(k)}</span>` +
               `<span class="v">${escapeHtml(v)}</span></div>`;
    }

    function renderWorkerPool(wp) {
        if (!wp) {
            wpCard.innerHTML = `<div class="card-skeleton">No WorkerPool found.</div>`;
            return;
        }
        const desired = wp.desiredReplicas ?? "–";
        wpCard.innerHTML =
            `<h3>WorkerPool <span class="kind-badge">ate.dev/v1alpha1</span></h3>` +
            `<div class="cr-name">${escapeHtml(wp.name)}</div>` +
            kvRow("desired replicas", desired) +
            kvRow("sandboxClass", wp.sandboxClass || "gvisor") +
            kvRow("ateomImage", wp.ateomImage || "–");
    }

    function renderDeployment(dep, wp) {
        if (!dep) {
            depCard.innerHTML = `<div class="card-skeleton">Reconcile pending…</div>`;
            return;
        }
        const ready = dep.readyReplicas ?? 0;
        const desired = dep.desiredReplicas ?? (wp ? wp.desiredReplicas : "–");
        const ok = !!dep.reconciled;
        const stateCls = ok ? "ok" : "wait";
        const stateTxt = ok ? "RECONCILED" : "RECONCILING";
        depCard.innerHTML =
            `<h3>Worker Deployment ` +
            `<span class="reconcile-state ${stateCls}">${stateTxt}</span></h3>` +
            `<div class="cr-name">${escapeHtml(dep.name)}</div>` +
            kvRow("ready / desired", `${ready} / ${desired}`) +
            `<div class="kv-row"><span class="k">reconcile</span>` +
            `<span class="v replica-pill ${ok ? "state-ok" : "state-wait"}">` +
            `${ok ? "desired state met" : "converging…"}</span></div>`;
    }

    function renderActorTemplate(at) {
        if (!at) {
            atCard.innerHTML = `<div class="card-skeleton">No ActorTemplate found.</div>`;
            return;
        }
        const containers = (at.containers || [])
            .map(c => `<div class="container-line">▪ ${escapeHtml(c.name)}: ${escapeHtml(c.image)}</div>`)
            .join("") || `<div class="container-line">–</div>`;
        const selector = Object.entries(at.workerSelector || {})
            .map(([k, v]) => `${k}=${v}`).join(", ") || "–";
        atCard.innerHTML =
            `<h3>ActorTemplate <span class="kind-badge">ate.dev/v1alpha1</span></h3>` +
            `<div class="cr-name">${escapeHtml(at.name)}</div>` +
            kvRow("pauseImage", at.pauseImage || "–") +
            `<div><span class="k" style="color: var(--text-muted); font-size: 0.82rem;">actor containers</span>${containers}</div>` +
            kvRow("workerSelector", selector);
    }

    function renderKpis(state) {
        const wp = (state.workerPools || [])[0];
        const dep = state.reconciledDeployment;
        el("mode-tag").textContent = state.mode === "MOCK" ? "(mock preview)" : "";
        el("kpi-desired").textContent = wp ? (wp.desiredReplicas ?? "–") : "–";
        el("kpi-ready").textContent = dep ? (dep.readyReplicas ?? 0) : "–";
        el("kpi-sandbox").textContent = wp ? (wp.sandboxClass || "gVisor") : "gVisor";
        const ok = dep && dep.reconciled;
        const kState = el("kpi-state");
        kState.textContent = ok ? "Reconciled" : "Reconciling";
        kState.className = "metric-value " + (ok ? "state-ok" : "state-wait");
    }

    async function refresh() {
        try {
            const resp = await fetchWithAuth("/api/features/substrate-basic/state");
            if (!resp.ok) throw new Error(`state fetch failed (${resp.status})`);
            const state = await resp.json();
            renderKpis(state);
            renderWorkerPool((state.workerPools || [])[0]);
            renderDeployment(state.reconciledDeployment, (state.workerPools || [])[0]);
            renderActorTemplate((state.actorTemplates || [])[0]);
        } catch (err) {
            wpCard.innerHTML = `<div class="card-skeleton" style="color:#ff4444;">Error: ${escapeHtml(err.message)}</div>`;
        }
    }

    refresh();
    setInterval(refresh, POLL_MS);
});
