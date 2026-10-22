const Admin = {
    session: null,
    view: "dashboard",

    init() {
        document.addEventListener("click", (e) => {
            const nav = e.target.closest("[data-view]");
            if (nav) {
                e.preventDefault();
                location.hash = "#admin/" + nav.dataset.view;
            }
            const editProduct = e.target.closest(".edit-product");
            if (editProduct) this.openProductModal(parseInt(editProduct.dataset.id));
            const deleteProduct = e.target.closest(".delete-product");
            if (deleteProduct) this.confirmDeleteProduct(parseInt(deleteProduct.dataset.id));
            const editCategory = e.target.closest(".edit-category");
            if (editCategory) this.openCategoryModal(parseInt(editCategory.dataset.id));
            const deleteCategory = e.target.closest(".delete-category");
            if (deleteCategory) this.confirmDeleteCategory(parseInt(deleteCategory.dataset.id));
            const changeStatus = e.target.closest(".change-status");
            if (changeStatus) this.changeOrderStatus(parseInt(changeStatus.dataset.id), changeStatus.dataset.status);
            const viewOrder = e.target.closest(".view-order");
            if (viewOrder) this.viewOrder(parseInt(viewOrder.dataset.id));
            const editUser = e.target.closest(".edit-user");
            if (editUser) this.openUserModal(parseInt(editUser.dataset.id));
            const deleteUser = e.target.closest(".delete-user");
            if (deleteUser) this.confirmDeleteUser(parseInt(deleteUser.dataset.id));
            const viewCustomer = e.target.closest(".view-customer");
            if (viewCustomer) this.viewCustomer(decodeURIComponent(viewCustomer.dataset.username));
            const resetPayment = e.target.closest(".reset-payment");
            if (resetPayment) this.confirmResetPayment(decodeURIComponent(resetPayment.dataset.username));
            const logout = e.target.closest(".logout-btn");
            if (logout) this.logout();
        });
        document.addEventListener("submit", (e) => {
            const loginForm = e.target.closest("#login-form");
            if (loginForm) {
                e.preventDefault();
                this.doLogin();
            }
        });
    },

    getToken() {
        return localStorage.getItem("kiosk_token");
    },

    isLoggedIn() {
        return !!this.getToken();
    },

    readSession() {
        try {
            this.session = JSON.parse(localStorage.getItem("kiosk_user") || "null");
        } catch {
            this.session = null;
        }
    },

    async doLogin() {
        const username = document.getElementById("login-username").value.trim();
        const password = document.getElementById("login-password").value;
        if (!username || !password) {
            Toast.error("Enter username and password");
            return;
        }
        const btn = document.querySelector("#login-form button[type=submit]");
        btn.disabled = true;
        btn.textContent = "Signing in...";
        try {
            const res = await API.post("/auth/login", { username, password });
            localStorage.setItem("kiosk_token", res.access_token);
            localStorage.setItem("kiosk_user", JSON.stringify(res.user));
            this.view = "dashboard";
            const target = "#admin";
            if (location.hash === target) {
                this.render();
            } else {
                location.hash = target;
            }
        } catch (err) {
            Toast.error(err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = "Sign In";
        }
    },

    logout() {
        localStorage.removeItem("kiosk_token");
        localStorage.removeItem("kiosk_user");
        Toast.show("Signed out");
        location.hash = "#admin/login";
    },

    renderLogin() {
        const app = document.getElementById("app");
        app.innerHTML = `
            <div class="auth-screen">
                <div class="auth-card">
                    <h1>🔐 Admin Sign In</h1>
                    <form id="login-form">
                        <div class="form-group">
                            <label>Username</label>
                            <input id="login-username" autocomplete="username" required>
                        </div>
                        <div class="form-group">
                            <label>Password</label>
                            <input id="login-password" type="password" autocomplete="current-password" required>
                        </div>
                        <button class="btn btn-primary" style="width:100%; margin-top:0.5rem;" type="submit">Sign In</button>
                    </form>
                </div>
            </div>
        `;
    },

    renderSidebar(user) {
        const initial = (user.full_name || user.username).charAt(0).toUpperCase();
        const navItems = [
            ["dashboard", "📊", "Dashboard"],
            ["products", "📦", "Products"],
            ["categories", "🗂️", "Categories"],
            ["orders", "🧾", "Orders"],
            ["customers", "👥", "Customers"],
            ["reports", "📈", "Reports"],
            ["audit", "📜", "Audit log"],
            ["users", "👤", "Users"],
            ["settings", "⚙️", "Settings"],
            ["system", "🩺", "System"],
        ];
        return `
            <aside class="admin-sidebar">
                <div class="brand">🛍️ ${esc(Store.settings.store_name || "Admin")}</div>
                <nav>
                    ${navItems.map(([view, icon, label]) => `
                        <a href="#admin/${view}" data-view="${view}"
                           class="${this.view === view ? "active" : ""}">${icon} ${label}</a>
                    `).join("")}
                </nav>
                <div class="sidebar-footer">
                    <div style="display:flex; align-items:center; gap:0.6rem;">
                        <span class="user-icon">${initial}</span>
                        <div>
                            <div style="font-size:0.9rem;">${esc(user.full_name || user.username)}</div>
                            <div style="font-size:0.75rem; color:#94a3b8;">Administrator</div>
                        </div>
                    </div>
                    <button class="btn btn-secondary logout-btn">Sign out</button>
                </div>
            </aside>
        `;
    },

    // The view container, or null when the admin has already moved on to
    // another view: a slow render must not overwrite the page now shown.
    mainFor(view) {
        return this.view === view ? document.getElementById("admin-main-container") : null;
    },

    async loadView(view) {
        this.view = view;
        switch (view) {
            case "dashboard": return this.renderDashboard();
            case "products": return this.renderProducts();
            case "categories": return this.renderCategories();
            case "orders": return this.renderOrders();
            case "customers": return this.renderCustomers();
            case "reports": return this.renderReports();
            case "users": return this.renderUsers();
            case "settings": return this.renderSettings();
            case "audit": return this.renderAudit();
            case "system": return this.renderSystem();
            default: return this.renderDashboard();
        }
    },

    async renderDashboard() {
        const [summary, topProducts] = await Promise.all([
            API.get("/reports/summary"),
            API.get("/reports/top-products?limit=5"),
        ]);
        const app = this.mainFor("dashboard");
        if (!app) return;
        app.innerHTML = `
            <div class="admin-main">
                <h2>Dashboard</h2>
                <div class="stats-grid">
                    <div class="stat-card"><div class="label">Outstanding Balance</div><div class="value" style="color:var(--warning);">${fmt(summary.outstanding)}</div><div class="sub">${summary.pending_orders} unpaid order(s)</div></div>
                    <div class="stat-card"><div class="label">Today's Paid</div><div class="value">${fmt(summary.today.revenue)}</div><div class="sub">${summary.today.order_count} order(s)</div></div>
                    <div class="stat-card"><div class="label">This Week</div><div class="value">${fmt(summary.week.revenue)}</div></div>
                    <div class="stat-card"><div class="label">This Month</div><div class="value">${fmt(summary.month.revenue)}</div></div>
                    <div class="stat-card"><div class="label">All-time Paid</div><div class="value">${fmt(summary.all_time.revenue)}</div></div>
                    <div class="stat-card"><div class="label">Margin this month</div><div class="value">${fmt(summary.margin_month.margin)}</div><div class="sub">${summary.margin_month.margin_pct != null ? `${summary.margin_month.margin_pct}% of costed sales` : "no costed sales yet"}</div></div>
                </div>
                <div class="panel">
                    <div class="panel-header"><h3>Top Products</h3></div>
                    <table>
                        <thead><tr><th>Product</th><th>Qty Sold</th><th>Revenue</th></tr></thead>
                        <tbody>
                            ${topProducts.length === 0
                                ? '<tr><td colspan="3">No sales yet</td></tr>'
                                : topProducts.map((p) => `
                                    <tr><td>${esc(p.product)}</td><td>${p.quantity}</td><td>${fmt(p.revenue)}</td></tr>
                                `).join("")}
                        </tbody>
                    </table>
                </div>
                <div class="panel" id="restock-needed">
                    <div class="panel-header"><h3>Restock needed${summary.low_stock_products.length ? ` (${summary.low_stock_products.length})` : ""}</h3></div>
                    <table>
                        <thead><tr><th>Product</th><th>Stock</th><th>Alert at</th><th>Price</th><th></th></tr></thead>
                        <tbody>
                            ${summary.low_stock_products.length === 0
                                ? '<tr><td colspan="5">All stock levels are healthy</td></tr>'
                                : summary.low_stock_products.map((p) => `
                                    <tr>
                                        <td>${esc(p.name)}</td>
                                        <td style="color:${p.stock <= 0 ? "var(--danger)" : "var(--warning)"};"><strong>${p.stock}</strong></td>
                                        <td>≤ ${p.low_stock_threshold}</td>
                                        <td>${fmt(effectivePrice(p))}</td>
                                        <td class="table-actions"><button class="btn btn-secondary" data-action="admin-restock" data-id="${p.id}">Restock</button></td>
                                    </tr>
                                `).join("")}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    },

    async renderProducts() {
        await Store.refresh();
        let restocks = [];
        try {
            restocks = await API.get("/restocks?limit=15");
        } catch {}
        const app = this.mainFor("products");
        if (!app) return;
        const products = [...Store.products].sort((a, b) => a.id - b.id);
        const specialBadge = (p) => ({
            active: ' <span class="weekly-badge">⚡ Weekly</span>',
            scheduled: ` <span class="weekly-badge badge-muted" title="Starts ${esc(p.special_starts_on)}">⏳ Scheduled</span>`,
            ended: ' <span class="weekly-badge badge-muted">⌛ Ended</span>',
        })[specialState(p)] || "";
        app.innerHTML = `
            <div class="admin-main">
                <h2>Products</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" data-action="admin-new-product">+ New Product</button>
                </div>
                <div class="panel">
                <table id="products-table">
                    <thead><tr><th>ID</th><th>Name</th><th>Image</th><th>Category</th><th>Price</th><th>Cost</th><th>Stock</th><th>Status</th><th></th></tr></thead>
                    <tbody>
                        ${products.map((p) => `
                            <tr>
                                <td>${p.id}</td>
                                <td>${esc(p.name)}${specialBadge(p)}</td>
                                <td>${p.image_url ? `<img class="thumb" src="${esc(p.image_url)}" alt="">` : "—"}</td>
                                <td>${p.category ? esc(p.category.name) : "—"}</td>
                                <td>${isSpecialActive(p)
                                    ? `<span class="price-old">${fmt(p.price)}</span> <span class="price-special">${fmt(p.special_price)}</span>`
                                    : fmt(p.price)}</td>
                                <td>${p.cost_price != null ? fmt(p.cost_price) : "—"}</td>
                                <td style="${isLowStock(p) ? "color:var(--warning); font-weight:600;" : ""}" title="Alert at ≤ ${p.low_stock_threshold ?? 5}">${p.stock}</td>
                                <td>${p.is_active ? '<span class="status-badge status-completed">Active</span>' : '<span class="status-badge status-cancelled">Inactive</span>'}</td>
                                <td class="table-actions">
                                    <button class="btn btn-secondary" data-action="admin-restock" data-id="${p.id}">Restock</button>
                                    <button class="btn btn-secondary edit-product" data-id="${p.id}">Edit</button>
                                    <button class="btn btn-danger delete-product" data-id="${p.id}">Delete</button>
                                </td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
                </div>
                <div class="panel" id="recent-restocks">
                    <div class="panel-header"><h3>Recent deliveries</h3></div>
                    ${this.restockTable(restocks, true)}
                </div>
            </div>
        `;
    },

    openProductModal(id) {
        const product = id ? Store.products.find((p) => p.id === id) : null;
        const categories = Store.categories;
        const c = product?.category || null;
        Modal.open(`
            <h2>${id ? "Edit Product" : "New Product"}</h2>
            <form id="product-form">
                <div class="form-group">
                    <label>Name</label>
                    <input id="p-name" value="${esc(product?.name || "")}" required>
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="p-desc" rows="2">${esc(product?.description || "")}</textarea>
                </div>
                <div class="form-group">
                    <label for="p-barcodes">Barcodes</label>
                    <textarea id="p-barcodes" rows="3" placeholder="Scan or enter one barcode per line">${esc((product?.barcodes || []).join("\n"))}</textarea>
                    <small style="color:var(--muted);">Scan each barcode into this field or type one per line. Multiple barcodes can identify the same product.</small>
                </div>
                <div class="form-group">
                    <label>Category</label>
                    <select id="p-category">
                        <option value="">— None —</option>
                        ${categories.map((cat) => `<option value="${cat.id}" ${product?.category_id === cat.id ? "selected" : ""}>${esc(cat.name)}</option>`).join("")}
                    </select>
                </div>
                <div class="form-group">
                    <label>Price (${esc(Store.settings.currency || "EUR")})</label>
                    <input id="p-price" type="number" step="0.01" min="0" value="${product?.price ?? ""}" required>
                </div>
                <div class="form-group">
                    <label style="display:flex; align-items:center; gap:0.5rem;">
                        <input type="checkbox" id="p-weekly" ${product?.is_weekly_special ? "checked" : ""}>
                        ⚡ Weekly special (listed at top of the shop)
                    </label>
                </div>
                <div class="form-group special-fields" style="display:${product?.is_weekly_special ? "" : "none"};">
                    <label>Special price (${esc(Store.settings.currency || "EUR")})</label>
                    <input id="p-special-price" type="number" step="0.01" min="0" value="${product?.special_price ?? ""}">
                </div>
                <div class="form-group special-fields" style="display:${product?.is_weekly_special ? "" : "none"};">
                    <label>Special runs (optional, inclusive dates)</label>
                    <div style="display:flex; gap:0.5rem; align-items:center;">
                        <input id="p-special-start" type="date" value="${esc(product?.special_starts_on || "")}" aria-label="Special starts on">
                        <span>to</span>
                        <input id="p-special-end" type="date" value="${esc(product?.special_ends_on || "")}" aria-label="Special ends on">
                    </div>
                    <small style="color:var(--muted);">Leave empty to run until you switch it off. The special turns on and off by itself on these dates (UTC).</small>
                </div>
                <div class="form-group">
                    <label>Product Image</label>
                    <div id="p-image-preview" class="image-preview">
                        ${product?.image_url
                            ? `<img src="${esc(product.image_url)}" alt="">`
                            : '<span class="image-preview-empty">No image</span>'}
                    </div>
                    <input id="p-image-file" type="file" accept="image/png,image/jpeg,image/webp,image/gif">
                    ${product?.image_url ? `
                        <label style="display:flex; align-items:center; gap:0.5rem; margin-top:0.5rem;">
                            <input type="checkbox" id="p-image-remove">
                            Remove current image
                        </label>
                    ` : ""}
                </div>
                <div class="form-group">
                    <label>Purchase price per unit (${esc(Store.settings.currency || "EUR")}, optional)</label>
                    <input id="p-cost" type="number" step="0.01" min="0" value="${product?.cost_price ?? ""}">
                    <small style="color:var(--muted);">Used for margins. Staff only, never shown at the kiosk. Restocking with a price updates it.</small>
                </div>
                <div class="form-group">
                    <label>Stock</label>
                    <input id="p-stock" type="number" step="1" min="0" value="${product?.stock ?? ""}" required>
                </div>
                <div class="form-group">
                    <label>Low-stock alert at (units)</label>
                    <input id="p-threshold" type="number" step="1" min="0" value="${product?.low_stock_threshold ?? 5}" required>
                </div>
                <div class="form-group">
                    <label style="display:flex; align-items:center; gap:0.5rem;">
                        <input type="checkbox" id="p-active" ${product === null || product.is_active ? "checked" : ""}>
                        Active (visible to customers)
                    </label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" data-action="modal-close">Cancel</button>
                    <button type="submit" class="btn btn-primary">Save</button>
                </div>
            </form>
        `);
        document.getElementById("p-weekly").addEventListener("change", (e) => {
            document.querySelectorAll("#product-form .special-fields").forEach((group) => {
                group.style.display = e.target.checked ? "" : "none";
            });
            if (!e.target.checked) {
                for (const fieldId of ["p-special-price", "p-special-start", "p-special-end"]) {
                    document.getElementById(fieldId).value = "";
                }
            }
        });
        document.getElementById("product-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            const isWeekly = document.getElementById("p-weekly").checked;
            const specialPriceInput = document.getElementById("p-special-price").value;
            const costInput = document.getElementById("p-cost").value;
            const payload = {
                name: document.getElementById("p-name").value.trim(),
                description: document.getElementById("p-desc").value,
                barcodes: document.getElementById("p-barcodes").value
                    .split(/\r?\n/)
                    .map((barcode) => barcode.trim())
                    .filter(Boolean),
                category_id: document.getElementById("p-category").value ? parseInt(document.getElementById("p-category").value) : null,
                price: parseFloat(document.getElementById("p-price").value) || 0,
                stock: parseInt(document.getElementById("p-stock").value) || 0,
                is_active: document.getElementById("p-active").checked,
                is_weekly_special: isWeekly,
                special_price: isWeekly && specialPriceInput !== "" ? parseFloat(specialPriceInput) : null,
                special_starts_on: (isWeekly && document.getElementById("p-special-start").value) || null,
                special_ends_on: (isWeekly && document.getElementById("p-special-end").value) || null,
                cost_price: costInput !== "" ? parseFloat(costInput) : null,
                low_stock_threshold: Math.max(0, parseInt(document.getElementById("p-threshold").value) || 0),
            };
            try {
                const result = id
                    ? await API.put(`/products/${id}`, payload)
                    : await API.post("/products", payload);
                const productId = id || result.id;
                const fileInput = document.getElementById("p-image-file");
                const removeImage = document.getElementById("p-image-remove");
                if (fileInput && fileInput.files && fileInput.files.length > 0) {
                    const formData = new FormData();
                    formData.append("file", fileInput.files[0]);
                    await API.upload(`/products/${productId}/image`, formData);
                } else if (removeImage && removeImage.checked) {
                    await API.del(`/products/${productId}/image`);
                }
                Toast.success(id ? "Product updated" : "Product created");
                Modal.close();
                this.renderProducts();
            } catch (err) {
                Toast.error(err.message);
            }
        });
    },

    confirmDeleteProduct(id) {
        const product = Store.products.find((p) => p.id === id);
        Modal.open(`
            <h2>Delete Product</h2>
            <p>Delete <strong>${esc(product?.name)}</strong>? This cannot be undone.</p>
            <div class="form-actions">
                <button class="btn btn-secondary" data-action="modal-close">Cancel</button>
                <button class="btn btn-danger" id="confirm-delete">Delete</button>
            </div>
        `);
        document.getElementById("confirm-delete").addEventListener("click", async () => {
            try {
                await API.del(`/products/${id}`);
                Toast.success("Product deleted");
                Modal.close();
                this.renderProducts();
            } catch (err) {
                Toast.error(err.message);
            }
        });
    },

    restockTable(restocks, withProduct) {
        if (!restocks.length) return '<p style="color:var(--muted); padding:0.75rem 1rem;">No deliveries recorded yet.</p>';
        return `
            <table>
                <thead><tr><th>Date</th>${withProduct ? "<th>Product</th>" : ""}<th>Qty</th><th>Cost / unit</th><th>Stock after</th><th>By</th><th>Note</th></tr></thead>
                <tbody>
                    ${restocks.map((r) => `
                        <tr>
                            <td>${new Date(r.created_at).toLocaleString()}</td>
                            ${withProduct ? `<td>${esc(r.product_name)}</td>` : ""}
                            <td>+${r.quantity}</td>
                            <td>${r.unit_cost != null ? fmt(r.unit_cost) : "—"}</td>
                            <td>${r.stock_after}</td>
                            <td>${esc(r.created_by || "—")}</td>
                            <td>${esc(r.note || "")}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        `;
    },

    async openRestockModal(id) {
        let product = Store.products.find((p) => p.id === id);
        try {
            if (!product || product.cost_price === undefined) {
                await Store.refresh();
                product = Store.products.find((p) => p.id === id);
            }
            if (!product) throw new Error("Product not found");
            const history = await API.get(`/products/${id}/restocks?limit=10`);
            Modal.open(`
                <h2>Restock ${esc(product.name)}</h2>
                <p style="color:var(--muted); margin-bottom:1rem;">In stock now: <strong>${product.stock}</strong> · alert at ≤ ${product.low_stock_threshold ?? 5}</p>
                <form id="restock-form">
                    <div class="form-group">
                        <label>Units received</label>
                        <input id="r-quantity" type="number" min="1" step="1" required>
                    </div>
                    <div class="form-group">
                        <label>Purchase price per unit (${esc(Store.settings.currency || "EUR")}, optional)</label>
                        <input id="r-cost" type="number" min="0" step="0.01" value="${product.cost_price ?? ""}">
                    </div>
                    <div class="form-group">
                        <label>Note (optional)</label>
                        <input id="r-note" maxlength="200" placeholder="Supplier, invoice number…">
                    </div>
                    <div class="form-actions">
                        <button type="button" class="btn btn-secondary" data-action="modal-close">Cancel</button>
                        <button type="submit" class="btn btn-primary">Add stock</button>
                    </div>
                </form>
                <h3 style="margin:1.25rem 0 0.5rem;">Previous deliveries</h3>
                ${this.restockTable(history, false)}
            `);
            document.getElementById("r-quantity").focus();
            document.getElementById("restock-form").addEventListener("submit", async (e) => {
                e.preventDefault();
                const cost = document.getElementById("r-cost").value;
                try {
                    const result = await API.post(`/products/${id}/restock`, {
                        quantity: parseInt(document.getElementById("r-quantity").value) || 0,
                        unit_cost: cost !== "" ? parseFloat(cost) : null,
                        note: document.getElementById("r-note").value,
                    });
                    Toast.success(`Added ${result.quantity} × ${result.product_name} (stock now ${result.stock_after})`);
                    Modal.close();
                    this.loadView(this.view);
                } catch (err) {
                    Toast.error(err.message);
                }
            });
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async renderCategories() {
        await Store.refresh();
        const app = this.mainFor("categories");
        if (!app) return;
        const countByCat = {};
        Store.products.forEach((p) => {
            if (p.category_id != null) countByCat[p.category_id] = (countByCat[p.category_id] || 0) + 1;
        });
        const categories = [...Store.categories].sort((a, b) => a.sort_order - b.sort_order);
        app.innerHTML = `
            <div class="admin-main">
                <h2>Categories</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" data-action="admin-new-category">+ New Category</button>
                </div>
                <div class="panel">
                <table>
                    <thead><tr><th>ID</th><th>Name</th><th>Description</th><th>Sort</th><th>Products</th><th></th></tr></thead>
                    <tbody>
                        ${categories.map((c) => `
                            <tr>
                                <td>${c.id}</td>
                                <td>${esc(c.name)}</td>
                                <td>${esc(c.description)}</td>
                                <td>${c.sort_order}</td>
                                <td>${countByCat[c.id] || 0}</td>
                                <td class="table-actions">
                                    <button class="btn btn-secondary edit-category" data-id="${c.id}">Edit</button>
                                    <button class="btn btn-danger delete-category" data-id="${c.id}">Delete</button>
                                </td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
                </div>
            </div>
        `;
    },

    openCategoryModal(id) {
        const category = id ? Store.categories.find((c) => c.id === id) : null;
        Modal.open(`
            <h2>${id ? "Edit Category" : "New Category"}</h2>
            <form id="category-form">
                <div class="form-group">
                    <label>Name</label>
                    <input id="c-name" value="${esc(category?.name || "")}" required>
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <input id="c-desc" value="${esc(category?.description || "")}">
                </div>
                <div class="form-group">
                    <label>Sort Order</label>
                    <input id="c-sort" type="number" value="${category?.sort_order ?? 0}">
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" data-action="modal-close">Cancel</button>
                    <button type="submit" class="btn btn-primary">Save</button>
                </div>
            </form>
        `);
        document.getElementById("category-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            const payload = {
                name: document.getElementById("c-name").value.trim(),
                description: document.getElementById("c-desc").value,
                sort_order: parseInt(document.getElementById("c-sort").value) || 0,
            };
            try {
                if (id) {
                    await API.put(`/categories/${id}`, payload);
                    Toast.success("Category updated");
                } else {
                    await API.post("/categories", payload);
                    Toast.success("Category created");
                }
                Modal.close();
                this.renderCategories();
            } catch (err) {
                Toast.error(err.message);
            }
        });
    },

    confirmDeleteCategory(id) {
        const category = Store.categories.find((c) => c.id === id);
        if (!category) return;
        const productCount = Store.products.filter((p) => p.category_id === id).length;
        Modal.open(`
            <h2>Delete Category</h2>
            <p>Delete <strong>${esc(category.name)}</strong>?${productCount > 0 ? ` ${productCount} product(s) will be uncategorized.` : ""}</p>
            <div class="form-actions">
                <button class="btn btn-secondary" data-action="modal-close">Cancel</button>
                <button class="btn btn-danger" id="confirm-delete">Delete</button>
            </div>
        `);
        document.getElementById("confirm-delete").addEventListener("click", async () => {
            try {
                await API.del(`/categories/${id}`);
                Toast.success("Category deleted");
                Modal.close();
                this.renderCategories();
            } catch (err) {
                Toast.error(err.message);
            }
        });
    },

    async renderOrders() {
        const statusParam = this.orderFilter ? `?status_=${encodeURIComponent(this.orderFilter)}` : "";
        const orders = await API.get("/orders" + statusParam);
        const app = this.mainFor("orders");
        if (!app) return;
        app.innerHTML = `
            <div class="admin-main">
                <h2>Orders</h2>
                <div class="toolbar" id="order-filters">
                    <button class="btn ${this.orderFilter || "btn-primary"}" data-filter="">All</button>
                    <button class="btn btn-secondary" data-filter="pending">Pending</button>
                    <button class="btn btn-secondary" data-filter="paid">Paid</button>
                    <button class="btn btn-secondary" data-filter="cancelled">Cancelled</button>
                </div>
                <div class="panel">
                <table>
                    <thead><tr><th>#</th><th>Date</th><th>User</th><th>Items</th><th>Total</th><th>Due</th><th>Status</th><th></th></tr></thead>
                    <tbody>
                        ${orders.map((o) => {
                            const overdue = o.status === "pending" && o.due_date && new Date(o.due_date) < new Date();
                            return `
                            <tr>
                                <td>${o.id}</td>
                                <td>${new Date(o.created_at).toLocaleString()}</td>
                                <td>${o.customer_username ? esc(o.customer_username) : "—"}</td>
                                <td><button class="btn btn-secondary view-order" data-id="${o.id}">View items</button></td>
                                <td>${fmt(o.total)}</td>
                                <td style="${overdue ? "color:var(--danger); font-weight:700;" : ""}">${o.due_date ? new Date(o.due_date).toLocaleDateString() + (overdue ? " ⚠" : "") : "—"}</td>
                                <td><span class="status-badge status-${o.status}">${o.status}</span></td>
                                <td class="table-actions">
                                    ${o.status === "pending" ? `
                                        <button class="btn btn-success change-status" data-id="${o.id}" data-status="paid">Mark paid</button>
                                        <button class="btn btn-danger change-status" data-id="${o.id}" data-status="cancelled">Cancel</button>
                                    ` : ""}
                                </td>
                            </tr>
                        `}).join("")}
                    </tbody>
                </table>
                </div>
            </div>
        `;
        document.getElementById("order-filters").addEventListener("click", (e) => {
            const btn = e.target.closest("[data-filter]");
            if (!btn) return;
            this.orderFilter = btn.dataset.filter;
            [...btn.parentElement.children].forEach((b) => {
                b.classList.toggle("btn-primary", b === btn);
                b.classList.toggle("btn-secondary", b !== btn);
            });
            this.renderOrders();
        });
        if (this.orderFilter) {
            const list = document.getElementById("order-filters");
            const filterBtn = list.querySelector(`[data-filter="${this.orderFilter}"]`);
            if (filterBtn) {
                [...list.children].forEach((b) => {
                    b.classList.toggle("btn-primary", b === filterBtn);
                    b.classList.toggle("btn-secondary", b !== filterBtn);
                });
            }
        }
    },

    async viewOrder(id) {
        try {
            const items = await API.get(`/orders/${id}/items`);
            Modal.open(`
                <h2>Order #${id}</h2>
                <table>
                    <thead><tr><th>Item</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr></thead>
                    <tbody>
                        ${items.map((i) => `
                            <tr><td>${esc(i.product_name)}</td><td>${i.quantity}</td><td>${fmt(i.unit_price)}</td><td>${fmt(i.unit_price * i.quantity)}</td></tr>
                        `).join("")}
                    </tbody>
                </table>
                <div class="form-actions">
                    <button class="btn btn-secondary" data-action="modal-close">Close</button>
                </div>
            `);
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async changeOrderStatus(id, status) {
        try {
            await API.patch(`/orders/${id}/status?new_status=${encodeURIComponent(status)}`, {});
            Toast.success(`Order #${id} marked ${status}`);
            this.renderOrders();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async renderCustomers() {
        const customers = await API.get("/customers");
        const app = this.mainFor("customers");
        if (!app) return;
        app.innerHTML = `
            <div class="admin-main">
                <h2>Customers</h2>
                <p style="color:var(--muted); margin-bottom:1rem;">
                    Customers are created automatically at the kiosk when they buy for the first time.
                    Reset payment clears a customer's outstanding balance.
                </p>
                <div class="panel">
                <table>
                    <thead><tr><th>User</th><th>Created</th><th>Orders</th><th>Orders/mo</th><th>Busiest day</th><th>Total paid</th><th>Balance to pay</th><th></th></tr></thead>
                    <tbody>
                        ${customers.length === 0
                            ? '<tr><td colspan="8">No customers yet</td></tr>'
                            : customers.map((c) => `
                            <tr>
                                <td><strong>${esc(c.username)}</strong></td>
                                <td>${new Date(c.created_at).toLocaleDateString()}</td>
                                <td>${c.order_count}</td>
                                <td>${c.stats.avg_orders_per_month}</td>
                                <td>${c.stats.busiest_day ? esc(c.stats.busiest_day) : "—"}</td>
                                <td>${fmt(c.total_paid)}</td>
                                <td style="${c.balance > 0 ? "color:var(--warning); font-weight:700;" : "color:var(--success);"}">${fmt(c.balance)}</td>
                                <td class="table-actions">
                                    <button class="btn btn-secondary view-customer" data-username="${encodeURIComponent(c.username)}">History</button>
                                    ${c.balance > 0 ? `
                                        <button class="btn btn-success reset-payment" data-username="${encodeURIComponent(c.username)}">Reset payment</button>
                                    ` : ""}
                                </td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
                </div>
            </div>
        `;
    },

    async viewCustomer(username) {
        try {
            const data = await API.get(`/customers/${encodeURIComponent(username)}`);
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
            const months = groupOrdersByMonth(data.orders);
            Modal.open(`
                <h2>👤 ${esc(data.customer.username)}</h2>
                <div class="balance-big">${fmt(data.balance)}</div>
                <p style="text-align:center; color:var(--muted); margin-bottom:1rem;">balance to pay</p>
                ${data.stats.next_due_date && data.balance > 0 ? `
                    <p style="text-align:center; color:var(--warning); font-weight:600; margin:0 0 0.5rem;">
                        Next payment due: ${new Date(data.stats.next_due_date).toLocaleDateString()}
                    </p>
                ` : ""}
                <div style="display:flex; justify-content:space-between; padding:0.5rem 0; border-top:1px solid var(--border); border-bottom:1px solid var(--border); margin-bottom:1rem;">
                    <span style="color:var(--muted);">Total paid</span>
                    <span style="font-weight:700;">${fmt(data.total_paid)}</span>
                </div>
                ${renderCustomerStats(data.stats)}
                <h3 style="margin:1.25rem 0 0.5rem;">Order history</h3>
                ${data.orders.length === 0
                    ? '<p style="color:var(--muted);">No orders.</p>'
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
                    ${data.balance > 0 ? `
                        <button class="btn btn-success" id="reset-from-modal" data-username="${encodeURIComponent(data.customer.username)}">Reset payment</button>
                    ` : ""}
                    <button class="btn btn-secondary" data-action="modal-close">Close</button>
                </div>
            `);
            const reset = document.getElementById("reset-from-modal");
            if (reset) {
                reset.addEventListener("click", async () => {
                    await this.resetPayment(data.customer.username);
                });
            }
        } catch (err) {
            Toast.error(err.message);
        }
    },

    confirmResetPayment(username) {
        Modal.open(`
            <h2>Reset payment</h2>
            <p>Mark all unpaid orders for <strong>${esc(username)}</strong> as paid?</p>
            <div class="form-actions">
                <button class="btn btn-secondary" data-action="modal-close">Cancel</button>
                <button class="btn btn-success" id="confirm-reset">Reset payment</button>
            </div>
        `);
        document.getElementById("confirm-reset").addEventListener("click", async () => {
            await this.resetPayment(username);
        });
    },

    async resetPayment(username) {
        try {
            const res = await API.post(`/customers/${encodeURIComponent(username)}/reset-payment`, {});
            Modal.close();
            Toast.success(`${res.settled} order(s) settled for ${res.username} (${fmt(res.amount)})`);
            if (this.view === "customers") {
                this.renderCustomers();
            }
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async renderReports() {
        const [summary, topProducts, salesByDay, customerInsights] = await Promise.all([
            API.get("/reports/summary"),
            API.get("/reports/top-products?limit=10"),
            API.get("/reports/sales-by-day?days=14"),
            API.get("/reports/customer-insights"),
        ]);
        const max = Math.max(...salesByDay.map((d) => d.revenue), 1);
        const revenueByDay = salesByDay.map((d) => ({
            ...d,
            orders: 0,
        }));
        const ordersMax = Math.max(...revenueByDay.map((d) => d.orders), 1);
        const app = this.mainFor("reports");
        if (!app) return;
        const customerLeaders = (title, leaders) => `
            <div class="panel">
                <div class="panel-header"><h3>${title}</h3></div>
                <table>
                    <thead><tr><th>#</th><th>Customer</th><th>Paid orders</th><th>Spent</th></tr></thead>
                    <tbody>
                        ${leaders.length === 0
                            ? '<tr><td colspan="4">No paid orders in this period</td></tr>'
                            : leaders.map((leader, i) => `
                                <tr><td>${i + 1}</td><td><strong>${esc(leader.username)}</strong></td><td>${leader.orders}</td><td>${fmt(leader.spent)}</td></tr>
                            `).join("")}
                    </tbody>
                </table>
            </div>
        `;
        const productLeaders = (title, leaders) => `
            <div class="panel">
                <div class="panel-header"><h3>${title}</h3></div>
                <table>
                    <thead><tr><th>#</th><th>Product</th><th>Units bought</th><th>Sales</th></tr></thead>
                    <tbody>
                        ${leaders.length === 0
                            ? '<tr><td colspan="4">No paid orders in this period</td></tr>'
                            : leaders.map((product, i) => `
                                <tr><td>${i + 1}</td><td><strong>${esc(product.product)}</strong></td><td>${product.quantity}</td><td>${fmt(product.revenue)}</td></tr>
                            `).join("")}
                    </tbody>
                </table>
            </div>
        `;
        app.innerHTML = `
            <div class="admin-main">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; margin-bottom:1rem;">
                    <h2 style="margin:0;">Reports</h2>
                    <button class="btn btn-primary" data-action="admin-export-reports-csv">Export CSV</button>
                </div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="label">Outstanding Balance</div><div class="value" style="color:var(--warning);">${fmt(summary.outstanding)}</div><div class="sub">${summary.pending_orders} unpaid order(s)</div></div>
                    <div class="stat-card"><div class="label">Today (paid)</div><div class="value">${fmt(summary.today.revenue)}</div><div class="sub">${summary.today.order_count} orders</div></div>
                    <div class="stat-card"><div class="label">Yesterday (paid)</div><div class="value">${fmt(summary.yesterday.revenue)}</div><div class="sub">${summary.yesterday.order_count} orders</div></div>
                    <div class="stat-card"><div class="label">This Week (paid)</div><div class="value">${fmt(summary.week.revenue)}</div><div class="sub">${summary.week.order_count} orders</div></div>
                    <div class="stat-card"><div class="label">This Month (paid)</div><div class="value">${fmt(summary.month.revenue)}</div><div class="sub">${summary.month.order_count} orders</div></div>
                </div>
                <div class="panel">
                    <div class="panel-header"><h3>Revenue (last 14 days)</h3></div>
                    <div class="chart">
                        <div style="flex:1; height:160px;" class="chart-wrap">
                            ${salesByDay.map((d) => `
                                <div style="display:inline-block; width:${100 / Math.max(salesByDay.length, 1)}%; height:100%; text-align:center; position:relative;">
                                    <div class="chart-col" style="height:${Math.max(4, (d.revenue / max) * 140)}px; display:inline-block; vertical-align:bottom;">
                                        <span style="font-size:0.65rem; color:var(--muted);">${fmt(d.revenue)}</span>
                                    </div>
                                    <div class="chart-label">${d.day.slice(5)}</div>
                                </div>
                            `).join("")}
                        </div>
                    </div>
                </div>
                <div class="panel" id="margins-panel"></div>
                <h3 style="margin:1.5rem 0 0.75rem;">Customer insights</h3>
                <p style="color:var(--muted); margin:0 0 0.75rem;">Ranked by total paid, then order count, using the payment date in the current day, Monday-start week, and calendar month.</p>
                <div class="stat-card" style="margin-bottom:1rem;">
                    <div class="label">Last customer to pay</div>
                    ${customerInsights.last_paid ? `
                        <div class="value">${esc(customerInsights.last_paid.username)}</div>
                        <div class="sub">Order #${customerInsights.last_paid.order_id} · ${fmt(customerInsights.last_paid.amount)} · ${new Date(customerInsights.last_paid.paid_at).toLocaleString()}</div>
                    ` : '<div class="value">No payments yet</div>'}
                </div>
                ${customerLeaders("Top customers today", customerInsights.today)}
                ${customerLeaders("Top customers this week", customerInsights.week)}
                ${customerLeaders("Top customers this month", customerInsights.month)}
                <h3 style="margin:1.5rem 0 0.75rem;">Most purchased products</h3>
                ${productLeaders("Products bought most today", customerInsights.products_today)}
                ${productLeaders("Products bought most this week", customerInsights.products_week)}
                ${productLeaders("Products bought most this month", customerInsights.products_month)}
                <div class="panel">
                    <div class="panel-header"><h3>Top Products</h3></div>
                    <table>
                        <thead><tr><th>#</th><th>Product</th><th>Units Sold</th><th>Revenue</th></tr></thead>
                        <tbody>
                            ${topProducts.length === 0
                                ? '<tr><td colspan="4">No sales yet</td></tr>'
                                : topProducts.map((p, i) => `
                                    <tr><td>${i + 1}</td><td>${esc(p.product)}</td><td>${p.quantity}</td><td>${fmt(p.revenue)}</td></tr>
                                `).join("")}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        this.renderMargins();
    },

    marginsPeriod: "month",

    async renderMargins(period = this.marginsPeriod) {
        this.marginsPeriod = period;
        const panel = document.getElementById("margins-panel");
        if (!panel) return;
        let report;
        try {
            report = await API.get(`/reports/margins?period=${encodeURIComponent(period)}`);
        } catch (err) {
            panel.innerHTML = `<p style="padding:1rem;">${esc(err.message)}</p>`;
            return;
        }
        const pct = (v) => (v == null ? "—" : `${v}%`);
        const periods = [["today", "Today"], ["week", "This week"], ["month", "This month"], ["all", "All time"]];
        panel.innerHTML = `
            <div class="panel-header" style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                <h3>Margins (paid sales)</h3>
                <div class="toolbar" style="margin:0;">
                    ${periods.map(([key, label]) => `
                        <button class="btn ${key === period ? "btn-primary" : "btn-secondary"}" data-action="admin-margins-period" data-period="${key}">${label}</button>
                    `).join("")}
                </div>
            </div>
            <table>
                <thead><tr><th>Product</th><th>Units</th><th>Revenue</th><th>Cost</th><th>Margin</th><th>Margin %</th></tr></thead>
                <tbody>
                    ${report.products.length === 0
                        ? '<tr><td colspan="6">No paid sales in this period</td></tr>'
                        : report.products.map((r) => `
                            <tr>
                                <td>${esc(r.product)}${r.uncosted_quantity ? ` <span class="muted-note" title="Sold before a purchase price was set">(${r.uncosted_quantity} without cost)</span>` : ""}</td>
                                <td>${r.quantity}</td>
                                <td>${fmt(r.revenue)}</td>
                                <td>${fmt(r.cost)}</td>
                                <td style="font-weight:600; color:${r.margin < 0 ? "var(--danger)" : "inherit"};">${fmt(r.margin)}</td>
                                <td>${pct(r.margin_pct)}</td>
                            </tr>
                        `).join("")}
                </tbody>
                <tfoot>
                    <tr><th>Total</th><th>${report.totals.quantity}</th><th>${fmt(report.totals.revenue)}</th><th>${fmt(report.totals.cost)}</th><th>${fmt(report.totals.margin)}</th><th>${pct(report.totals.margin_pct)}</th></tr>
                </tfoot>
            </table>
            <p class="muted-note" style="padding:0.5rem 1rem;">Cost is the purchase price at the time of sale. Units sold before a purchase price was set count as revenue but not toward the margin.</p>
        `;
    },

    async exportReportsCsv() {
        try {
            await API.download("/reports/export.csv", "kiosk-report.csv");
            Toast.success("Report exported as CSV");
        } catch (err) {
            Toast.error(err.message);
        }
    },

    auditFilters: [
        ["", "Everything"],
        ["order.", "Orders"],
        ["customer.", "Payments"],
        ["product.restock", "Deliveries"],
        ["product.", "Products"],
        ["settings.", "Settings"],
        ["user.", "Users"],
        ["backup.", "Backups"],
    ],

    async renderAudit() {
        const app = this.mainFor("audit");
        if (!app) return;
        app.innerHTML = `
            <div class="admin-main">
                <h2>Audit log</h2>
                <p style="color:var(--muted); margin-bottom:1rem;">
                    Who changed what and when: payments, cancellations, stock, prices, settings,
                    users and backups. "kiosk" means a customer at the kiosk.
                </p>
                <div class="toolbar">
                    <label for="audit-filter" style="font-weight:600;">Show</label>
                    <select id="audit-filter" data-action-input="admin-audit-filter">
                        ${this.auditFilters.map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}
                    </select>
                </div>
                <div class="panel" id="audit-rows"></div>
            </div>
        `;
        await this.renderAuditRows("");
    },

    async renderAuditRows(action) {
        const panel = document.getElementById("audit-rows");
        if (!panel) return;
        try {
            const query = action ? `&action=${encodeURIComponent(action)}` : "";
            const entries = await API.get(`/audit?limit=300${query}`);
            panel.innerHTML = `
                <table>
                    <thead><tr><th>Time</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
                    <tbody>
                        ${entries.length === 0
                            ? '<tr><td colspan="5">Nothing recorded yet</td></tr>'
                            : entries.map((e) => `
                                <tr>
                                    <td style="white-space:nowrap;">${new Date(e.created_at).toLocaleString()}</td>
                                    <td><strong>${esc(e.actor)}</strong></td>
                                    <td><span class="audit-action">${esc(e.action)}</span></td>
                                    <td>${esc(e.entity)}${e.entity_id ? ` ${esc(e.entity === "order" ? "#" + e.entity_id : e.entity_id)}` : ""}</td>
                                    <td class="audit-details">${esc(e.details)}</td>
                                </tr>
                            `).join("")}
                    </tbody>
                </table>
            `;
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async renderSystem() {
        const status = await API.get("/system/status");
        const app = this.mainFor("system");
        if (!app) return;
        const front = AppInfo.info || {};
        const tag = (v) => (/^\d/.test(v || "") ? "v" + v : (v || "dev"));
        const short = (c) => (c ? String(c).slice(0, 7) : "—");
        const released = (v) => /^\d/.test(v || "");
        const mismatch = released(front.version) && released(status.version) && status.version !== front.version;
        const noBackupHint = status.database.engine === "postgresql"
            ? "This installation uses PostgreSQL. Back it up with <code>pg_dump</code>."
            : `Backups are not available for this database (${esc(status.database.engine)}).`;
        const b = status.backups;
        const backupAge = b.last_backup_at ? (Date.now() - new Date(b.last_backup_at).getTime()) / 3600000 : null;
        const backupStale = b.supported && b.interval_hours > 0 && (backupAge == null || backupAge > b.interval_hours * 2);
        app.innerHTML = `
            <div class="admin-main">
                <h2>System</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="label">Version</div>
                        <div class="value">${esc(tag(status.version))}</div>
                        <div class="sub">backend ${esc(short(status.commit))} · frontend ${esc(tag(front.version))} ${esc(short(front.commit))}</div>
                        ${mismatch ? '<div class="sub" style="color:var(--warning); font-weight:600;">⚠ Backend and frontend versions differ</div>' : ""}
                    </div>
                    <div class="stat-card"><div class="label">Uptime</div><div class="value">${fmtDuration(status.uptime_seconds)}</div><div class="sub">since ${new Date(status.started_at).toLocaleString()}</div></div>
                    <div class="stat-card"><div class="label">Database</div><div class="value">${fmtBytes(status.database.size_bytes)}</div><div class="sub">${esc(status.database.engine)} · Python ${esc(status.python)}</div></div>
                    <div class="stat-card">
                        <div class="label">Last backup</div>
                        <div class="value" style="${backupStale ? "color:var(--danger);" : ""}">${b.last_backup_at ? new Date(b.last_backup_at).toLocaleString() : (b.supported ? "Never" : "n/a")}</div>
                        <div class="sub">${b.supported ? `${b.count} kept · ${fmtBytes(b.total_bytes)}` : (status.database.engine === "postgresql" ? "PostgreSQL: use pg_dump" : "not available")}</div>
                    </div>
                </div>
                <div class="stats-grid">
                    <div class="stat-card"><div class="label">Products</div><div class="value">${status.counts.active_products}</div><div class="sub">${status.counts.products} total · ${status.counts.low_stock_products} need restock</div></div>
                    <div class="stat-card"><div class="label">Customers</div><div class="value">${status.counts.customers}</div></div>
                    <div class="stat-card"><div class="label">Orders</div><div class="value">${status.counts.orders}</div><div class="sub">${status.counts.pending_orders} unpaid</div></div>
                    <div class="stat-card"><div class="label">Last change</div><div class="value" style="font-size:1rem;">${status.last_activity ? esc(status.last_activity.action) : "—"}</div><div class="sub">${status.last_activity ? `${esc(status.last_activity.actor)} · ${new Date(status.last_activity.at).toLocaleString()}` : ""}</div></div>
                </div>
                <div class="panel" id="backups-panel">
                    <div class="panel-header" style="display:flex; justify-content:space-between; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                        <h3>Backups</h3>
                        ${b.supported ? '<button class="btn btn-primary" data-action="admin-backup-now">Back up now</button>' : ""}
                    </div>
                    ${b.supported ? `
                        <p class="muted-note" style="padding:0 1rem;">
                            ${b.interval_hours > 0 ? `Automatic backup every ${b.interval_hours} h` : "Automatic backups are off"} ·
                            keeps the newest ${b.keep} · stored in <code>data/backups/</code> next to the database.
                            Change this under Settings. Copy backups off the device now and then.
                        </p>
                        <table>
                            <thead><tr><th>Backup</th><th>Taken</th><th>Size</th><th></th></tr></thead>
                            <tbody>
                                ${b.items.length === 0
                                    ? '<tr><td colspan="4">No backups yet</td></tr>'
                                    : b.items.map((item) => `
                                        <tr>
                                            <td><code>${esc(item.name)}</code></td>
                                            <td>${new Date(item.created_at).toLocaleString()}</td>
                                            <td>${fmtBytes(item.size_bytes)}</td>
                                            <td class="table-actions"><button class="btn btn-secondary" data-action="admin-backup-download" data-name="${esc(item.name)}">Download</button></td>
                                        </tr>
                                    `).join("")}
                            </tbody>
                        </table>
                    ` : `<p class="muted-note" style="padding:0 1rem 1rem;">${noBackupHint}</p>`}
                </div>
            </div>
        `;
    },

    async backupNow() {
        try {
            const result = await API.post("/system/backups", {});
            Toast.success(`Backup ${result.name} created (${fmtBytes(result.size_bytes)})`);
            if (this.view === "system") this.renderSystem();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async downloadBackup(name) {
        try {
            await API.download(`/system/backups/${encodeURIComponent(name)}`, name);
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async renderUsers() {
        const users = await API.get("/users");
        const app = this.mainFor("users");
        if (!app) return;
        app.innerHTML = `
            <div class="admin-main">
                <h2>Users</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" data-action="admin-new-user">+ New User</button>
                </div>
                <div class="panel">
                <table>
                    <thead><tr><th>ID</th><th>Username</th><th>Full Name</th><th>Created</th><th>Status</th><th></th></tr></thead>
                    <tbody>
                        ${users.map((u) => `
                            <tr>
                                <td>${u.id}</td>
                                <td>${esc(u.username)}</td>
                                <td>${esc(u.full_name || "—")}</td>
                                <td>${new Date(u.created_at).toLocaleDateString()}</td>
                                <td>${u.is_active ? '<span class="status-badge status-completed">Active</span>' : '<span class="status-badge status-cancelled">Disabled</span>'}</td>
                                <td class="table-actions">
                                    <button class="btn btn-secondary edit-user" data-id="${u.id}">Edit</button>
                                    ${u.id !== this.session?.id ? `<button class="btn btn-danger delete-user" data-id="${u.id}">Delete</button>` : ""}
                                </td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
                </div>
            </div>
        `;
    },

    openUserModal(id) {
        Modal.open(`
            <h2>${id ? "Edit User" : "New User"}</h2>
            <form id="user-form">
                ${id ? "" : `
                <div class="form-group">
                    <label>Username</label>
                    <input id="u-username" required>
                </div>`}
                <div class="form-group">
                    <label>Full Name</label>
                    <input id="u-fullname">
                </div>
                <div class="form-group">
                    <label>Password ${id ? "(leave blank to keep)" : ""}</label>
                    <input id="u-password" type="password" ${id ? "" : "required"}>
                </div>
                ${id ? `
                <div class="form-group">
                    <label style="display:flex; align-items:center; gap:0.5rem;">
                        <input type="checkbox" id="u-active"> Active
                    </label>
                </div>` : ""}
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" data-action="modal-close">Cancel</button>
                    <button type="submit" class="btn btn-primary">Save</button>
                </div>
            </form>
        `);
        const users = null;
        if (id) {
            API.get("/users").then((users) => {
                const user = users.find((u) => u.id === id);
                if (!user) return;
                const nameInput = document.getElementById("u-fullname");
                if (nameInput) nameInput.value = user.full_name || "";
                const activeInput = document.getElementById("u-active");
                if (activeInput) activeInput.checked = user.is_active;
            });
        }
        document.getElementById("user-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            const payload = {
                full_name: document.getElementById("u-fullname").value,
            };
            const password = document.getElementById("u-password").value;
            if (password) payload.password = password;
            if (id) {
                payload.is_active = document.getElementById("u-active").checked;
            }
            try {
                if (id) {
                    await API.put(`/users/${id}`, payload);
                    Toast.success("User updated");
                } else {
                    await API.post("/users", { ...payload, username: document.getElementById("u-username").value.trim() });
                    Toast.success("User created");
                }
                Modal.close();
                this.renderUsers();
            } catch (err) {
                Toast.error(err.message);
            }
        });
    },

    confirmDeleteUser(id) {
        Modal.open(`
            <h2>Delete User</h2>
            <p>Delete this user? This cannot be undone.</p>
            <div class="form-actions">
                <button class="btn btn-secondary" data-action="modal-close">Cancel</button>
                <button class="btn btn-danger" id="confirm-delete">Delete</button>
            </div>
        `);
        document.getElementById("confirm-delete").addEventListener("click", async () => {
            try {
                await API.del(`/users/${id}`);
                Toast.success("User deleted");
                Modal.close();
                this.renderUsers();
            } catch (err) {
                Toast.error(err.message);
            }
        });
    },

    async renderSettings() {
        await Store.loadPublicData();
        const settings = Store.settings;
        let nextDue = null;
        try {
            nextDue = await API.get("/reports/summary");
        } catch {}
        const app = this.mainFor("settings");
        if (!app) return;
        const dueDate = settings.payment_due_date ?? "";
        app.innerHTML = `
            <div class="admin-main">
                <h2>Store Settings</h2>
                <div class="panel" style="max-width:640px;">
                    <div class="form-group">
                        <label>Store Name</label>
                        <input id="s-store_name" value="${esc(settings.store_name || "")}">
                    </div>
                    <div class="form-group">
                        <label>Receipt Footer</label>
                        <textarea id="s-receipt_footer" rows="2">${esc(settings.receipt_footer || "")}</textarea>
                    </div>
                    <div class="form-group">
                        <label>Currency</label>
                        <select id="s-currency">
                            ${Object.entries(SUPPORTED_CURRENCIES).map(([code, name]) => `
                                <option value="${code}" ${(settings.currency || "EUR") === code ? "selected" : ""}>
                                    ${code} — ${esc(name)}
                                </option>
                            `).join("")}
                        </select>
                    </div>
                    <div class="form-group" style="border-top:1px solid var(--border); padding-top:1rem;">
                        <label>Payment Due Date (optional)</label>
                        <input id="s-payment_due_date" type="date" value="${esc(dueDate)}">
                        <div style="font-size:0.8rem; color:var(--muted); margin-top:0.25rem;">
                            Orders must be paid by this date. Leave empty for no end
                            date (default).
                            ${nextDue?.next_due_date ? ` · Next due: <strong>${new Date(nextDue.next_due_date).toLocaleDateString()}</strong>` : ""}
                        </div>
                    </div>
                    <div class="form-group">
                        <label style="display:flex; align-items:center; gap:0.5rem;">
                            <input type="checkbox" id="s-customer_self_service_payment"
                                ${settings.customer_self_service_payment === "true" ? "checked" : ""}>
                            Allow customers to mark all their unpaid orders as paid from lookup
                        </label>
                        <div style="font-size:0.8rem; color:var(--warning); margin-top:0.25rem;">
                            This does not verify identity or payment. Anyone who knows a
                            username can mark that customer's balance as paid.
                        </div>
                    </div>
                    <div class="form-group" style="border-top:1px solid var(--border); padding-top:1rem;">
                        <label for="s-kiosk_idle_seconds">Reset the kiosk after inactivity (seconds)</label>
                        <input id="s-kiosk_idle_seconds" type="number" min="0" step="1" value="${esc(settings.kiosk_idle_seconds ?? "90")}">
                        <div style="font-size:0.8rem; color:var(--muted); margin-top:0.25rem;">
                            After this long without a touch, the kiosk warns for 10 seconds and then clears the
                            cart and closes open dialogs, so the next customer starts fresh. 0 turns it off.
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="s-backup_interval_hours">Automatic database backup every (hours)</label>
                        <input id="s-backup_interval_hours" type="number" min="0" step="1" value="${esc(settings.backup_interval_hours ?? "24")}">
                    </div>
                    <div class="form-group">
                        <label for="s-backup_keep">Backups to keep</label>
                        <input id="s-backup_keep" type="number" min="1" max="365" step="1" value="${esc(settings.backup_keep ?? "7")}">
                        <div style="font-size:0.8rem; color:var(--muted); margin-top:0.25rem;">
                            0 hours turns automatic backups off; "Back up now" on the System page still works.
                        </div>
                    </div>
                    <div class="form-group">
                        <label style="display:flex; align-items:center; gap:0.5rem;">
                            <input type="checkbox" id="s-debug_mode" ${Debug.isOn(settings) ? "checked" : ""}>
                            🐞 Debug mode (show load times &amp; verbose info on every site)
                        </label>
                    </div>
                    <button class="btn btn-primary" data-action="admin-save-settings">Save Settings</button>
                </div>
            </div>
        `;
    },

    async saveSettings() {
        const fields = {
            store_name: document.getElementById("s-store_name").value.trim(),
            receipt_footer: document.getElementById("s-receipt_footer").value,
            currency: document.getElementById("s-currency").value,
            debug_mode: document.getElementById("s-debug_mode").checked ? "true" : "false",
            payment_due_date: document.getElementById("s-payment_due_date").value.trim(),
            customer_self_service_payment: document.getElementById("s-customer_self_service_payment").checked ? "true" : "false",
            kiosk_idle_seconds: String(Math.max(0, parseInt(document.getElementById("s-kiosk_idle_seconds").value) || 0)),
            backup_interval_hours: String(Math.max(0, parseInt(document.getElementById("s-backup_interval_hours").value) || 0)),
            backup_keep: String(Math.min(365, Math.max(1, parseInt(document.getElementById("s-backup_keep").value) || 7))),
        };
        try {
            for (const [key, value] of Object.entries(fields)) {
                await API.put(`/settings/${key}`, { key, value: String(value) });
            }
            Store.settings = { ...Store.settings, ...fields };
            Debug.syncSetting();
            Toast.success("Settings saved");
            this.renderSettings();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async render() {
        this.readSession();
        if (!this.isLoggedIn()) {
            this.renderLogin();
            return;
        }
        const user = this.session;
        if (!Store.settings.store_name) {
            try {
                await Store.loadPublicData();
            } catch {}
        }
        document.getElementById("app").innerHTML = `
            <div class="admin-layout">
                ${this.renderSidebar(user)}
                <div id="admin-main-container"></div>
            </div>
        `;
        try {
            await this.loadView(this.view);
        } catch (err) {
            Toast.error(err.message);
        }
    },
};