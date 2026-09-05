const API = {
    async request(path, options = {}) {
        const opts = { ...options };
        opts.headers = { ...(opts.headers || {}) };
        if (opts.body && !(opts.body instanceof FormData)) {
            opts.headers["Content-Type"] = "application/json";
        }
        const token = localStorage.getItem("kiosk_token");
        if (token) {
            opts.headers["Authorization"] = `Bearer ${token}`;
        }
        const res = await fetch(`/api${path}`, opts);
        if (res.status === 401 && token) {
            localStorage.removeItem("kiosk_token");
            localStorage.removeItem("kiosk_user");
            location.hash = "#admin/login";
        }
        if (res.status === 204) return null;
        const data = await res.json().catch(() => null);
        if (!res.ok) {
            const detail = data && data.detail ? data.detail : `Request failed (${res.status})`;
            throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
        }
        return data;
    },

    get(path) { return this.request(path); },
    post(path, body) {
        return this.request(path, { method: "POST", body: JSON.stringify(body) });
    },
    put(path, body) {
        return this.request(path, { method: "PUT", body: JSON.stringify(body) });
    },
    patch(path, body) {
        return this.request(path, { method: "PATCH", body: JSON.stringify(body) });
    },
    del(path) { return this.request(path, { method: "DELETE" }); },
    upload(path, formData) {
        return this.request(path, { method: "POST", body: formData });
    },
};