// ==============================================================================
// Agent Substrate — Overcommit (suspend/resume) — Playroom Controller
//
// 10 actor lanes on a 2-worker pool. Every button maps to a real ate control
// plane call via the Hub router:
//   Run     -> POST /lanes/{n}/run      (CreateActor)
//   Touch   -> POST /lanes/{n}/touch    (data path via atenet-router; bumps the
//              in-RAM counter and transparently resumes a suspended actor)
//   Suspend -> POST /lanes/{n}/suspend  (SuspendActor -> full snapshot)
//   Resume  -> POST /lanes/{n}/resume   (ResumeActor from snapshot)
//   Reset   -> DELETE /lanes/{n}        (DeleteActor)
//
// The per-lane count is only observable through Touch responses, so it's kept
// client-side: the state-preservation proof is watching it CONTINUE after a
// suspend -> resume round-trip.
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
    const API = "/api/features/substrate-overcommit";
    const NUM_LANES = 10;
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
    const laneTable = el("lane-table");
    const errBox = el("oc-error");
    const autoSuspendBox = el("auto-suspend");

    // Client-side per-lane memory: last observed count + in-flight action.
    const counts = {};   // lane -> last {"count": N} from Touch
    const busy = {};     // lane -> action name while a request is in flight
    let lastState = null;

    const STATUS_CLS = {
        running: "st-running",
        suspended: "st-suspended",
        paused: "st-suspended",
        resuming: "st-busy",
        suspending: "st-busy",
        pausing: "st-busy",
        absent: "st-absent",
        unknown: "st-busy",
    };

    function setError(msg) { errBox.textContent = msg || ""; }

    function renderMeter(state) {
        el("mode-tag").textContent = state.mode === "MOCK" ? "(mock preview)" : "";
        const m = state.meter || {};
        el("meter-execs").textContent = m.executions ?? "–";
        el("meter-workers").textContent = m.workers ?? "–";
        el("kpi-running").textContent = m.running ?? "–";
        el("kpi-suspended").textContent = m.suspended ?? "–";
        const assigned = (state.workers || []).filter(w => w.assignment).length;
        el("kpi-pool").textContent = (state.workers || []).length
            ? `${assigned}/${(state.workers || []).length} slots bound`
            : "–";
    }

    function laneButtons(lane, status) {
        const b = busy[lane.lane];
        const disabled = (cond) => (b || cond) ? "disabled" : "";
        const transitional = ["resuming", "suspending", "pausing", "unknown"].includes(status);
        return `
            <button class="lane-btn primary" data-act="run" data-lane="${lane.lane}"
                ${disabled(status !== "absent")}>Run</button>
            <button class="lane-btn primary" data-act="touch" data-lane="${lane.lane}"
                ${disabled(status === "absent" || transitional)}>${b === "touch" ? "…" : "Touch"}</button>
            <button class="lane-btn" data-act="suspend" data-lane="${lane.lane}"
                ${disabled(status !== "running")}>Suspend</button>
            <button class="lane-btn" data-act="resume" data-lane="${lane.lane}"
                ${disabled(status !== "suspended" && status !== "paused")}>Resume</button>
            <button class="lane-btn danger" data-act="reset" data-lane="${lane.lane}"
                ${disabled(status === "absent")}>Reset</button>`;
    }

    function renderLanes(state) {
        const rows = (state.lanes || []).map(lane => {
            const status = busy[lane.lane] ? `${busy[lane.lane]}…` : lane.status;
            const cls = STATUS_CLS[lane.status] || "st-absent";
            const count = counts[lane.lane];
            return `<div class="lane-row">
                <span class="lane-name">${escapeHtml(lane.name)}</span>
                <span class="lane-status ${busy[lane.lane] ? "st-busy" : cls}">${escapeHtml(status)}</span>
                <span class="lane-count">${count != null ? count : "–"}
                    <span class="count-label">count</span></span>
                <span class="lane-worker">${escapeHtml(lane.worker_pod || "")}</span>
                <span class="lane-actions">${laneButtons(lane, lane.status)}</span>
            </div>`;
        }).join("");
        laneTable.innerHTML = rows || `<div class="card-skeleton">No lanes.</div>`;
    }

    function render(state) {
        lastState = state;
        renderMeter(state);
        renderLanes(state);
    }

    async function refresh() {
        try {
            const resp = await fetchWithAuth(`${API}/state`);
            if (!resp.ok) throw new Error(`state fetch failed (${resp.status})`);
            render(await resp.json());
            setError("");
        } catch (err) {
            setError(`Error: ${err.message}`);
        }
    }

    async function doAction(lane, act) {
        if (busy[lane]) return;
        busy[lane] = act;
        if (lastState) renderLanes(lastState);
        setError("");
        try {
            const method = act === "reset" ? "DELETE" : "POST";
            let path = act === "reset" ? `${API}/lanes/${lane}` : `${API}/lanes/${lane}/${act}`;
            if (act === "touch" && autoSuspendBox && !autoSuspendBox.checked) {
                path += "?auto_suspend=0";
            }
            const resp = await fetchWithAuth(path, { method });
            if (!resp.ok) {
                let detail = `${act} failed (${resp.status})`;
                try { detail = (await resp.json()).detail || detail; } catch (_) { /* keep */ }
                throw new Error(detail);
            }
            const body = await resp.json();
            if (act === "touch" && body.count != null) counts[lane] = body.count;
            if (act === "reset") delete counts[lane];
        } catch (err) {
            setError(`lane-${lane}: ${err.message}`);
        } finally {
            delete busy[lane];
            await refresh();
        }
    }

    laneTable.addEventListener("click", (ev) => {
        const btn = ev.target.closest("button[data-act]");
        if (!btn || btn.disabled) return;
        doAction(Number(btn.dataset.lane), btn.dataset.act);
    });

    refresh();
    setInterval(refresh, POLL_MS);
});
