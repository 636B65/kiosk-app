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

const SUPPORTED_CURRENCIES = {
    AED: "UAE Dirham",
    AUD: "Australian Dollar",
    BRL: "Brazilian Real",
    CAD: "Canadian Dollar",
    CHF: "Swiss Franc",
    CNY: "Chinese Yuan",
    DKK: "Danish Krone",
    EUR: "Euro",
    GBP: "British Pound",
    HKD: "Hong Kong Dollar",
    INR: "Indian Rupee",
    JPY: "Japanese Yen",
    KRW: "South Korean Won",
    MXN: "Mexican Peso",
    NOK: "Norwegian Krone",
    NZD: "New Zealand Dollar",
    PLN: "Polish Zloty",
    RUB: "Russian Ruble",
    SEK: "Swedish Krona",
    SGD: "Singapore Dollar",
    USD: "US Dollar",
    ZAR: "South African Rand",
};

const fmt = (n) => {
    const currency = Store.settings.currency || "EUR";
    const code = SUPPORTED_CURRENCIES[currency] ? currency : "EUR";
    return new Intl.NumberFormat("sv-SE", {
        style: "currency",
        currency: code,
        minimumFractionDigits: 2,
    }).format(n ?? 0);
};

const effectivePrice = (p) =>
    p && p.is_weekly_special && p.special_price != null ? p.special_price : (p?.price || 0);

const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));

function confetti({ particleCount = 180, duration = 3500 } = {}) {
    const colors = ["#f59e0b", "#ef4444", "#3b82f6", "#10b981", "#8b5cf6", "#ec4899", "#facc15"];
    const canvas = document.createElement("canvas");
    canvas.className = "confetti-layer";
    canvas.style.position = "fixed";
    canvas.style.inset = "0";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.pointerEvents = "none";
    canvas.style.zIndex = "9999";
    document.body.appendChild(canvas);

    const dpr = window.devicePixelRatio || 1;
    const width = window.innerWidth;
    const height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const particles = Array.from({ length: particleCount }, () => ({
        x: Math.random() * width,
        y: -20 - Math.random() * height * 0.4,
        size: 6 + Math.random() * 7,
        color: colors[Math.floor(Math.random() * colors.length)],
        vx: (Math.random() - 0.5) * 3,
        vy: 2 + Math.random() * 4,
        rot: Math.random() * Math.PI * 2,
        vr: (Math.random() - 0.5) * 0.3,
        round: Math.random() < 0.4,
    }));

    const started = performance.now();
    const gravity = 0.08;
    function frame(now) {
        ctx.clearRect(0, 0, width, height);
        const elapsed = now - started;
        const fade = elapsed > duration - 600 ? Math.max(0, (duration - elapsed) / 600) : 1;
        for (const p of particles) {
            p.vy += gravity;
            p.x += p.vx;
            p.y += p.vy;
            p.rot += p.vr;
            ctx.save();
            ctx.globalAlpha = fade;
            ctx.translate(p.x, p.y);
            ctx.rotate(p.rot);
            ctx.fillStyle = p.color;
            if (p.round) {
                ctx.beginPath();
                ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
                ctx.fill();
            } else {
                ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
            }
            ctx.restore();
        }
        if (elapsed < duration) {
            requestAnimationFrame(frame);
        } else {
            canvas.remove();
        }
    }
    requestAnimationFrame(frame);
}

function sortShopProducts(products) {
    return [...products].sort((a, b) => {
        const aSpec = a.is_weekly_special ? 0 : 1;
        const bSpec = b.is_weekly_special ? 0 : 1;
        if (aSpec !== bSpec) return aSpec - bSpec;
        return a.name.localeCompare(b.name);
    });
}

function renderProductImage(product) {
    if (product.image_url) {
        return `<img src="${esc(product.image_url)}" alt="${esc(product.name)}">`;
    }
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