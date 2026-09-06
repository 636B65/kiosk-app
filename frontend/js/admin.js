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
            ["users", "👤", "Users"],
            ["settings", "⚙️", "Settings"],
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
            default: return this.renderDashboard();
        }
    },

    async renderDashboard() {
        const [summary, topProducts] = await Promise.all([
            API.get("/reports/summary"),
            API.get("/reports/top-products?limit=5"),
        ]);
        const app = document.getElementById("admin-main-container");
        app.innerHTML = `
            <div class="admin-main">
                <h2>Dashboard</h2>
                <div class="stats-grid">
                    <div class="stat-card"><div class="label">Outstanding Balance</div><div class="value" style="color:var(--warning);">${fmt(summary.outstanding)}</div><div class="sub">${summary.pending_orders} unpaid order(s)</div></div>
                    <div class="stat-card"><div class="label">Today's Paid</div><div class="value">${fmt(summary.today.revenue)}</div><div class="sub">${summary.today.order_count} order(s)</div></div>
                    <div class="stat-card"><div class="label">This Week</div><div class="value">${fmt(summary.week.revenue)}</div></div>
                    <div class="stat-card"><div class="label">This Month</div><div class="value">${fmt(summary.month.revenue)}</div></div>
                    <div class="stat-card"><div class="label">All-time Paid</div><div class="value">${fmt(summary.all_time.revenue)}</div></div>
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
                <div class="panel">
                    <div class="panel-header"><h3>Low Stock Alerts</h3></div>
                    <table>
                        <thead><tr><th>Product</th><th>Stock</th><th>Price</th></tr></thead>
                        <tbody>
                            ${summary.low_stock_products.length === 0
                                ? '<tr><td colspan="3">All stock levels are healthy</td></tr>'
                                : summary.low_stock_products.map((p) => `
                                    <tr><td>${esc(p.name)}</td><td style="color:var(--warning);"><strong>${p.stock}</strong></td><td>${fmt(effectivePrice(p))}</td></tr>
                                `).join("")}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    },

    async renderProducts() {
        await Store.refresh();
        const app = document.getElementById("admin-main-container");
        const products = [...Store.products].sort((a, b) => a.id - b.id);
        app.innerHTML = `
            <div class="admin-main">
                <h2>Products</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" onclick="Admin.openProductModal()">+ New Product</button>
                </div>
                <div class="panel">
                <table>
                    <thead><tr><th>ID</th><th>Name</th><th>Image</th><th>Category</th><th>Price</th><th>Stock</th><th>Status</th><th></th></tr></thead>
                    <tbody>
                        ${products.map((p) => `
                            <tr>
                                <td>${p.id}</td>
                                <td>${esc(p.name)}${p.is_weekly_special ? ' <span class="weekly-badge">⚡ Weekly</span>' : ""}</td>
                                <td>${p.image_url ? `<img class="thumb" src="${esc(p.image_url)}" alt="">` : "—"}</td>
                                <td>${p.category ? esc(p.category.name) : "—"}</td>
                                <td>${p.is_weekly_special && p.special_price != null
                                    ? `<span class="price-old">${fmt(p.price)}</span> <span class="price-special">${fmt(p.special_price)}</span>`
                                    : fmt(p.price)}</td>
                                <td style="${p.stock <= 5 ? "color:var(--warning); font-weight:600;" : ""}">${p.stock}</td>
                                <td>${p.is_active ? '<span class="status-badge status-completed">Active</span>' : '<span class="status-badge status-cancelled">Inactive</span>'}</td>
                                <td class="table-actions">
                                    <button class="btn btn-secondary edit-product" data-id="${p.id}">Edit</button>
                                    <button class="btn btn-danger delete-product" data-id="${p.id}">Delete</button>
                                </td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
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
                <div class="form-group" style="display:${product?.is_weekly_special ? "" : "none"};">
                    <label>Special price (${esc(Store.settings.currency || "EUR")})</label>
                    <input id="p-special-price" type="number" step="0.01" min="0" value="${product?.special_price ?? ""}">
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
                    <label>Stock</label>
                    <input id="p-stock" type="number" step="1" min="0" value="${product?.stock ?? ""}" required>
                </div>
                <div class="form-group">
                    <label style="display:flex; align-items:center; gap:0.5rem;">
                        <input type="checkbox" id="p-active" ${product === null || product.is_active ? "checked" : ""}>
                        Active (visible to customers)
                    </label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
                    <button type="submit" class="btn btn-primary">Save</button>
                </div>
            </form>
        `);
        document.getElementById("p-weekly").addEventListener("change", (e) => {
            const group = document.getElementById("p-special-price").closest(".form-group");
            if (group) group.style.display = e.target.checked ? "" : "none";
            if (!e.target.checked) document.getElementById("p-special-price").value = "";
        });
        document.getElementById("product-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            const isWeekly = document.getElementById("p-weekly").checked;
            const specialPriceInput = document.getElementById("p-special-price").value;
            const payload = {
                name: document.getElementById("p-name").value.trim(),
                description: document.getElementById("p-desc").value,
                category_id: document.getElementById("p-category").value ? parseInt(document.getElementById("p-category").value) : null,
                price: parseFloat(document.getElementById("p-price").value) || 0,
                stock: parseInt(document.getElementById("p-stock").value) || 0,
                is_active: document.getElementById("p-active").checked,
                is_weekly_special: isWeekly,
                special_price: isWeekly && specialPriceInput !== "" ? parseFloat(specialPriceInput) : null,
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
                <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
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

    async renderCategories() {
        await Store.refresh();
        const app = document.getElementById("admin-main-container");
        const countByCat = {};
        Store.products.forEach((p) => {
            if (p.category_id != null) countByCat[p.category_id] = (countByCat[p.category_id] || 0) + 1;
        });
        const categories = [...Store.categories].sort((a, b) => a.sort_order - b.sort_order);
        app.innerHTML = `
            <div class="admin-main">
                <h2>Categories</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" onclick="Admin.openCategoryModal()">+ New Category</button>
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
                    <button type="button" class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
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
                <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
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
        const app = document.getElementById("admin-main-container");
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
                    <thead><tr><th>#</th><th>Date</th><th>User</th><th>Items</th><th>Total</th><th>Status</th><th></th></tr></thead>
                    <tbody>
                        ${orders.map((o) => `
                            <tr>
                                <td>${o.id}</td>
                                <td>${new Date(o.created_at).toLocaleString()}</td>
                                <td>${o.customer_username ? esc(o.customer_username) : "—"}</td>
                                <td><button class="btn btn-secondary view-order" data-id="${o.id}">View items</button></td>
                                <td>${fmt(o.total)}</td>
                                <td><span class="status-badge status-${o.status}">${o.status}</span></td>
                                <td class="table-actions">
                                    ${o.status === "pending" ? `
                                        <button class="btn btn-success change-status" data-id="${o.id}" data-status="paid">Mark paid</button>
                                        <button class="btn btn-danger change-status" data-id="${o.id}" data-status="cancelled">Cancel</button>
                                    ` : ""}
                                </td>
                            </tr>
                        `).join("")}
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
                    <button class="btn btn-secondary" onclick="Modal.close()">Close</button>
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
        const app = document.getElementById("admin-main-container");
        app.innerHTML = `
            <div class="admin-main">
                <h2>Customers</h2>
                <p style="color:var(--muted); margin-bottom:1rem;">
                    Customers are created automatically at the kiosk when they buy for the first time.
                    Reset payment clears a customer's outstanding balance.
                </p>
                <div class="panel">
                <table>
                    <thead><tr><th>User</th><th>Created</th><th>Orders</th><th>Total paid</th><th>Balance to pay</th><th></th></tr></thead>
                    <tbody>
                        ${customers.length === 0
                            ? '<tr><td colspan="6">No customers yet</td></tr>'
                            : customers.map((c) => `
                            <tr>
                                <td><strong>${esc(c.username)}</strong></td>
                                <td>${new Date(c.created_at).toLocaleDateString()}</td>
                                <td>${c.order_count}</td>
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
                    <button class="btn btn-secondary" onclick="Modal.close()">Close</button>
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
                <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
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
        const [summary, topProducts, salesByDay] = await Promise.all([
            API.get("/reports/summary"),
            API.get("/reports/top-products?limit=10"),
            API.get("/reports/sales-by-day?days=14"),
        ]);
        const max = Math.max(...salesByDay.map((d) => d.revenue), 1);
        const revenueByDay = salesByDay.map((d) => ({
            ...d,
            orders: 0,
        }));
        const ordersMax = Math.max(...revenueByDay.map((d) => d.orders), 1);
        const app = document.getElementById("admin-main-container");
        app.innerHTML = `
            <div class="admin-main">
                <h2>Reports</h2>
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
    },

    async renderUsers() {
        const users = await API.get("/users");
        const app = document.getElementById("admin-main-container");
        app.innerHTML = `
            <div class="admin-main">
                <h2>Users</h2>
                <div class="toolbar">
                    <button class="btn btn-primary" onclick="Admin.openUserModal()">+ New User</button>
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
                    <button type="button" class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
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
                <button class="btn btn-secondary" onclick="Modal.close()">Cancel</button>
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
        const app = document.getElementById("admin-main-container");
        const settings = Store.settings;
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
                    <div class="form-group">
                        <label style="display:flex; align-items:center; gap:0.5rem;">
                            <input type="checkbox" id="s-debug_mode" ${Debug.isOn(settings) ? "checked" : ""}>
                            🐞 Debug mode (show load times &amp; verbose info on every site)
                        </label>
                    </div>
                    <button class="btn btn-primary" onclick="Admin.saveSettings()">Save Settings</button>
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