// GitHub Pages demo shim: overrides fetch() with an in-memory mock of the
// FastAPI backend so the static frontend runs standalone as a live demo.
// Active on *.github.io hosts or with ?demo=1; otherwise a no-op.
(function () {
    "use strict";

    const query = new URLSearchParams(window.location.search);
    const onGitHubIo = /(^|\.)github\.io$/.test(window.location.hostname);
    if (query.get("demo") !== "1" && !onGitHubIo) return;

    function pad(n) { return String(n).padStart(2, "0"); }
    function fmtDT(d) {
        if (d == null) return null;
        return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
            "T" + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }
    function daysAgo(n, hour) {
        const d = new Date();
        d.setDate(d.getDate() - n);
        if (hour !== undefined) d.setHours(hour, 0, 0, 0);
        return d;
    }
    function hoursAgo(h) {
        const d = new Date();
        d.setHours(d.getHours() - h, 0, 0, 0);
        return d;
    }

    function svgImage(emoji, color) {
        const svg = "<svg xmlns='http://www.w3.org/2000/svg' width='96' height='96'>" +
            "<rect width='96' height='96' rx='16' fill='" + color + "'/>" +
            "<text x='48' y='58' font-size='44' text-anchor='middle'>" + emoji + "</text></svg>";
        return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    }

    const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

    const DB = {
        categories: [
            { id: 1, name: "Electronics", description: "Gadgets and accessories", sort_order: 1 },
            { id: 2, name: "Snacks", description: "Quick bites and treats", sort_order: 2 },
            { id: 3, name: "Beverages", description: "Drinks and refreshments", sort_order: 3 },
            { id: 4, name: "Clothing", description: "Apparel and accessories", sort_order: 4 },
        ],
        products: [],
        customers: [],
        orders: [],
        users: [
            { id: 1, username: "admin", password: "demo-password123", full_name: "Store Administrator", is_active: true, created_at: fmtDT(daysAgo(45)) },
        ],
        settings: {
            store_name: "My Kiosk Store",
            receipt_footer: "Thank you for your purchase!",
            currency: "EUR",
            payment_due_date: "",
            debug_mode: "false",
            customer_self_service_payment: "false",
            kiosk_idle_seconds: "90",
            kiosk_barcode_scanning: "false",
            backup_interval_hours: "24",
            backup_keep: "7",
        },
        restocks: [],
        audit: [],
        tokens: {},
        nextId: { product: 100, customer: 100, order: 100, item: 100, user: 100, restock: 1, audit: 1 },
    };

    const CAT_ID = (name) => DB.categories.find((c) => c.name === name).id;
    DB.products = [
        { id: 1, name: "USB-C Cable", description: "2m fast charging cable", price: 9.99, special_price: null, is_weekly_special: false, stock: 49, is_active: true, category_id: CAT_ID("Electronics"), image_path: svgImage("🔌", "#e2e8f0"), created_at: fmtDT(daysAgo(45)) },
        { id: 2, name: "Wireless Mouse", description: "Compact wireless mouse", price: 24.99, special_price: null, is_weekly_special: false, stock: 24, is_active: true, category_id: CAT_ID("Electronics"), image_path: svgImage("🖱️", "#e2e8f0"), created_at: fmtDT(daysAgo(45)) },
        { id: 3, name: "Bluetooth Earbuds", description: "True wireless earbuds with case", price: 49.99, special_price: 39.99, is_weekly_special: true, stock: 12, is_active: true, category_id: CAT_ID("Electronics"), image_path: svgImage("🎧", "#c7d2fe"), created_at: fmtDT(daysAgo(45)) },
        { id: 4, name: "Potato Chips", description: "Classic salted chips", price: 2.99, special_price: null, is_weekly_special: false, stock: 98, is_active: true, category_id: CAT_ID("Snacks"), image_path: svgImage("🍟", "#fde68a"), created_at: fmtDT(daysAgo(45)) },
        { id: 5, name: "Chocolate Bar", description: "Milk chocolate 100g", price: 3.49, special_price: null, is_weekly_special: false, stock: 79, is_active: true, category_id: CAT_ID("Snacks"), image_path: svgImage("🍫", "#fecaca"), created_at: fmtDT(daysAgo(45)) },
        { id: 6, name: "Trail Mix", description: "Nuts and dried fruit", price: 5.99, special_price: null, is_weekly_special: false, stock: 3, is_active: true, category_id: CAT_ID("Snacks"), image_path: svgImage("🥜", "#d9f99d"), created_at: fmtDT(daysAgo(45)) },
        { id: 7, name: "Bottled Water", description: "500ml still water", price: 1.49, special_price: null, is_weekly_special: false, stock: 199, is_active: true, category_id: CAT_ID("Beverages"), image_path: svgImage("💧", "#bae6fd"), created_at: fmtDT(daysAgo(45)) },
        { id: 8, name: "Cola", description: "Carbonated cola 330ml", price: 1.99, special_price: null, is_weekly_special: false, stock: 149, is_active: true, category_id: CAT_ID("Beverages"), image_path: svgImage("🥤", "#fed7aa"), created_at: fmtDT(daysAgo(45)) },
        { id: 9, name: "Orange Juice", description: "Fresh squeezed 1L", price: 4.99, special_price: null, is_weekly_special: false, stock: 60, is_active: true, category_id: CAT_ID("Beverages"), image_path: svgImage("🍊", "#fde047"), created_at: fmtDT(daysAgo(45)) },
        { id: 10, name: "Cotton T-Shirt", description: "100% cotton, multiple sizes", price: 14.99, special_price: null, is_weekly_special: false, stock: 20, is_active: true, category_id: CAT_ID("Clothing"), image_path: svgImage("👕", "#ddd6fe"), created_at: fmtDT(daysAgo(45)) },
        { id: 11, name: "Baseball Cap", description: "Adjustable cotton cap", price: 12.99, special_price: null, is_weekly_special: false, stock: 4, is_active: true, category_id: CAT_ID("Clothing"), image_path: svgImage("🧢", "#cbd5e1"), created_at: fmtDT(daysAgo(45)) },
    ];

    // Purchase prices (~60% of the price), restock thresholds and an optional
    // schedule for the special, mirroring backend/seed.py.
    for (const p of DB.products) {
        p.cost_price = Math.round(p.price * 0.6 * 100) / 100;
        p.low_stock_threshold = 5;
        p.special_starts_on = null;
        p.special_ends_on = null;
    }

    function addOrder(order) {
        order.id = DB.nextId.order++;
        order.created_at = order.created_at || fmtDT(new Date());
        order.items.forEach((it) => {
            it.id = DB.nextId.item++;
            it.order_id = order.id;
            if (it.unit_cost === undefined) {
                const product = DB.products.find((p) => p.id === it.product_id);
                it.unit_cost = product ? product.cost_price : null;
            }
        });
        DB.orders.push(order);
        return order;
    }

    DB.customers = [
        { id: 1, username: "alice", created_at: fmtDT(daysAgo(30)) },
        { id: 2, username: "bob", created_at: fmtDT(daysAgo(20)) },
        { id: 3, username: "carol", created_at: fmtDT(daysAgo(14)) },
    ];

    addOrder({
        status: "paid", subtotal: 5.98, total: 5.98, notes: "", customer_id: 1,
        created_at: fmtDT(daysAgo(6, 11)), completed_at: fmtDT(daysAgo(6, 11)), due_date: null,
        items: [{ product_id: 4, product_name: "Potato Chips", quantity: 2, unit_price: 2.99 }],
    });
    addOrder({
        status: "paid", subtotal: 24.99, total: 24.99, notes: "", customer_id: 2,
        created_at: fmtDT(daysAgo(3, 12)), completed_at: fmtDT(daysAgo(3, 12)), due_date: null,
        items: [{ product_id: 2, product_name: "Wireless Mouse", quantity: 1, unit_price: 24.99 }],
    });
    addOrder({
        status: "paid", subtotal: 7.48, total: 7.48, notes: "", customer_id: 1,
        created_at: fmtDT(daysAgo(1, 12)), completed_at: fmtDT(daysAgo(1, 12)), due_date: null,
        items: [
            { product_id: 7, product_name: "Bottled Water", quantity: 1, unit_price: 1.49 },
            { product_id: 6, product_name: "Trail Mix", quantity: 1, unit_price: 5.99 },
        ],
    });
    addOrder({
        status: "pending", subtotal: 1.99, total: 1.99, notes: "", customer_id: 1,
        created_at: fmtDT(hoursAgo(3)), completed_at: null, due_date: null,
        items: [{ product_id: 8, product_name: "Cola", quantity: 1, unit_price: 1.99 }],
    });
    addOrder({
        status: "pending", subtotal: 3.49, total: 3.49, notes: "", customer_id: 2,
        created_at: fmtDT(hoursAgo(1)), completed_at: null, due_date: null,
        items: [{ product_id: 5, product_name: "Chocolate Bar", quantity: 1, unit_price: 3.49 }],
    });
    addOrder({
        status: "paid", subtotal: 9.99, total: 9.99, notes: "", customer_id: 2,
        created_at: fmtDT(hoursAgo(2)), completed_at: fmtDT(hoursAgo(2)), due_date: null,
        items: [{ product_id: 1, product_name: "USB-C Cable", quantity: 1, unit_price: 9.99 }],
    });
    addOrder({
        status: "paid", subtotal: 12.99, total: 12.99, notes: "", customer_id: 3,
        created_at: fmtDT(daysAgo(12, 14)), completed_at: fmtDT(daysAgo(12, 14)), due_date: null,
        items: [{ product_id: 11, product_name: "Baseball Cap", quantity: 1, unit_price: 12.99 }],
    });

    function today() { return fmtDT(new Date()).slice(0, 10); }

    function specialActive(p) {
        if (!p.is_weekly_special || p.special_price == null) return false;
        if (p.special_starts_on && today() < p.special_starts_on) return false;
        if (p.special_ends_on && today() > p.special_ends_on) return false;
        return true;
    }

    function effectivePrice(p) {
        return specialActive(p) ? p.special_price : p.price;
    }

    function round2(n) { return Math.round(n * 100) / 100; }

    function audit(actor, action, entity, entityId, details) {
        DB.audit.push({
            id: DB.nextId.audit++, created_at: fmtDT(new Date()), actor, action,
            entity: entity || "", entity_id: String(entityId ?? ""), details: details || "",
        });
    }

    function actorOf(init) {
        return currentUser(init)?.username || "system";
    }

    function addRestock(product, quantity, unitCost, note, by, createdAt) {
        product.stock += quantity;
        if (unitCost != null) product.cost_price = unitCost;
        const restock = {
            id: DB.nextId.restock++, product_id: product.id, product_name: product.name,
            quantity, unit_cost: unitCost ?? null, stock_after: product.stock,
            note: (note || "").trim(), created_by: by, created_at: createdAt || fmtDT(new Date()),
        };
        DB.restocks.push(restock);
        return restock;
    }

    // Two past deliveries for the history views (stock levels stay as seeded).
    for (const [id, quantity, cost, note, days] of [[8, 48, 1.19, "Weekly delivery", 5], [4, 24, 1.79, "", 2]]) {
        const product = DB.products.find((p) => p.id === id);
        DB.restocks.push({
            id: DB.nextId.restock++, product_id: id, product_name: product.name, quantity,
            unit_cost: cost, stock_after: product.stock, note, created_by: "admin",
            created_at: fmtDT(daysAgo(days, 9)),
        });
        DB.audit.push({
            id: DB.nextId.audit++, created_at: fmtDT(daysAgo(days, 9)), actor: "admin",
            action: "product.restock", entity: "product", entity_id: String(id),
            details: `${product.name}: +${quantity} at ${cost} each; stock now ${product.stock}`,
        });
    }

    function dueTime() {
        const raw = DB.settings.payment_due_date;
        if (!raw) return null;
        return raw + "T23:59:59";
    }

    function categoryOf(product) {
        return DB.categories.find((c) => c.id === product.category_id) || null;
    }

    function productOut(p, admin) {
        return {
            id: p.id, name: p.name, description: p.description, price: p.price,
            special_price: p.special_price, is_weekly_special: p.is_weekly_special,
            special_starts_on: p.special_starts_on || null,
            special_ends_on: p.special_ends_on || null,
            special_active: specialActive(p),
            // Purchase prices are staff-only, as in the real API.
            cost_price: admin ? (p.cost_price ?? null) : null,
            stock: p.stock, low_stock_threshold: p.low_stock_threshold ?? 5,
            is_active: p.is_active, category_id: p.category_id,
            barcodes: p.barcodes || [],
            category: categoryOf(p),
            image_url: p.image_path || null,
        };
    }

    function lowStockProducts() {
        return DB.products
            .filter((p) => p.is_active && p.stock <= (p.low_stock_threshold ?? 5))
            .sort((a, b) => a.stock - b.stock || a.name.localeCompare(b.name))
            .map((p) => ({
                id: p.id, name: p.name, stock: p.stock, low_stock_threshold: p.low_stock_threshold ?? 5,
                price: p.price, special_price: p.special_price, is_weekly_special: p.is_weekly_special,
                special_active: specialActive(p), cost_price: p.cost_price ?? null,
            }));
    }

    function marginsFor(start, end) {
        const byName = {};
        for (const o of DB.orders) {
            if (o.status !== "paid") continue;
            const paidAt = new Date(o.completed_at || o.created_at);
            if (start && paidAt < start) continue;
            if (end && paidAt >= end) continue;
            for (const it of o.items) {
                const row = byName[it.product_name] ||
                    { quantity: 0, revenue: 0, costedRevenue: 0, cost: 0, uncosted: 0 };
                const revenue = it.unit_price * it.quantity;
                row.quantity += it.quantity;
                row.revenue += revenue;
                if (it.unit_cost != null) {
                    row.costedRevenue += revenue;
                    row.cost += it.unit_cost * it.quantity;
                } else {
                    row.uncosted += it.quantity;
                }
                byName[it.product_name] = row;
            }
        }
        const out = (name, r) => {
            const margin = r.costedRevenue - r.cost;
            const row = {
                quantity: r.quantity, revenue: round2(r.revenue), cost: round2(r.cost),
                margin: round2(margin),
                margin_pct: r.costedRevenue ? Math.round((margin / r.costedRevenue) * 1000) / 10 : null,
                uncosted_quantity: r.uncosted,
            };
            return name == null ? row : { product: name, ...row };
        };
        const rows = Object.keys(byName).map((name) => out(name, byName[name]))
            .sort((a, b) => b.margin - a.margin || b.revenue - a.revenue || a.product.localeCompare(b.product));
        const sum = (key) => Object.values(byName).reduce((s, r) => s + r[key], 0);
        return {
            products: rows,
            totals: out(null, {
                quantity: sum("quantity"), revenue: sum("revenue"), costedRevenue: sum("costedRevenue"),
                cost: sum("cost"), uncosted: sum("uncosted"),
            }),
        };
    }

    function periodBounds(period) {
        const now = new Date();
        const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        if (period === "today") return [t0, new Date(t0.getFullYear(), t0.getMonth(), t0.getDate() + 1)];
        if (period === "week") {
            const week = new Date(t0);
            week.setDate(week.getDate() - ((week.getDay() + 6) % 7));
            return [week, new Date(week.getFullYear(), week.getMonth(), week.getDate() + 7)];
        }
        if (period === "month") {
            return [new Date(now.getFullYear(), now.getMonth(), 1), new Date(now.getFullYear(), now.getMonth() + 1, 1)];
        }
        return [null, null];
    }

    function favoritesFor(customerId) {
        const byProduct = {};
        for (const o of DB.orders) {
            if (o.customer_id !== customerId || o.status === "cancelled") continue;
            for (const it of o.items) {
                const product = DB.products.find((p) => p.id === it.product_id);
                if (!product || !product.is_active) continue;
                byProduct[product.id] = (byProduct[product.id] || 0) + it.quantity;
            }
        }
        return Object.keys(byProduct)
            .map((id) => {
                const product = DB.products.find((p) => p.id === Number(id));
                return { product_id: product.id, name: product.name, quantity: byProduct[id] };
            })
            .sort((a, b) => b.quantity - a.quantity || a.name.localeCompare(b.name))
            .slice(0, 5);
    }

    function orderItems(o) {
        return o.items.map((it) => ({
            id: it.id, product_id: it.product_id, product_name: it.product_name,
            quantity: it.quantity, unit_price: it.unit_price,
        }));
    }

    function orderOut(o) {
        return {
            id: o.id, status: o.status, subtotal: o.subtotal, total: o.total,
            notes: o.notes,
            customer_username: customerById(o.customer_id)?.username || null,
            created_at: o.created_at, completed_at: o.completed_at, due_date: o.due_date,
        };
    }

    function normalizeBarcodes(values) {
        return [...new Set((Array.isArray(values) ? values : [])
            .filter((code) => typeof code === "string")
            .map((code) => code.trim().toLowerCase())
            .filter(Boolean))];
    }

    function assertUniqueBarcodes(barcodes, productId) {
        for (const code of barcodes) {
            if (DB.products.some((p) =>
                p.id !== productId && (p.barcodes || []).includes(code))) {
                throw new ApiError(HTTP.CONFLICT, "A barcode is already assigned to another product");
            }
        }
    }

    function statsFor(customerId) {
        const orders = DB.orders
            .filter((o) => o.customer_id === customerId)
            .sort((a, b) => (a.created_at < b.created_at ? -1 : 1));
        const paid = orders.filter((o) => o.status === "paid")
            .reduce((s, o) => s + o.total, 0);
        const pending = orders.filter((o) => o.status === "pending")
            .reduce((s, o) => s + o.total, 0);
        const total = orders.reduce((s, o) => s + o.total, 0);
        const count = orders.length;

        const itemsBought = orders.reduce((s, o) =>
            s + o.items.reduce((x, it) => x + it.quantity, 0), 0);

        const byName = {};
        for (const o of orders) for (const it of o.items) {
            byName[it.product_name] = (byName[it.product_name] || 0) + it.quantity;
        }
        let topItem = null, topQty = 0;
        for (const name of Object.keys(byName)) {
            if (byName[name] > topQty) { topItem = name; topQty = byName[name]; }
        }

        const perMonth = {}, monthSpent = {};
        const perWeekday = {}, weekdaySpent = {};
        for (const o of orders) {
            const key = (o.created_at || "").slice(0, 7);
            perMonth[key] = (perMonth[key] || 0) + 1;
            monthSpent[key] = (monthSpent[key] || 0) + o.total;
            const w = WEEKDAYS.indexOf(weekdayName(o.created_at));
            perWeekday[w] = (perWeekday[w] || 0) + 1;
            weekdaySpent[w] = (weekdaySpent[w] || 0) + o.total;
        }

        let busiestDay = null, busiestCount = 0;
        const monthKeys = Object.keys(perMonth);
        for (let w = 0; w < 7; w++) {
            if ((perWeekday[w] || 0) > busiestCount) { busiestDay = WEEKDAYS[w]; busiestCount = perWeekday[w]; }
        }

        const monthCount = monthKeys.length || 1;
        const ordersPerMonth = Object.keys(perMonth).sort().map((k) => ({
            month: k, orders: perMonth[k], spent: Math.round(monthSpent[k] * 100) / 100,
        }));
        const ordersByWeekday = [];
        for (let w = 0; w < 7; w++) {
            if (perWeekday[w]) {
                ordersByWeekday.push({
                    day: WEEKDAYS[w], orders: perWeekday[w],
                    spent: Math.round(weekdaySpent[w] * 100) / 100,
                });
            }
        }

        return {
            orders: count,
            paid_orders: orders.filter((o) => o.status === "paid").length,
            pending_orders: orders.filter((o) => o.status === "pending").length,
            cancelled_orders: orders.filter((o) => o.status === "cancelled").length,
            total_spent: Math.round(total * 100) / 100,
            total_paid: Math.round(paid * 100) / 100,
            balance: Math.round(pending * 100) / 100,
            avg_order: count ? Math.round((total / count) * 100) / 100 : 0,
            items_bought: itemsBought,
            first_order_at: orders[0] ? orders[0].created_at : null,
            last_order_at: orders.length ? orders[orders.length - 1].created_at : null,
            last_paid_at: orders.filter((o) => o.status === "paid")
                .map((o) => o.completed_at || o.created_at).sort().slice(-1)[0] || null,
            last_paid_amount: (() => {
                const lastPaid = orders.filter((o) => o.status === "paid")
                    .sort((a, b) => (a.completed_at || a.created_at).localeCompare(b.completed_at || b.created_at))
                    .slice(-1)[0];
                return lastPaid ? lastPaid.total : 0;
            })(),
            top_item: topItem,
            top_item_qty: topQty,
            avg_orders_per_month: Math.round((count / monthCount) * 100) / 100,
            busiest_day: busiestDay,
            orders_per_month: ordersPerMonth,
            orders_by_weekday: ordersByWeekday,
            next_due_date: dueTime(),
        };
    }

    function weekdayName(isoStr) {
        return WEEKDAYS[(new Date(isoStr).getDay() + 6) % 7];
    }

    function customerById(id) { return DB.customers.find((c) => c.id === id); }

    function findCustomer(username) {
        const name = (username || "").trim().toLowerCase().normalize("NFC");
        return DB.customers.find((c) => c.username === name);
    }

    function getOrCreateCustomer(username) {
        const name = (username || "").trim().toLowerCase().normalize("NFC");
        if (!name) return null;
        let c = findCustomer(name);
        if (!c) {
            // Same rules as backend routers/customers.py::validate_new_username.
            if (name.length > 64) throw new ApiError(HTTP.UNPROCESSABLE, "Username must be at most 64 characters");
            if (/\p{C}/u.test(name)) throw new ApiError(HTTP.UNPROCESSABLE, "Username contains characters that are not allowed");
            c = { id: DB.nextId.customer++, username: name, created_at: fmtDT(new Date()) };
            DB.customers.push(c);
        }
        return c;
    }

    // Customer PINs. The real backend stores Argon2id(HMAC(pepper, pin)); this
    // in-browser demo keeps the PIN in memory only, since nothing is persisted.
    function customerOut(c) {
        return { id: c.id, username: c.username, created_at: c.created_at, has_pin: !!c.pin };
    }

    function pinFrom(init) {
        const hdr = (init && init.headers) || {};
        return hdr["X-Customer-PIN"] || hdr["x-customer-pin"] || "";
    }

    function checkPin(customer, pin) {
        if (!customer.pin) return;
        const now = Date.now();
        if (customer.pinLockedUntil && customer.pinLockedUntil > now) {
            const minutes = Math.ceil((customer.pinLockedUntil - now) / 60000);
            throw new ApiError(HTTP.TOO_MANY, `Too many wrong PINs. Try again in ${minutes} minute(s).`);
        }
        if (!pin) throw new ApiError(HTTP.PRECONDITION_REQUIRED, "PIN required");
        if (pin !== customer.pin) {
            customer.pinFailed = (customer.pinFailed || 0) + 1;
            if (customer.pinFailed >= 5) {
                customer.pinFailed = 0;
                customer.pinLockedUntil = now + 15 * 60000;
                audit("kiosk", "customer.pin_locked", "customer", customer.username, "5 wrong PINs; locked for 15 min");
            }
            throw new ApiError(HTTP.FORBIDDEN, "Wrong PIN");
        }
        customer.pinFailed = 0;
        customer.pinLockedUntil = null;
    }

    function pendingOrdersFor(customerId) {
        return DB.orders.filter((o) => o.customer_id === customerId && o.status === "pending");
    }

    function revenueForPeriod(start, end) {
        let sum = 0, count = 0;
        for (const o of DB.orders) {
            if (o.status !== "paid") continue;
            const paidAt = o.completed_at || o.created_at;
            if (start && paidAt < start) continue;
            if (end && paidAt >= end) continue;
            sum += o.total;
            count += 1;
        }
        return { order_count: count, revenue: Math.round(sum * 100) / 100 };
    }

    function reportsSummary() {
        const now = new Date();
        const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const todayStart = fmtDT(t0);
        const tomorrowStart = fmtDT(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
        const yStart = fmtDT(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
        const weekStart = new Date(t0);
        weekStart.setDate(weekStart.getDate() - ((weekStart.getDay() + 6) % 7));
        const nextWeek = new Date(weekStart);
        nextWeek.setDate(nextWeek.getDate() + 7);
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
        const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
        const lowStock = lowStockProducts();
        return {
            today: revenueForPeriod(todayStart, tomorrowStart),
            yesterday: revenueForPeriod(yStart, todayStart),
            week: revenueForPeriod(fmtDT(weekStart), fmtDT(nextWeek)),
            month: revenueForPeriod(fmtDT(monthStart), fmtDT(nextMonth)),
            all_time: revenueForPeriod(),
            outstanding: Math.round(DB.orders.filter((o) => o.status === "pending").reduce((s, o) => s + o.total, 0) * 100) / 100,
            pending_orders: DB.orders.filter((o) => o.status === "pending").length,
            next_due_date: dueTime(),
            low_stock_products: lowStock,
            margin_month: marginsFor(monthStart, nextMonth).totals,
        };
    }

    function topProducts(limit) {
        const byName = {};
        for (const o of DB.orders) {
            if (o.status !== "paid") continue;
            for (const it of o.items) {
                const row = byName[it.product_name] || { quantity: 0, revenue: 0 };
                row.quantity += it.quantity;
                row.revenue += it.unit_price * it.quantity;
                byName[it.product_name] = row;
            }
        }
        return Object.keys(byName)
            .map((name) => ({
                product: name,
                quantity: byName[name].quantity,
                revenue: Math.round(byName[name].revenue * 100) / 100,
            }))
            .sort((a, b) => b.quantity - a.quantity || b.revenue - a.revenue)
            .slice(0, limit);
    }

    function salesByDay(days) {
        const start = fmtDT(daysAgo(days));
        const byDay = {};
        for (const o of DB.orders) {
            const paidAt = o.completed_at || o.created_at;
            if (o.status !== "paid" || paidAt < start) continue;
            const day = paidAt.slice(0, 10);
            const row = byDay[day] || { orders: 0, revenue: 0 };
            row.orders += 1;
            row.revenue += o.total;
            byDay[day] = row;
        }
        return Object.keys(byDay).sort().map((day) => ({
            day, orders: byDay[day].orders, revenue: Math.round(byDay[day].revenue * 100) / 100,
        }));
    }

    function customerInsights(limit) {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const week = new Date(today);
        week.setDate(week.getDate() - ((week.getDay() + 6) % 7));
        const month = new Date(now.getFullYear(), now.getMonth(), 1);
        const leaderRows = (start, end) => {
            const byCustomer = {};
            for (const o of DB.orders) {
                const paidAt = new Date(o.completed_at || o.created_at);
                if (o.status !== "paid" || paidAt < start || paidAt >= end) continue;
                const customer = customerById(o.customer_id);
                if (!customer) continue;
                const row = byCustomer[customer.username] || { username: customer.username, orders: 0, spent: 0 };
                row.orders += 1;
                row.spent += o.total;
                byCustomer[customer.username] = row;
            }
            return Object.values(byCustomer)
                .sort((a, b) => b.spent - a.spent || b.orders - a.orders || a.username.localeCompare(b.username))
                .slice(0, limit)
                .map((row) => ({ ...row, spent: Math.round(row.spent * 100) / 100 }));
        };
        const paidOrders = DB.orders.filter((o) => o.status === "paid").sort((a, b) =>
            (a.completed_at || a.created_at).localeCompare(b.completed_at || b.created_at) || a.id - b.id);
        const latest = paidOrders[paidOrders.length - 1];
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        const nextWeek = new Date(week);
        nextWeek.setDate(nextWeek.getDate() + 7);
        const nextMonth = new Date(month.getFullYear(), month.getMonth() + 1, 1);
        return {
            today: leaderRows(today, tomorrow),
            week: leaderRows(week, nextWeek),
            month: leaderRows(month, nextMonth),
            products_today: productRows(today, tomorrow, limit),
            products_week: productRows(week, nextWeek, limit),
            products_month: productRows(month, nextMonth, limit),
            last_paid: latest ? {
                username: customerById(latest.customer_id)?.username || null,
                order_id: latest.id,
                amount: latest.total,
                paid_at: latest.completed_at || latest.created_at,
            } : null,
        };
    }

    function productRows(start, end, limit) {
        const byName = {};
        for (const o of DB.orders) {
            const paidAt = new Date(o.completed_at || o.created_at);
            if (o.status !== "paid" || paidAt < start || paidAt >= end) continue;
            for (const item of o.items) {
                const row = byName[item.product_name] || { product: item.product_name, quantity: 0, revenue: 0 };
                row.quantity += item.quantity;
                row.revenue += item.quantity * item.unit_price;
                byName[item.product_name] = row;
            }
        }
        return Object.values(byName)
            .sort((a, b) => b.quantity - a.quantity || b.revenue - a.revenue || a.product.localeCompare(b.product))
            .slice(0, limit)
            .map((row) => ({ ...row, revenue: Math.round(row.revenue * 100) / 100 }));
    }

    function reportCsvResponse() {
        const headers = [
            "section", "period", "record", "id", "name", "count",
            "quantity", "amount", "unit_price", "stock", "stock_value", "details",
        ];
        const rows = [headers];
        const add = (section, fields = {}) => rows.push(headers.map((key) => fields[key] ?? ""));
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const week = new Date(today);
        week.setDate(week.getDate() - ((week.getDay() + 6) % 7));
        const month = new Date(now.getFullYear(), now.getMonth(), 1);

        for (const period of ["today", "yesterday", "week", "month", "all_time"]) {
            const totals = reportsSummary()[period];
            add("sales_summary", {
                period, count: totals.order_count, amount: totals.revenue,
                details: "paid orders and revenue",
            });
        }

        const pending = DB.orders.filter((order) => order.status === "pending");
        add("outstanding", {
            record: "store_total", count: pending.length,
            amount: Math.round(pending.reduce((sum, order) => sum + order.total, 0) * 100) / 100,
            details: "total pending customer balance",
        });
        add("payment_due_date", {
            record: "store",
            details: reportsSummary().next_due_date || "not configured",
        });
        for (const customer of DB.customers.slice().sort((a, b) => a.username.localeCompare(b.username))) {
            const orders = pending.filter((order) => order.customer_id === customer.id);
            const stats = statsFor(customer.id);
            add("customer_summary", {
                record: "lifetime", id: customer.id, name: customer.username,
                count: stats.orders, amount: stats.total_paid,
                details: "paid orders: " + stats.paid_orders,
            });
            add("customer_balance", {
                record: "pending", id: customer.id, name: customer.username,
                count: orders.length,
                amount: Math.round(orders.reduce((sum, order) => sum + order.total, 0) * 100) / 100,
                details: "pending orders: " + orders.map((order) =>
                    `#${order.id} due ${order.due_date || "not set"}`).join("; "),
            });
        }
        for (const product of DB.products.slice().sort((a, b) => a.name.localeCompare(b.name))) {
            const price = effectivePrice(product);
            const cost = product.cost_price != null
                ? `; cost price ${product.cost_price}; value at cost ${round2(product.stock * product.cost_price)}`
                : "; cost price not set";
            add("inventory", {
                record: product.is_active ? "active" : "inactive",
                id: product.id, name: product.name, unit_price: price, stock: product.stock,
                stock_value: Math.round(product.stock * price * 100) / 100,
                details: "category: " + (categoryOf(product)?.name || "") +
                    "; value at current selling price" + cost,
            });
        }
        for (const product of lowStockProducts()) {
            add("restock_needed", {
                record: "low_stock", id: product.id, name: product.name, stock: product.stock,
                details: `threshold ${product.low_stock_threshold}`,
            });
        }
        for (const period of ["month", "all"]) {
            const [start, end] = periodBounds(period);
            const report = marginsFor(start, end);
            const label = period === "all" ? "all_time" : period;
            for (const row of report.products) {
                add("margins", {
                    period: label, record: "product", name: row.product, quantity: row.quantity,
                    amount: row.margin,
                    details: `revenue ${row.revenue}; cost ${row.cost}; margin ${row.margin_pct ?? "-"}%; ` +
                        `units without cost ${row.uncosted_quantity}`,
                });
            }
            add("margins", {
                period: label, record: "store_total", quantity: report.totals.quantity,
                amount: report.totals.margin,
                details: `revenue ${report.totals.revenue}; cost ${report.totals.cost}`,
            });
        }

        for (const day of salesByDay(14)) {
            add("daily_sales", {
                period: day.day, count: day.orders, amount: day.revenue,
                details: "paid orders and revenue",
            });
        }
        const insights = customerInsights(20);
        for (const period of ["today", "week", "month"]) {
            for (const [index, customer] of insights[period].entries()) {
                add("top_customers", {
                    period, record: `rank_${index + 1}`, name: customer.username,
                    count: customer.orders, amount: customer.spent,
                });
            }
            const start = period === "today" ? today : period === "week" ? week : month;
            const end = period === "today"
                ? new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1)
                : period === "week"
                    ? new Date(week.getFullYear(), week.getMonth(), week.getDate() + 7)
                    : new Date(month.getFullYear(), month.getMonth() + 1, 1);
            for (const [index, product] of productRows(start, end, 20).entries()) {
                add("top_products", {
                    period, record: `rank_${index + 1}`, name: product.product,
                    quantity: product.quantity, amount: product.revenue,
                });
            }
        }
        for (const [index, product] of topProducts(20).entries()) {
            add("top_products", {
                period: "all_time", record: `rank_${index + 1}`, name: product.product,
                quantity: product.quantity, amount: product.revenue,
            });
        }
        if (insights.last_paid) {
            add("last_payment", {
                record: "latest", id: insights.last_paid.order_id,
                name: insights.last_paid.username, amount: insights.last_paid.amount,
                details: insights.last_paid.paid_at,
            });
        }

        const escapeCell = (value) => {
            const text = String(value);
            const safe = typeof value === "string" &&
                text.trimStart().match(/^[=+\-@\t\r]/) ? "'" + text : text;
            return `"${safe.replace(/"/g, '""')}"`;
        };
        const body = "\uFEFF" + rows.map((row) => row.map(escapeCell).join(",")).join("\r\n");
        return new Response(body, {
            headers: {
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": 'attachment; filename="kiosk-report-demo.csv"',
            },
        });
    }

    function userOut(u) {
        return {
            id: u.id, username: u.username, full_name: u.full_name || "",
            is_active: u.is_active, created_at: u.created_at,
        };
    }

    const HTTP = {
        OK: 200,
        CREATED: 201,
        NO_CONTENT: 204,
        BAD_REQUEST: 400,
        UNAUTHORIZED: 401,
        FORBIDDEN: 403,
        CONFLICT: 409,
        NOT_FOUND: 404,
        UNPROCESSABLE: 422,
        PRECONDITION_REQUIRED: 428,
        TOO_MANY: 429,
    };

    function response(status, data) {
        return { __status: status, __data: data };
    }
    function noContent() {
        return { __status: HTTP.NO_CONTENT };
    }

    class ApiError extends Error {
        constructor(status, detail) {
            super(detail);
            this.status = status;
            this.detail = detail;
        }
    }

    function currentUser(init) {
        const hdr = (init && init.headers) || {};
        const auth = hdr.Authorization || hdr.authorization || "";
        const token = /^Bearer\s+(.+)$/.exec(auth || "");
        if (!token) return null;
        const username = DB.tokens[token[1]];
        if (!username) return null;
        return DB.users.find((u) => u.username === username) || null;
    }

    function requireAdmin(init) {
        if (!currentUser(init)) {
            throw new ApiError(HTTP.UNAUTHORIZED, "Not authenticated");
        }
    }

    async function handle(path, query, method, init) {
        const body = (() => {
            if (!init || !init.body) return null;
            if (init.body instanceof FormData) return init.body;
            try { return JSON.parse(init.body); } catch { return null; }
        })();
        const parts = path.split("/").filter(Boolean); // e.g. ["products","3","image"]

        if (path === "/categories" && method === "GET") {
            return DB.categories.slice().sort((a, b) => a.sort_order - b.sort_order);
        }
        if (path === "/categories" && method === "POST") {
            requireAdmin(init);
            const id = DB.nextId.category;
            DB.nextId.category++;
            const cat = { id, name: body.name, description: body.description || "", sort_order: body.sort_order || 0 };
            DB.categories.push(cat);
            return response(HTTP.CREATED, cat);
        }
        if (parts.length === 2 && parts[0] === "categories" && method === "PUT") {
            requireAdmin(init);
            const cat = DB.categories.find((c) => c.id === Number(parts[1]));
            if (!cat) throw new ApiError(HTTP.NOT_FOUND, "Category not found");
            if (body.name !== undefined) cat.name = body.name;
            if (body.description !== undefined) cat.description = body.description;
            if (body.sort_order !== undefined) cat.sort_order = body.sort_order;
            for (const p of DB.products) if (p.category_id === cat.id) p.category_id = cat.id;
            return cat;
        }
        if (parts.length === 2 && parts[0] === "categories" && method === "DELETE") {
            requireAdmin(init);
            const id = Number(parts[1]);
            if (!DB.categories.some((c) => c.id === id)) throw new ApiError(HTTP.NOT_FOUND, "Category not found");
            DB.categories = DB.categories.filter((c) => c.id !== id);
            for (const p of DB.products) if (p.category_id === id) p.category_id = null;
            return noContent();
        }

        if (path === "/products" && method === "GET") {
            const activeOnly = query.get("active_only") !== "false";
            const catId = query.get("category_id") ? Number(query.get("category_id")) : null;
            const search = query.get("search");
            return DB.products
                .filter((p) => (activeOnly ? p.is_active : true))
                .filter((p) => (catId ? p.category_id === catId : true))
                .filter((p) => (search ? p.name.toLowerCase().includes(search.toLowerCase()) : true))
                .sort((a, b) => a.name.localeCompare(b.name))
                .map((p) => productOut(p, !!currentUser(init)));
        }
        if (path === "/products" && method === "POST") {
            requireAdmin(init);
            const id = DB.nextId.product++;
            const p = {
                id, name: body.name, description: body.description || "",
                price: body.price || 0, special_price: body.special_price ?? null,
                is_weekly_special: !!body.is_weekly_special,
                special_starts_on: body.special_starts_on || null,
                special_ends_on: body.special_ends_on || null,
                cost_price: body.cost_price ?? null,
                stock: body.stock || 0, low_stock_threshold: body.low_stock_threshold ?? 5,
                is_active: body.is_active !== false,
                category_id: body.category_id ?? null, image_path: null,
                barcodes: normalizeBarcodes(body.barcodes),
                created_at: fmtDT(new Date()),
            };
            assertSpecialWindow(p);
            assertUniqueBarcodes(p.barcodes, null);
            DB.products.push(p);
            audit(actorOf(init), "product.create", "product", p.id, `${p.name}; price ${p.price}; stock ${p.stock}`);
            return response(HTTP.CREATED, productOut(p, true));
        }
        if (parts.length === 2 && parts[0] === "products" && method === "PUT") {
            requireAdmin(init);
            const p = DB.products.find((x) => x.id === Number(parts[1]));
            if (!p) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            const before = { ...p };
            const fields = [
                "name", "description", "price", "special_price", "is_weekly_special",
                "special_starts_on", "special_ends_on", "cost_price", "stock",
                "low_stock_threshold", "is_active", "category_id",
            ];
            const next = { ...p };
            for (const field of fields) if (body[field] !== undefined) next[field] = body[field];
            assertSpecialWindow(next);
            if (body.barcodes !== undefined) {
                const barcodes = normalizeBarcodes(body.barcodes);
                assertUniqueBarcodes(barcodes, p.id);
                next.barcodes = barcodes;
            }
            Object.assign(p, next);
            const changes = fields.filter((f) => f !== "description" && (before[f] ?? null) !== (p[f] ?? null))
                .map((f) => `${f}: ${before[f] ?? "-"} -> ${p[f] ?? "-"}`);
            if (changes.length) audit(actorOf(init), "product.update", "product", p.id, `${p.name}: ${changes.join("; ")}`);
            return productOut(p, true);
        }
        if (parts.length === 3 && parts[0] === "products" && parts[1] === "barcode" && method === "GET") {
            const barcode = decodeURIComponent(parts[2]).trim().toLowerCase();
            const product = DB.products.find((p) =>
                p.is_active && (p.barcodes || []).includes(barcode));
            if (!product) throw new ApiError(HTTP.NOT_FOUND, "No active product found for barcode");
            return productOut(product, !!currentUser(init));
        }
        if (parts.length === 2 && parts[0] === "products" && method === "DELETE") {
            requireAdmin(init);
            const id = Number(parts[1]);
            const product = DB.products.find((p) => p.id === id);
            if (!product) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            DB.products = DB.products.filter((p) => p.id !== id);
            audit(actorOf(init), "product.delete", "product", id, `${product.name}; stock ${product.stock}`);
            return noContent();
        }
        if (parts.length === 3 && parts[0] === "products" && parts[2] === "restock" && method === "POST") {
            requireAdmin(init);
            const p = DB.products.find((x) => x.id === Number(parts[1]));
            if (!p) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            const quantity = Number(body.quantity);
            if (!Number.isInteger(quantity) || quantity < 1 || quantity > 100000) {
                throw new ApiError(HTTP.UNPROCESSABLE, "quantity must be between 1 and 100000");
            }
            if (body.unit_cost != null && body.unit_cost < 0) {
                throw new ApiError(HTTP.UNPROCESSABLE, "unit_cost must not be negative");
            }
            const restock = addRestock(p, quantity, body.unit_cost ?? null, body.note, actorOf(init));
            const cost = body.unit_cost != null ? ` at ${body.unit_cost} each` : "";
            audit(actorOf(init), "product.restock", "product", p.id, `${p.name}: +${quantity}${cost}; stock now ${p.stock}`);
            return response(HTTP.CREATED, restock);
        }
        if (parts.length === 3 && parts[0] === "products" && parts[2] === "restocks" && method === "GET") {
            requireAdmin(init);
            const id = Number(parts[1]);
            if (!DB.products.some((p) => p.id === id)) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            return DB.restocks.filter((r) => r.product_id === id).slice().reverse()
                .slice(0, Number(query.get("limit")) || 50);
        }
        if (path === "/restocks" && method === "GET") {
            requireAdmin(init);
            return DB.restocks.slice().reverse().slice(0, Number(query.get("limit")) || 50);
        }
        if (parts.length === 3 && parts[0] === "products" && parts[2] === "image" && method === "POST") {
            requireAdmin(init);
            const p = DB.products.find((x) => x.id === Number(parts[1]));
            if (!p) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            const file = body.get("file");
            if (!file) throw new ApiError(HTTP.BAD_REQUEST, "Empty file");
            p.image_path = await readAsDataURL(file);
            return productOut(p, true);
        }
        if (parts.length === 3 && parts[0] === "products" && parts[2] === "image" && method === "DELETE") {
            requireAdmin(init);
            const p = DB.products.find((x) => x.id === Number(parts[1]));
            if (!p) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            p.image_path = null;
            return productOut(p, true);
        }

        if (path === "/orders" && method === "GET") {
            requireAdmin(init);
            const status_ = query.get("status_");
            return DB.orders
                .filter((o) => (status_ ? o.status === status_ : true))
                .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
                .map((o) => orderOut(o));
        }
        if (parts.length === 3 && parts[0] === "orders" && parts[2] === "items" && method === "GET") {
            requireAdmin(init);
            const order = DB.orders.find((o) => o.id === Number(parts[1]));
            if (!order) throw new ApiError(HTTP.NOT_FOUND, "Order not found");
            return orderItems(order);
        }
        if (path === "/orders" && method === "POST") {
            const existing = findCustomer(body.customer_username);
            if (existing) checkPin(existing, body.customer_pin || "");
            const customer = getOrCreateCustomer(body.customer_username);
            if (!customer) throw new ApiError(HTTP.BAD_REQUEST, "A username is required");
            if (!body.items || body.items.length === 0) throw new ApiError(HTTP.BAD_REQUEST, "Order must contain items");
            const due = dueTime();
            if (due && new Date(due) < new Date() && pendingOrdersFor(customer.id).length > 0) {
                throw new ApiError(HTTP.FORBIDDEN, "The payment due date has passed and your previous order is still unpaid. Ask the staff to mark it as paid before you can buy again.");
            }
            const items = [];
            let subtotal = 0;
            for (const item of body.items) {
                const p = DB.products.find((x) => x.id === item.product_id);
                if (!p || !p.is_active) throw new ApiError(HTTP.BAD_REQUEST, `Product ${item.product_id} not available`);
                if (p.stock < item.quantity) throw new ApiError(HTTP.BAD_REQUEST, `Insufficient stock for '${p.name}' (${p.stock} left)`);
                p.stock -= item.quantity;
                const unit = effectivePrice(p);
                subtotal += unit * item.quantity;
                items.push({
                    product_id: p.id, product_name: p.name,
                    quantity: item.quantity, unit_price: unit,
                });
            }
            const order = addOrder({
                status: "pending", subtotal: Math.round(subtotal * 100) / 100,
                total: Math.round(subtotal * 100) / 100, notes: body.notes || "",
                customer_id: customer.id, created_at: fmtDT(new Date()),
                completed_at: null, due_date: dueTime(), items,
            });
            return response(HTTP.CREATED, orderOut(order));
        }
        if (parts.length === 3 && parts[0] === "orders" && parts[2] === "status" && method === "PATCH") {
            requireAdmin(init);
            const order = DB.orders.find((o) => o.id === Number(parts[1]));
            if (!order) throw new ApiError(HTTP.NOT_FOUND, "Order not found");
            const status = query.get("new_status");
            if (!["pending", "paid", "cancelled"].includes(status)) throw new ApiError(HTTP.BAD_REQUEST, "Invalid status");
            if (order.status === "pending" && status === "cancelled") {
                for (const it of order.items) {
                    const p = DB.products.find((x) => x.id === it.product_id);
                    if (p) p.stock += it.quantity;
                }
            }
            const previous = order.status;
            order.status = status;
            order.completed_at = status !== "pending" ? fmtDT(new Date()) : order.completed_at;
            if (previous !== status) {
                const restored = previous === "pending" && status === "cancelled" ? " (stock restored)" : "";
                audit(actorOf(init), "order." + status, "order", order.id,
                    `${customerById(order.customer_id)?.username || "-"}: ${previous} -> ${status}, total ${order.total}${restored}`);
            }
            return orderOut(order);
        }

        if (path === "/customers" && method === "GET") {
            requireAdmin(init);
            return DB.customers
                .slice()
                .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
                .map((c) => {
                    const stats = statsFor(c.id);
                    const orders = DB.orders.filter((o) => o.customer_id === c.id);
                    return {
                        ...customerOut(c),
                        balance: stats.balance, total_paid: stats.total_paid,
                        order_count: orders.length, stats,
                    };
                });
        }
        if (path === "/customers/suggest" && method === "GET") {
            const prefix = (query.get("q") || "").trim().toLowerCase();
            if (!prefix) return [];
            return DB.customers
                .map((c) => c.username)
                .filter((u) => u.startsWith(prefix))
                .sort()
                .slice(0, 20);
        }
        if (parts.length === 2 && parts[0] === "customers" && parts[1] === "suggest") {
            return [];
        }
        if (parts.length === 2 && parts[0] === "customers" && parts[1] !== "suggest" && method === "GET") {
            const customer = findCustomer(decodeURIComponent(parts[1]));
            if (!customer) throw new ApiError(HTTP.NOT_FOUND, "Customer not found");
            if (!(query.get("as_admin") === "true" && currentUser(init))) checkPin(customer, pinFrom(init));
            const orders = DB.orders
                .filter((o) => o.customer_id === customer.id)
                .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
            const stats = statsFor(customer.id);
            return {
                customer: customerOut(customer),
                balance: stats.balance, total_paid: stats.total_paid,
                orders: orders.map((o) => ({ ...orderOut(o), items: orderItems(o) })),
                stats,
                favorites: favoritesFor(customer.id),
            };
        }
        if (parts.length === 3 && parts[0] === "customers" &&
            parts[2] === "self-mark-paid" && method === "POST") {
            if (DB.settings.customer_self_service_payment !== "true") {
                throw new ApiError(HTTP.FORBIDDEN, "Customer self-service payment is disabled");
            }
            const customer = findCustomer(decodeURIComponent(parts[1]));
            if (!customer) throw new ApiError(HTTP.NOT_FOUND, "Customer not found");
            checkPin(customer, pinFrom(init));
            const pending = pendingOrdersFor(customer.id);
            let amount = 0;
            for (const order of pending) {
                order.status = "paid";
                order.completed_at = fmtDT(new Date());
                amount += order.total;
            }
            if (pending.length) {
                audit("kiosk", "customer.self_mark_paid", "customer", customer.username,
                    `${pending.length} order(s) marked paid: ${pending.map((o) => "#" + o.id).join(", ")}; amount ${round2(amount)}`);
            }
            return {
                username: customer.username,
                settled: pending.length,
                amount: Math.round(amount * 100) / 100,
            };
        }
        if (parts.length === 3 && parts[0] === "customers" && parts[2] === "pin" && method === "POST") {
            const customer = findCustomer(decodeURIComponent(parts[1]));
            if (!customer) throw new ApiError(HTTP.NOT_FOUND, "Customer not found");
            if (!/^[0-9]{4,8}$/.test(body.pin || "")) throw new ApiError(HTTP.UNPROCESSABLE, "The PIN must be 4 to 8 digits");
            const changing = !!customer.pin;
            if (changing) checkPin(customer, body.current_pin || "");
            customer.pin = body.pin;
            audit("kiosk", changing ? "customer.pin_changed" : "customer.pin_set", "customer", customer.username);
            return { username: customer.username, has_pin: true };
        }
        if (parts.length === 3 && parts[0] === "customers" && parts[2] === "reset-pin" && method === "POST") {
            requireAdmin(init);
            const customer = findCustomer(decodeURIComponent(parts[1]));
            if (!customer) throw new ApiError(HTTP.NOT_FOUND, "Customer not found");
            if (customer.pin) {
                if (pendingOrdersFor(customer.id).length) {
                    throw new ApiError(HTTP.CONFLICT, "The customer has unpaid orders. Settle the balance before resetting the PIN.");
                }
                customer.pin = null;
                customer.pinFailed = 0;
                customer.pinLockedUntil = null;
                audit(actorOf(init), "customer.pin_reset", "customer", customer.username);
            }
            return { username: customer.username, has_pin: false };
        }
        if (parts.length === 3 && parts[0] === "customers" && parts[2] === "reset-payment" && method === "POST") {
            requireAdmin(init);
            const customer = findCustomer(decodeURIComponent(parts[1]));
            if (!customer) throw new ApiError(HTTP.NOT_FOUND, "Customer not found");
            const pending = pendingOrdersFor(customer.id);
            let amount = 0;
            for (const o of pending) {
                o.status = "paid";
                o.completed_at = fmtDT(new Date());
                amount += o.total;
            }
            if (pending.length) {
                audit(actorOf(init), "customer.reset_payment", "customer", customer.username,
                    `${pending.length} order(s) marked paid: ${pending.map((o) => "#" + o.id).join(", ")}; amount ${round2(amount)}`);
            }
            return {
                username: customer.username,
                settled: pending.length,
                amount: Math.round(amount * 100) / 100,
            };
        }

        if (path === "/settings" && method === "GET") {
            return { ...DB.settings };
        }
        if (parts.length === 2 && parts[0] === "settings" && method === "PUT") {
            requireAdmin(init);
            const previous = DB.settings[parts[1]];
            DB.settings[parts[1]] = body.value;
            if (previous !== body.value) {
                audit(actorOf(init), "settings.update", "setting", parts[1],
                    `${parts[1]}: ${previous || "-"} -> ${body.value || "-"}`);
            }
            return { key: parts[1], value: body.value };
        }

        if (path === "/auth/login" && method === "POST") {
            const user = DB.users.find((u) => u.username === (body.username || "").trim().toLowerCase());
            if (!user || user.password !== body.password) {
                throw new ApiError(HTTP.UNAUTHORIZED, "Incorrect username or password");
            }
            if (!user.is_active) {
                throw new ApiError(HTTP.UNAUTHORIZED, "User is disabled");
            }
            const token = "demo." + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
            DB.tokens[token] = user.username;
            return { access_token: token, token_type: "bearer", user: userOut(user) };
        }

        if (path === "/users" && method === "GET") {
            requireAdmin(init);
            return DB.users.map((u) => userOut(u));
        }
        if (path === "/users" && method === "POST") {
            requireAdmin(init);
            if (!body.username || !body.password) throw new ApiError(HTTP.BAD_REQUEST, "username and password are required");
            if (body.password.length < 8) throw new ApiError(HTTP.BAD_REQUEST, `password must be at least 8 characters`);
            if (DB.users.some((u) => u.username === body.username)) throw new ApiError(HTTP.BAD_REQUEST, "Username already registered");
            const id = DB.nextId.user++;
            const u = {
                id, username: body.username, password: body.password,
                full_name: body.full_name || "", is_active: true, created_at: fmtDT(new Date()),
            };
            DB.users.push(u);
            audit(actorOf(init), "user.create", "user", u.username);
            return response(HTTP.CREATED, userOut(u));
        }
        if (parts.length === 2 && parts[0] === "users" && method === "PUT") {
            requireAdmin(init);
            const u = DB.users.find((x) => x.id === Number(parts[1]));
            if (!u) throw new ApiError(HTTP.NOT_FOUND, "User not found");
            if (body.password) {
                if (body.password.length < 8) throw new ApiError(HTTP.BAD_REQUEST, `password must be at least 8 characters`);
                u.password = body.password;
            }
            const changed = [];
            if (body.password) changed.push("password");
            if (body.full_name !== undefined && body.full_name !== u.full_name) changed.push("full_name");
            if (body.is_active !== undefined && body.is_active !== u.is_active) changed.push("is_active");
            if (body.full_name !== undefined) u.full_name = body.full_name;
            if (body.is_active !== undefined) u.is_active = body.is_active;
            if (changed.length) audit(actorOf(init), "user.update", "user", u.username, "changed: " + changed.join(", "));
            return userOut(u);
        }
        if (parts.length === 2 && parts[0] === "users" && method === "DELETE") {
            requireAdmin(init);
            const id = Number(parts[1]);
            const user = DB.users.find((u) => u.id === id);
            if (!user) throw new ApiError(HTTP.NOT_FOUND, "User not found");
            DB.users = DB.users.filter((u) => u.id !== id);
            audit(actorOf(init), "user.delete", "user", user.username);
            return noContent();
        }

        if (path === "/reports/summary" && method === "GET") {
            requireAdmin(init);
            return reportsSummary();
        }
        if (path === "/reports/export.csv" && method === "GET") {
            requireAdmin(init);
            return reportCsvResponse();
        }
        if (path === "/reports/top-products" && method === "GET") {
            requireAdmin(init);
            return topProducts(Number(query.get("limit")) || 10);
        }
        if (path === "/reports/customer-insights" && method === "GET") {
            requireAdmin(init);
            return customerInsights(Math.max(1, Math.min(Number(query.get("limit")) || 5, 20)));
        }
        if (path === "/reports/sales-by-day" && method === "GET") {
            requireAdmin(init);
            return salesByDay(Number(query.get("days")) || 14);
        }
        if (path === "/reports/margins" && method === "GET") {
            requireAdmin(init);
            const period = query.get("period") || "all";
            if (!["today", "week", "month", "all"].includes(period)) {
                throw new ApiError(HTTP.UNPROCESSABLE, "Invalid period");
            }
            const [start, end] = periodBounds(period);
            return { period, ...marginsFor(start, end) };
        }

        if (path === "/audit" && method === "GET") {
            requireAdmin(init);
            const action = query.get("action") || "";
            const limit = Math.max(1, Math.min(Number(query.get("limit")) || 200, 1000));
            return DB.audit.filter((e) => e.action.startsWith(action)).slice().reverse().slice(0, limit);
        }

        if (path === "/system/status" && method === "GET") {
            requireAdmin(init);
            const last = DB.audit[DB.audit.length - 1];
            return {
                version: "demo", commit: "", python: "n/a (browser demo)",
                server_time: fmtDT(new Date()), started_at: DEMO_STARTED,
                uptime_seconds: Math.floor((Date.now() - new Date(DEMO_STARTED).getTime()) / 1000),
                database: { engine: "in-browser demo", size_bytes: null },
                counts: {
                    products: DB.products.length,
                    active_products: DB.products.filter((p) => p.is_active).length,
                    low_stock_products: lowStockProducts().length,
                    customers: DB.customers.length,
                    orders: DB.orders.length,
                    pending_orders: DB.orders.filter((o) => o.status === "pending").length,
                    users: DB.users.length,
                },
                last_activity: last ? { at: last.created_at, actor: last.actor, action: last.action } : null,
                backups: demoBackups(),
            };
        }
        if (path === "/system/backups" && method === "GET") {
            requireAdmin(init);
            return demoBackups();
        }
        if (path === "/system/backups" && method === "POST") {
            requireAdmin(init);
            throw new ApiError(HTTP.BAD_REQUEST, "Backups are not available in the browser demo");
        }

        throw new ApiError(HTTP.NOT_FOUND, "Not Found");
    }

    const DEMO_STARTED = fmtDT(new Date());

    function demoBackups() {
        return {
            supported: false, interval_hours: Number(DB.settings.backup_interval_hours) || 0,
            keep: Number(DB.settings.backup_keep) || 7, count: 0, total_bytes: 0,
            last_backup_at: null, items: [],
        };
    }

    function assertSpecialWindow(p) {
        if (p.special_starts_on && p.special_ends_on && p.special_ends_on < p.special_starts_on) {
            throw new ApiError(HTTP.UNPROCESSABLE, "special_ends_on must not be before special_starts_on");
        }
    }

    async function readAsDataURL(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    function jsonResponse(data, status) {
        return new Response(JSON.stringify(data), {
            status,
            headers: { "Content-Type": "application/json" },
        });
    }

    const origFetch = window.fetch;
    window.fetch = function (input, init) {
        const url = typeof input === "string" ? input : (input && input.url);
        if (!url || !url.startsWith("/api/")) {
            return origFetch(input, init);
        }
        const path = url.slice(4).split("?")[0];
        const query = new URLSearchParams(url.split("?")[1] || "");
        const method = ((init && init.method) || "GET").toUpperCase();
        const delay = 40 + Math.random() * 60;
        return handle(path, query, method, init)
            .then((result) => {
                if (result instanceof Response) {
                    return new Promise((resolve) => setTimeout(() => resolve(result), delay));
                }
                const status = typeof result.__status === "number" ? result.__status : HTTP.OK;
                const data = typeof result.__status === "number" ? result.__data : result;
                return new Promise((resolve) => setTimeout(() => {
                    if (status === HTTP.NO_CONTENT) resolve(new Response(null, { status }));
                    else resolve(jsonResponse(data, status));
                }, delay));
            })
            .catch((err) => {
                const status = err instanceof ApiError ? err.status : 500;
                const detail = err instanceof ApiError ? err.detail : "Internal demo error";
                return new Promise((resolve) => setTimeout(() => resolve(jsonResponse({ detail }, status)), delay));
            });
    };

    const banner = document.createElement("div");
    banner.className = "demo-banner";
    banner.innerHTML =
        "<strong>&#128640; GitHub Pages demo</strong> " +
        "data lives in your browser and resets on refresh &middot; " +
        "admin login <code>admin</code> / <code>demo-password123</code> &middot; " +
        '<a href="#/">Kiosk</a> &middot; <a href="#admin">Admin</a> &middot; ' +
        '<a href="javascript:location.reload()">Reset demo</a>';
    const bannerStyle = document.createElement("style");
    bannerStyle.textContent =
        ".demo-banner{position:fixed;top:0;left:0;right:0;z-index:10000;display:flex;" +
        "flex-wrap:wrap;gap:0.5rem;align-items:center;justify-content:center;" +
        "padding:0.4rem 1rem;background:#1e293b;color:#e2e8f0;font-size:0.8rem;" +
        "box-shadow:0 2px 10px rgba(0,0,0,0.3);}" +
        ".demo-banner a{color:#93c5fd;font-weight:600;text-decoration:none;}" +
        ".demo-banner code{background:#0f172a;padding:0 0.3rem;border-radius:4px;}" +
        "body.demo-mode{padding-top:2.2rem;}";
    banner.id = "demo-banner";
    (document.head || document.documentElement).appendChild(bannerStyle);

    function addBanner() {
        if (!document.getElementById("demo-banner")) {
            document.body.appendChild(banner);
        }
        document.body.classList.add("demo-mode");
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", addBanner);
    } else {
        addBanner();
    }

    window.Demo = { active: true };
})();