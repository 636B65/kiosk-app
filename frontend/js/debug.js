const Debug = {
    enabled: false,
    open: false,
    fab: null,
    panel: null,
    requests: [],
    routes: [],
    nav: { dcl: null, load: null, fcp: null },
    tickTimer: null,
    pollTimer: null,
    MAX_REQ: 40,

    isOn(settings) {
        settings = settings || Store.settings || {};
        return settings.debug_mode === "true" || settings.debug_mode === "1";
    },

    async syncSetting() {
        try {
            const settings = await API.get("/settings");
            Store.settings = { ...Store.settings, ...settings };
            this.setEnabled(this.isOn(settings));
        } catch {}
    },

    init() {
        this.installHooks();
        this.captureNav();
        this.syncSetting();
        this.pollTimer = setInterval(() => this.syncSetting(), 15000);
    },

    installHooks() {
        const orig = API.request;
        const self = this;
        API.request = function (path, options) {
            const t0 = performance.now();
            const method = (options && options.method) || "GET";
            return orig.call(this, path, options)
                .then((data) => {
                    self.recordRequest(method, path, "OK", performance.now() - t0);
                    return data;
                })
                .catch((err) => {
                    self.recordRequest(method, path, "ERR", performance.now() - t0);
                    throw err;
                });
        };
    },

    captureNav() {
        const nav = performance.getEntriesByType("navigation")[0];
        if (nav) {
            this.nav.dcl = nav.domContentLoadedEventEnd;
            this.nav.load = nav.loadEventEnd;
        }
        if ("PerformanceObserver" in window) {
            try {
                const obs = new PerformanceObserver((list) => {
                    for (const e of list.getEntries()) {
                        if (e.name === "first-contentful-paint") this.nav.fcp = e.startTime;
                    }
                });
                obs.observe({ type: "paint", buffered: true });
            } catch {}
        }
    },

    recordRequest(method, path, status, ms) {
        const t = new Date();
        this.requests.push({
            time: `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}:${String(t.getSeconds()).padStart(2, "0")}`,
            method,
            path,
            status,
            ms: Math.round(ms),
        });
        if (this.requests.length > this.MAX_REQ) this.requests.shift();
    },

    recordRoute(label, ms) {
        const t = new Date();
        this.routes.push({
            label,
            ms: Math.round(ms),
            time: `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}:${String(t.getSeconds()).padStart(2, "0")}`,
        });
        if (this.routes.length > 20) this.routes.shift();
    },

    setEnabled(on) {
        if (this.enabled === on) return;
        this.enabled = on;
        if (on) {
            this.buildPanel();
            this.tick();
            this.tickTimer = setInterval(() => this.tick(), 1500);
            this.open = true;
            this.render();
        } else {
            this.teardown();
        }
    },

    toggle() {
        if (!this.enabled) return;
        this.open = !this.open;
        this.render();
    },

    memory() {
        const m = performance.memory || null;
        const nodes = document.getElementsByTagName("*").length;
        return { used: m ? m.usedJSHeapSize : null, limit: m ? m.jsHeapSizeLimit : null, nodes };
    },

    network() {
        const res = performance.getEntriesByType("resource");
        let bytes = 0;
        let images = 0;
        for (const r of res) {
            if (r.transferSize > 0) bytes += r.transferSize;
            if (r.initiatorType === "img") images++;
        }
        return { count: res.length, bytes, images };
    },

    ms(n, suffix = "ms") {
        return n == null ? "—" : `${Math.round(n)} ${suffix}`;
    },

    fmtBytes(n) {
        if (!n) return "0 B";
        if (n < 1 << 10) return `${n} B`;
        if (n < 1 << 20) return `${(n / (1 << 10)).toFixed(1)} KB`;
        return `${(n / (1 << 20)).toFixed(2)} MB`;
    },

    statusClass(ms) {
        if (ms >= 1000) return "debug-slow";
        if (ms >= 300) return "debug-warn";
        return "";
    },

    fmtMemory() {
        const m = this.memory();
        if (m.used == null) return "n/a (browser)";
        const pct = Math.round((m.used / m.limit) * 100);
        return `${(m.used / 1048576).toFixed(1)} / ${(m.limit / 1048576).toFixed(0)} MB (${pct}%)`;
    },

    buildPanel() {
        if (this.fab) return;
        this.fab = document.createElement("button");
        this.fab.className = "debug-fab";
        this.fab.title = "Toggle debug panel";
        this.fab.textContent = "🐞";
        this.fab.addEventListener("click", () => this.toggle());

        this.panel = document.createElement("div");
        this.panel.className = "debug-panel";
        this.panel.innerHTML = `
            <div class="debug-head">
                <span>🐞 Debug / Verbose</span>
                <span class="debug-badge" id="debug-status">ON</span>
                <button id="debug-clear">Clear</button>
                <button id="debug-close" title="Collapse">—</button>
            </div>
            <div id="debug-body"></div>
        `;
        this.panel.querySelector("#debug-close").addEventListener("click", () => this.toggle());
        this.panel.querySelector("#debug-clear").addEventListener("click", () => {
            this.requests = [];
            this.tick();
        });
        document.body.appendChild(this.fab);
        document.body.appendChild(this.panel);
    },

    teardown() {
        if (this.tickTimer) {
            clearInterval(this.tickTimer);
            this.tickTimer = null;
        }
        if (this.fab) {
            this.fab.remove();
            this.fab = null;
        }
        if (this.panel) {
            this.panel.remove();
            this.panel = null;
        }
        this.open = false;
    },

    tick() {
        if (!this.enabled) return;
        this.captureNav();
        if (!this.panel) return;
        const nw = this.network();
        const mem = this.memory();
        const lastRoute = this.routes[this.routes.length - 1];
        const reqCount = this.requests.length;
        const avgMs = reqCount
            ? Math.round(this.requests.reduce((s, r) => s + r.ms, 0) / reqCount)
            : 0;
        const slow = this.requests.filter((r) => r.ms >= 300).length;

        const log = this.requests.slice(-20).reverse().map((r) => `
            <tr class="${this.statusClass(r.ms)}">
                <td class="debug-dim">${r.time}</td>
                <td>${esc(r.method)}</td>
                <td class="debug-path" title="${esc(r.path)}">${esc(r.path)}</td>
                <td class="${r.status === "OK" ? "debug-ok" : "debug-bad"}">${r.status}</td>
                <td class="debug-num">${r.ms}</td>
            </tr>
        `).join("");

        const routeRows = this.routes.slice(-5).reverse().map((r) => `
            <tr>
                <td class="debug-dim">${r.time}</td>
                <td>${esc(r.label)}</td>
                <td class="debug-num">${r.ms}</td>
                <td></td>
            </tr>
        `).join("");

        const body = document.getElementById("debug-body");
        if (!body) return;
        body.innerHTML = `
            <div class="debug-grid">
                <div class="debug-cell">
                    <span>DOMContentLoaded</span>
                    <strong>${this.ms(this.nav.dcl)}</strong>
                </div>
                <div class="debug-cell">
                    <span>Load</span>
                    <strong>${this.ms(this.nav.load)}</strong>
                </div>
                <div class="debug-cell">
                    <span>First Contentful Paint</span>
                    <strong>${this.ms(this.nav.fcp)}</strong>
                </div>
                <div class="debug-cell">
                    <span>API calls</span>
                    <strong>${reqCount}</strong>
                    <small>avg ${avgMs} ms · ${slow} slow</small>
                </div>
                <div class="debug-cell">
                    <span>Memory (JS heap)</span>
                    <strong>${this.fmtMemory()}</strong>
                </div>
                <div class="debug-cell">
                    <span>DOM nodes</span>
                    <strong>${mem.nodes}</strong>
                </div>
                <div class="debug-cell">
                    <span>Network resources</span>
                    <strong>${nw.count}</strong>
                    <small>${this.fmtBytes(nw.bytes)} · ${nw.images} img</small>
                </div>
                <div class="debug-cell">
                    <span>Last route</span>
                    <strong>${lastRoute ? esc(lastRoute.label) : "—"}</strong>
                    <small>render ${lastRoute ? `${lastRoute.ms} ms` : "—"}</small>
                </div>
            </div>
            <div class="debug-section">Route render times</div>
            <table class="debug-table">
                <thead><tr><th>Time</th><th>Route</th><th>ms</th><th></th></tr></thead>
                <tbody>${routeRows || '<tr><td colspan="4" class="debug-dim">No routes measured yet</td></tr>'}</tbody>
            </table>
            <div class="debug-section">API requests</div>
            <table class="debug-table">
                <thead><tr><th>Time</th><th>Method</th><th>Path</th><th>Status</th><th>ms</th></tr></thead>
                <tbody>${log || '<tr><td colspan="5" class="debug-dim">No requests logged</td></tr>'}</tbody>
            </table>
        `;
    },

    render() {
        if (!this.enabled || !this.panel) return;
        this.panel.classList.toggle("debug-open", this.open);
    },
};