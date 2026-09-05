const Kiosk = {
    init() {
        document.addEventListener("click", (e) => {
            const addBtn = e.target.closest(".add-btn");
            if (addBtn) this.addToCart(parseInt(addBtn.dataset.id));
            const qty = e.target.closest(".qty-btn");
            if (qty) this.changeQty(parseInt(qty.dataset.id), parseInt(qty.dataset.delta));
            const cat = e.target.closest(".category-pill");
            if (cat) this.setCategory(parseInt(cat.dataset.id));
            const cartBtn = e.target.closest(".cart-btn");
            if (cartBtn) this.toggleCart();
            const lookupBtn = e.target.closest("#lookup-btn");
            if (lookupBtn) this.openLookup();
            const closeCart = e.target.closest(".cart-close");
            if (closeCart) this.toggleCart();
            const overlay = e.target.closest(".cart-overlay");
            if (e.target === overlay) this.toggleCart();
            const removeItem = e.target.closest(".remove-item");
            if (removeItem) this.removeFromCart(parseInt(removeItem.dataset.id));
            const checkout = e.target.closest(".checkout-btn");
            if (checkout) this.checkout();
            const recalc = e.target.closest(".recalc-cart");
            if (recalc) this.renderCart();
        });
    },

    renderHeader() {
        const name = Store.settings.store_name || "Kiosk Store";
        return `
            <header class="kiosk-header">
                <h1>🛍️ ${esc(name)}</h1>
                <div style="display:flex; gap:0.75rem;">
                    <button class="cart-btn" id="lookup-btn">🔍 User lookup</button>
                    <button class="cart-btn">🛒 Cart <span class="cart-badge" id="cart-count">${Store.cartCount()}</span></button>
                </div>
            </header>
        `;
    },

    renderCategories() {
        const cats = [
            { id: null, name: "All" },
            ...Store.categories,
        ];
        return `
            <div class="categories-bar">
                ${cats.map((c) => `
                    <button class="category-pill ${Store.activeCategory === c.id ? "active" : ""}"
                            data-id="${c.id ?? ""}">${esc(c.name)}</button>
                `).join("")}
            </div>
        `;
    },

    renderProductGrid() {
        const filtered = Store.products.filter((p) => {
            if (Store.activeCategory && p.category_id !== Store.activeCategory) return false;
            const search = (document.getElementById("search-input")?.value || "").toLowerCase();
            if (search && !p.name.toLowerCase().includes(search)) return false;
            return true;
        });
        const products = sortShopProducts(filtered);
        const container = document.getElementById("product-grid-container");
        if (!container) return;
        container.innerHTML = `
            <div class="product-grid">
                ${products.length === 0
                    ? '<p style="grid-column: 1/-1; text-align:center; color: var(--muted); padding: 2rem;">No products found</p>'
                    : products.map(this.productCard.bind(this)).join("")}
            </div>
        `;
        this.updateCartBadge();
    },

    productCard(p) {
        const inCart = Store.cart.find((i) => i.product_id === p.id);
        const qty = inCart ? inCart.quantity : 0;
        const soldOut = p.stock <= 0;
        const lowStock = p.stock > 0 && p.stock <= 5;
        const isSpecial = p.is_weekly_special && p.special_price != null;
        return `
            <div class="product-card">
                ${isSpecial ? '<div class="weekly-badge">⚡ Weekly special</div>' : ""}
                <div class="product-image">${renderProductImage(p)}</div>
                <div class="product-name">${esc(p.name)}</div>
                <div class="product-desc">${esc(p.description)}</div>
                <div class="product-price">
                    ${isSpecial
                        ? `<span class="price-old">${fmt(p.price)}</span> <span class="price-special">${fmt(p.special_price)}</span>`
                        : fmt(p.price)}
                </div>
                <div class="stock-label ${lowStock ? "stock-low" : ""} ${soldOut ? "stock-out" : ""}">
                    ${soldOut ? "Out of stock" : `${p.stock} in stock`}
                </div>
                <div class="product-actions">
                    ${soldOut
                        ? `<button class="add-btn" disabled>Sold out</button>`
                        : qty > 0
                            ? `
                        <div class="qty-control">
                            <button class="qty-btn" data-id="${p.id}" data-delta="-1">−</button>
                            <span>${qty}</span>
                            <button class="qty-btn" data-id="${p.id}" data-delta="1">+</button>
                        </div>`
                            : `<button class="add-btn" data-id="${p.id}">Add to cart</button>`}
                </div>
            </div>
        `;
    },

    setCategory(id) {
        Store.activeCategory = id;
        this.renderBody();
    },

    addToCart(productId) {
        const product = Store.products.find((p) => p.id === productId);
        if (!product) return;
        const item = Store.cart.find((i) => i.product_id === productId);
        if (item) {
            if (item.quantity >= product.stock) {
                Toast.error("No more stock available");
                return;
            }
            item.quantity += 1;
        } else {
            Store.cart.push({ product_id: product.id, name: product.name, price: effectivePrice(product), quantity: 1 });
        }
        Store.saveCart();
        this.refreshUI();
    },

    changeQty(productId, delta) {
        const item = Store.cart.find((i) => i.product_id === productId);
        if (!item) return;
        const product = Store.products.find((p) => p.id === productId);
        item.quantity += delta;
        if (item.quantity <= 0 || (product && delta > 0 && item.quantity > product.stock)) {
            if (product && delta > 0 && item.quantity > product.stock) {
                Toast.error("No more stock available");
                item.quantity = product.stock;
            } else {
                Store.cart = Store.cart.filter((i) => i.product_id !== productId);
                Toast.show("Removed from cart");
            }
        }
        Store.saveCart();
        this.refreshUI();
    },

    removeFromCart(productId) {
        Store.cart = Store.cart.filter((i) => i.product_id !== productId);
        Store.saveCart();
        this.refreshUI();
    },

    refreshUI() {
        this.renderProductGrid();
        this.updateCartBadge();
        if (document.getElementById("cart-overlay")) {
            this.renderCart();
        }
    },

    updateCartBadge() {
        const badge = document.getElementById("cart-count");
        if (badge) badge.textContent = Store.cartCount();
    },

    toggleCart() {
        const overlay = document.getElementById("cart-overlay");
        if (overlay) {
            overlay.remove();
            return;
        }
        this.renderCart();
    },

    renderCart() {
        const old = document.getElementById("cart-overlay");
        if (old) old.remove();
        const total = Store.cartTotal();
        const overlay = document.createElement("div");
        overlay.className = "cart-overlay";
        overlay.id = "cart-overlay";
        overlay.innerHTML = `
            <div class="cart-panel">
                <div class="cart-header">
                    Your Cart
                    <button class="close-btn cart-close">✕</button>
                </div>
                <div class="cart-items">
                    ${Store.cart.length === 0
                        ? '<div class="cart-empty">Your cart is empty</div>'
                        : Store.cart.map((i) => `
                            <div class="cart-item">
                                <div class="cart-item-info">
                                    <div class="cart-item-name">${esc(i.name)}</div>
                                    <div class="cart-item-price">${fmt(i.price)} × ${i.quantity}</div>
                                </div>
                                <div style="display:flex; align-items:center; gap:0.5rem;">
                                    <button class="btn btn-secondary qty-btn" data-id="${i.product_id}" data-delta="-1">−</button>
                                    <button class="btn btn-secondary qty-btn" data-id="${i.product_id}" data-delta="1">+</button>
                                    <button class="btn btn-danger remove-item" data-id="${i.product_id}">✕</button>
                                </div>
                            </div>
                        `).join("")}
                </div>
                <div class="cart-footer">
                    <div class="cart-total-row">
                        <span>Total</span><span>${fmt(total)}</span>
                    </div>
                    <button class="checkout-btn" ${Store.cart.length === 0 ? "disabled" : ""}>
                        Buy
                    </button>
                    <p style="font-size:0.8rem; color:var(--muted); text-align:center; margin:0;">
                        The amount is added to your balance and paid at the counter on a later visit.
                    </p>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    },

    checkout() {
        Modal.open(`
            <h2>Buy</h2>
            <p style="color:var(--muted);">Enter your username to add this purchase to your balance.</p>
            <form id="checkout-form">
                <div class="form-group">
                    <label>Username</label>
                    <input id="co-username" autocomplete="off" required>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Buy</button>
                </div>
            </form>
        `);
        document.getElementById("checkout-form").addEventListener("submit", (e) => {
            e.preventDefault();
            this.placeOrder(document.getElementById("co-username").value);
        });
    },

    async placeOrder(username) {
        const userName = username.trim();
        if (!userName) {
            Toast.error("Enter your username");
            return;
        }
        try {
            const items = Store.cart.map((i) => ({ product_id: i.product_id, quantity: i.quantity }));
            const order = await API.post("/orders", { customer_username: userName, items, notes: "" });
            Store.cart = [];
            Store.saveCart();
            document.getElementById("cart-overlay")?.remove();
            await Store.loadPublicData();
            this.renderBody();
            let history = null;
            try {
                history = await API.get(`/customers/${encodeURIComponent(userName)}`);
            } catch {}
            this.renderConfirmation(order, history);
        } catch (err) {
            Toast.error(err.message);
            await Store.loadPublicData();
            this.renderBody();
        }
    },

    renderConfirmation(order, history) {
        confetti();
        Modal.open(`
            <h2>✅ Order Complete</h2>
            <p style="color:var(--muted);">Order #${order.id} for ${esc(order.customer_username)}</p>
            <p><strong>Order total:</strong> ${fmt(order.total)}</p>
            ${history ? `
                <p style="color:var(--warning); font-weight:700;">Balance to pay: ${fmt(history.balance)}</p>
            ` : ""}
            <p style="color:var(--muted);">${esc(Store.settings.receipt_footer || "Thank you for your purchase!")}</p>
            <div class="form-actions">
                <button class="btn btn-primary" onclick="Modal.close(); Kiosk.newOrder()">New Order</button>
            </div>
        `);
    },

    openLookup() {
        Modal.open(`
            <h2>Payment lookup</h2>
            <p style="color:var(--muted);">Enter your username to see your balance and history.</p>
            <form id="lookup-form">
                <div class="form-group">
                    <label>Username</label>
                    <input id="lk-username" autocomplete="off" required>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Look up</button>
                </div>
            </form>
        `);
        document.getElementById("lookup-form").addEventListener("submit", (e) => {
            e.preventDefault();
            this.lookupUser(document.getElementById("lk-username").value);
        });
    },

    async lookupUser(username) {
        const userName = username.trim();
        if (!userName) return;
        try {
            const data = await API.get(`/customers/${encodeURIComponent(userName)}`);
            Kiosk.showLookup(data);
        } catch (err) {
            Toast.error(err.message);
        }
    },

    showLookup(data) {
        const orderBlock = (o) => `
            <div class="history-order">
                <div class="history-order-head">
                    <span>Order #${o.id} — ${new Date(o.created_at).toLocaleString()}</span>
                    <span class="status-badge status-${o.status}">${o.status}</span>
                </div>
                <ul>
                    ${o.items.map((i) => `
                        <li>
                            <span>${esc(i.product_name)} × ${i.quantity}</span>
                            <span>${fmt(i.unit_price * i.quantity)}</span>
                        </li>`).join("")}
                </ul>
                <div class="history-order-total">Total: ${fmt(o.total)}</div>
            </div>
        `;
        const unpaidCount = data.orders.filter((o) => o.status === "pending").length;
        const months = groupOrdersByMonth(data.orders);
        Modal.fill(`
            <h2>👤 ${esc(data.customer.username)}</h2>
            <div class="balance-big">${fmt(data.balance)}</div>
            <p style="text-align:center; color:var(--muted); margin-bottom:1rem;">
                ${data.balance > 0
                    ? `${unpaidCount} unpaid order(s) — pay this at the counter`
                    : "No outstanding balance 🎉"}
            </p>
            <div style="display:flex; justify-content:space-between; padding:0.5rem 0; border-top:1px solid var(--border); border-bottom:1px solid var(--border); margin-bottom:1rem;">
                <span style="color:var(--muted);">Total paid</span>
                <span style="font-weight:700;">${fmt(data.total_paid)}</span>
            </div>
            ${renderCustomerStats(data.stats)}
            <h3 style="margin:1.25rem 0 0.5rem;">Order history</h3>
            ${data.orders.length === 0
                ? '<p style="color:var(--muted);">No orders yet.</p>'
                : months.map((m) => `
                    <div class="history-month">
                        <div class="history-month-head">
                            <span>${esc(m.label)}</span>
                            <span>${m.orders.length} order(s) — ${fmt(m.orders.reduce((s, o) => s + o.total, 0))}</span>
                        </div>
                        ${m.orders.map(orderBlock).join("")}
                    </div>
                `).join("")}
            <div class="form-actions">
                <button class="btn btn-secondary" onclick="Modal.close()">Close</button>
                <button class="btn btn-primary" onclick="Kiosk.openLookup()">Another user</button>
            </div>
        `);
    },

    newOrder() {
        Store.activeCategory = null;
        this.renderBody();
    },

    renderBody() {
        const app = document.getElementById("app");
        app.innerHTML = `
            ${this.renderHeader()}
            ${this.renderCategories()}
            <div class="search-bar">
                <input id="search-input" placeholder="Search products..."
                       autocomplete="off" spellcheck="false"
                       oninput="Kiosk.renderProductGrid()">
            </div>
            <div id="product-grid-container"></div>
        `;
        this.renderProductGrid();
    },

    async render() {
        try {
            await Store.loadPublicData();
        } catch (err) {
            Toast.error("Failed to load data: " + err.message);
        }
        this.renderBody();
    },
};