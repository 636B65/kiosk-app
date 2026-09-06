const Actions = {
    handlers: {},

    register(action, fn) {
        this.handlers[action] = fn;
    },

    init() {
        document.addEventListener("click", (e) => {
            const el = e.target.closest("[data-action]");
            if (!el) return;
            const fn = this.handlers[el.dataset.action];
            if (fn) fn(el, e);
        });
        document.addEventListener("input", (e) => {
            if (!e.target.matches("[data-action-input]")) return;
            const fn = this.handlers[e.target.dataset.actionInput];
            if (fn) fn(e.target, e);
        });
    },
};

Actions.register("modal-close", () => Modal.close());

Actions.register("admin-new-product", () => Admin.openProductModal());
Actions.register("admin-new-category", () => Admin.openCategoryModal());
Actions.register("admin-new-user", () => Admin.openUserModal());
Actions.register("admin-save-settings", () => Admin.saveSettings());

Actions.register("kiosk-new-order", () => {
    Modal.close();
    Kiosk.newOrder();
});
Actions.register("kiosk-open-lookup", () => Kiosk.openLookup());
Actions.register("kiosk-search", () => Kiosk.renderProductGrid());
