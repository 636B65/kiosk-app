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
        },
        tokens: {},
        nextId: { product: 100, customer: 100, order: 100, item: 100, user: 100 },
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

    function addOrder(order) {
        order.id = DB.nextId.order++;
        order.created_at = order.created_at || fmtDT(new Date());
        order.items.forEach((it) => {
            it.id = DB.nextId.item++;
            it.order_id = order.id;
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

    function effectivePrice(p) {
        return p.is_weekly_special && p.special_price != null ? p.special_price : p.price;
    }

    function dueTime() {
        const raw = DB.settings.payment_due_date;
        if (!raw) return null;
        return raw + "T23:59:59";
    }

    function categoryOf(product) {
        return DB.categories.find((c) => c.id === product.category_id) || null;
    }

    function productOut(p) {
        return {
            id: p.id, name: p.name, description: p.description, price: p.price,
            special_price: p.special_price, is_weekly_special: p.is_weekly_special,
            stock: p.stock, is_active: p.is_active, category_id: p.category_id,
            category: categoryOf(p),
            image_url: p.image_path || null,
        };
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
            total_spent: Math.round(total * 100) / 100,
            total_paid: Math.round(paid * 100) / 100,
            balance: Math.round(pending * 100) / 100,
            avg_order: count ? Math.round((total / count) * 100) / 100 : 0,
            items_bought: itemsBought,
            first_order_at: orders[0] ? orders[0].created_at : null,
            last_order_at: orders.length ? orders[orders.length - 1].created_at : null,
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
        const name = (username || "").trim().toLowerCase();
        return DB.customers.find((c) => c.username === name);
    }

    function getOrCreateCustomer(username) {
        const name = (username || "").trim().toLowerCase();
        if (!name) return null;
        let c = findCustomer(name);
        if (!c) {
            c = { id: DB.nextId.customer++, username: name, created_at: fmtDT(new Date()) };
            DB.customers.push(c);
        }
        return c;
    }

    function pendingOrdersFor(customerId) {
        return DB.orders.filter((o) => o.customer_id === customerId && o.status === "pending");
    }

    function revenueForPeriod(start, end) {
        let sum = 0, count = 0;
        for (const o of DB.orders) {
            if (o.status !== "paid") continue;
            if (start && o.created_at < start) continue;
            if (end && o.created_at >= end) continue;
            sum += o.total;
            count += 1;
        }
        return { order_count: count, revenue: Math.round(sum * 100) / 100 };
    }

    function reportsSummary() {
        const now = new Date();
        const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const todayStart = fmtDT(t0);
        const yStart = fmtDT(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
        const lowStock = DB.products
            .filter((p) => p.is_active && p.stock <= 5)
            .sort((a, b) => a.stock - b.stock)
            .map((p) => productOut(p));
        return {
            today: revenueForPeriod(todayStart),
            yesterday: revenueForPeriod(yStart, todayStart),
            week: revenueForPeriod(fmtDT(daysAgo(7))),
            month: revenueForPeriod(fmtDT(daysAgo(30))),
            all_time: revenueForPeriod(),
            outstanding: Math.round(DB.orders.filter((o) => o.status === "pending").reduce((s, o) => s + o.total, 0) * 100) / 100,
            pending_orders: DB.orders.filter((o) => o.status === "pending").length,
            next_due_date: dueTime(),
            low_stock_products: lowStock,
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
            if (o.status !== "paid" || o.created_at < start) continue;
            const day = (o.created_at || "").slice(0, 10);
            const row = byDay[day] || { orders: 0, revenue: 0 };
            row.orders += 1;
            row.revenue += o.total;
            byDay[day] = row;
        }
        return Object.keys(byDay).sort().map((day) => ({
            day, orders: byDay[day].orders, revenue: Math.round(byDay[day].revenue * 100) / 100,
        }));
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
        NOT_FOUND: 404,
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
                .map((p) => productOut(p));
        }
        if (path === "/products" && method === "POST") {
            requireAdmin(init);
            const id = DB.nextId.product++;
            const p = {
                id, name: body.name, description: body.description || "",
                price: body.price || 0, special_price: body.special_price ?? null,
                is_weekly_special: !!body.is_weekly_special,
                stock: body.stock || 0, is_active: body.is_active !== false,
                category_id: body.category_id ?? null, image_path: null,
                created_at: fmtDT(new Date()),
            };
            DB.products.push(p);
            return response(HTTP.CREATED, productOut(p));
        }
        if (parts.length >= 2 && parts[0] === "products" && method === "PUT") {
            requireAdmin(init);
            const p = DB.products.find((x) => x.id === Number(parts[1]));
            if (!p) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            if (body.name !== undefined) p.name = body.name;
            if (body.description !== undefined) p.description = body.description;
            if (body.price !== undefined) p.price = body.price;
            if (body.special_price !== undefined) p.special_price = body.special_price;
            if (body.is_weekly_special !== undefined) p.is_weekly_special = body.is_weekly_special;
            if (body.stock !== undefined) p.stock = body.stock;
            if (body.is_active !== undefined) p.is_active = body.is_active;
            if (body.category_id !== undefined) p.category_id = body.category_id;
            return productOut(p);
        }
        if (parts.length >= 2 && parts[0] === "products" && method === "DELETE") {
            requireAdmin(init);
            const id = Number(parts[1]);
            if (!DB.products.some((p) => p.id === id)) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            DB.products = DB.products.filter((p) => p.id !== id);
            return noContent();
        }
        if (parts.length === 3 && parts[0] === "products" && parts[2] === "image" && method === "POST") {
            requireAdmin(init);
            const p = DB.products.find((x) => x.id === Number(parts[1]));
            if (!p) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            const file = body.get("file");
            if (!file) throw new ApiError(HTTP.BAD_REQUEST, "Empty file");
            p.image_path = await readAsDataURL(file);
            return productOut(p);
        }
        if (parts.length === 3 && parts[0] === "products" && parts[2] === "image" && method === "DELETE") {
            requireAdmin(init);
            const p = DB.products.find((x) => x.id === Number(parts[1]));
            if (!p) throw new ApiError(HTTP.NOT_FOUND, "Product not found");
            p.image_path = null;
            return productOut(p);
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
            const customer = getOrCreateCustomer(body.customer_username);
            if (!customer) throw new ApiError(HTTP.BAD_REQUEST, "A username is required");
            if (!body.items || body.items.length === 0) throw new ApiError(HTTP.BAD_REQUEST, "Order must contain items");
            if (pendingOrdersFor(customer.id).length > 0) {
                throw new ApiError(HTTP.FORBIDDEN, "Your previous order is still unpaid. Ask the staff to mark it as paid before you can buy again.");
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
            order.status = status;
            order.completed_at = status !== "pending" ? fmtDT(new Date()) : order.completed_at;
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
                        id: c.id, username: c.username, created_at: c.created_at,
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
            const orders = DB.orders
                .filter((o) => o.customer_id === customer.id)
                .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
            const stats = statsFor(customer.id);
            return {
                customer: { id: customer.id, username: customer.username, created_at: customer.created_at },
                balance: stats.balance, total_paid: stats.total_paid,
                orders: orders.map((o) => ({ ...orderOut(o), items: orderItems(o) })),
                stats,
            };
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
            DB.settings[parts[1]] = body.value;
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
            if (body.full_name !== undefined) u.full_name = body.full_name;
            if (body.is_active !== undefined) u.is_active = body.is_active;
            return userOut(u);
        }
        if (parts.length === 2 && parts[0] === "users" && method === "DELETE") {
            requireAdmin(init);
            const id = Number(parts[1]);
            if (!DB.users.some((u) => u.id === id)) throw new ApiError(HTTP.NOT_FOUND, "User not found");
            DB.users = DB.users.filter((u) => u.id !== id);
            return noContent();
        }

        if (path === "/reports/summary" && method === "GET") {
            requireAdmin(init);
            return reportsSummary();
        }
        if (path === "/reports/top-products" && method === "GET") {
            requireAdmin(init);
            return topProducts(Number(query.get("limit")) || 10);
        }
        if (path === "/reports/sales-by-day" && method === "GET") {
            requireAdmin(init);
            return salesByDay(Number(query.get("days")) || 14);
        }

        throw new ApiError(HTTP.NOT_FOUND, "Not Found");
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