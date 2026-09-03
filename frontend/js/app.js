let currentRoute = "customer";

function parseRoute() {
    const hash = location.hash.replace(/^#\/?/, "");
    if (hash.startsWith("admin")) {
        return { page: "admin", view: hash.split("/")[1] || "dashboard" };
    }
    return { page: "customer" };
}

function handleRoute() {
    const route = parseRoute();
    if (route.page !== currentRoute) {
        Modal.close();
    }
    currentRoute = route.page;
    if (route.page === "admin") {
        Admin.view = route.view;
        Admin.render();
    } else {
        Kiosk.render();
    }
}

document.addEventListener("DOMContentLoaded", () => {
    Kiosk.init();
    Admin.init();
    handleRoute();
    window.addEventListener("hashchange", handleRoute);
});

const Store = {
    categories: [],
    products: [],
    settings: {},
    cart: JSON.parse(localStorage.getItem("kiosk_cart") || "[]"),
    activeCategory: null,

    saveCart() {
        localStorage.setItem("kiosk_cart", JSON.stringify(this.cart));
    },

    cartCount() {
        return this.cart.reduce((n, i) => n + i.quantity, 0);
    },

    cartTotal() {
        return this.cart.reduce((sum, i) => sum + i.price * i.quantity, 0);
    },

    async loadPublicData() {
        const [categories, products, settings] = await Promise.all([
            API.get("/categories"),
            API.get("/products"),
            API.get("/settings"),
        ]);
        this.categories = categories;
        this.products = products;
        this.settings = settings;
    },

    async refresh() {
        const [categories, products] = await Promise.all([
            API.get("/categories"),
            API.get("/products?active_only=false"),
        ]);
        this.categories = categories;
        this.products = products;
    },
};

const Toast = {
    show(message, type = "info") {
        let container = document.querySelector(".toast-container");
        if (!container) {
            container = document.createElement("div");
            container.className = "toast-container";
            document.body.appendChild(container);
        }
        const el = document.createElement("div");
        el.className = `toast ${type}`;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    },
    success(msg) { this.show(msg, "success"); },
    error(msg) { this.show(msg, "error"); },
};

const Modal = {
    open(content) {
        this.close();
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        overlay.id = "modal-overlay";
        overlay.innerHTML = `<div class="modal">${content}</div>`;
        document.body.appendChild(overlay);
        overlay.addEventListener("mousedown", (e) => {
            if (e.target === overlay) overlay.remove();
        });
    },
    close() {
        const el = document.getElementById("modal-overlay");
        if (el) el.remove();
    },
    fill(content) {
        const el = document.querySelector("#modal-overlay .modal");
        if (el) el.innerHTML = content;
    },
};

const fmt = (n) =>
    new Intl.NumberFormat("sv-SE", {
        style: "currency",
        currency: "SEK",
        minimumFractionDigits: 2,
    }).format(n ?? 0);

const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

function renderProductImage(product) {
    return `<span>${esc(product.name.charAt(0).toUpperCase())}</span>`;
}

function monthKey(dateStr) {
    const d = new Date(dateStr);
    if (isNaN(d)) return "";
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    return `${d.getFullYear()}-${mm}`;
}

function monthLabel(key) {
    const [y, m] = key.split("-");
    const nm = new Intl.DateTimeFormat("sv-SE", { month: "long" }).format(new Date(Number(y), Number(m) - 1, 1));
    const cap = nm.charAt(0).toUpperCase() + nm.slice(1);
    return `${cap} ${y}`;
}

function groupOrdersByMonth(orders) {
    const groups = {};
    for (const o of orders) {
        const k = monthKey(o.created_at) || "unknown";
        (groups[k] = groups[k] || []).push(o);
    }
    return Object.keys(groups)
        .sort((a, b) => (a === "unknown" ? -1 : b === "unknown" ? 1 : b.localeCompare(a)))
        .map((k) => ({ key: k, label: monthLabel(k), orders: groups[k] }));
}

function renderCustomerStats(stats) {
    if (!stats) return "";
    const rows = [
        ["Orders", stats.orders],
        ["Items bought", stats.items_bought],
        ["Most bought", stats.top_item ? `${esc(stats.top_item)} (${stats.top_item_qty})` : "—"],
        ["Total spent", fmt(stats.total_spent)],
        ["Total paid", fmt(stats.total_paid)],
        ["Average order", fmt(stats.avg_order)],
        ["First order", stats.first_order_at ? new Date(stats.first_order_at).toLocaleDateString() : "—"],
        ["Last order", stats.last_order_at ? new Date(stats.last_order_at).toLocaleDateString() : "—"],
    ];
    return `
        <h3 style="margin:1rem 0 0.5rem;">Stats</h3>
        <div class="customer-stats">
            ${rows.map(([label, val]) => `
                <div class="customer-stat">
                    <div class="customer-stat-label">${label}</div>
                    <div class="customer-stat-value">${val}</div>
                </div>
            `).join("")}
        </div>
    `;
}