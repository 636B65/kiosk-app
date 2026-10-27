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
        document.addEventListener("keydown", (e) => {
            if (e.key !== "Escape" || document.getElementById("idle-warning")) return;
            if (document.getElementById("modal-overlay")) {
                Modal.close();
            } else {
                document.getElementById("cart-overlay")?.remove();
            }
        });
        document.addEventListener("input", (e) => {
            if (!e.target.matches("[data-action-input]")) return;
            const fn = this.handlers[e.target.dataset.actionInput];
            if (fn) fn(e.target, e);
        });
    },
};

Actions.register("modal-close", () => Modal.close());
Actions.register("show-changelog", () => AppInfo.openChangelog());

Actions.register("admin-new-product", () => Admin.openProductModal());
Actions.register("admin-new-category", () => Admin.openCategoryModal());
Actions.register("admin-new-user", () => Admin.openUserModal());
Actions.register("admin-save-settings", () => Admin.saveSettings());
Actions.register("admin-export-reports-csv", () => Admin.exportReportsCsv());

Actions.register("kiosk-new-order", () => {
    Modal.close();
    Kiosk.newOrder();
});
Actions.register("kiosk-open-lookup", () => Kiosk.openLookup());
Actions.register("kiosk-lookup-suggest", (el) => Kiosk.suggestLookup(el));
Actions.register("kiosk-lookup-pick", (el) => Kiosk.pickLookup(el.dataset.username));
Actions.register("kiosk-mark-all-paid", (el) =>
    Kiosk.markAllPaid(decodeURIComponent(el.dataset.username))
);
Actions.register("kiosk-search", () => Kiosk.renderProductGrid());
Actions.register("kiosk-idle-continue", () => Kiosk.noteActivity());
Actions.register("kiosk-buy-again", (el) => Kiosk.buyAgain(parseInt(el.dataset.id)));
Actions.register("kiosk-open-cart", () => Kiosk.openCartFromModal());
Actions.register("kiosk-forgot-pin", (el) => {
    const help = el.parentElement.querySelector(".pin-forgot-help");
    if (help) help.hidden = false;
});
Actions.register("kiosk-pin-setup", (el) =>
    Kiosk.openPinSetup(decodeURIComponent(el.dataset.username), el.dataset.hasPin === "true")
);
Actions.register("admin-reset-pin", (el) =>
    Admin.confirmResetPin(decodeURIComponent(el.dataset.username))
);

Actions.register("admin-restock", (el) => Admin.openRestockModal(parseInt(el.dataset.id)));
Actions.register("admin-margins-period", (el) => Admin.renderMargins(el.dataset.period));
Actions.register("admin-audit-filter", (el) => Admin.renderAuditRows(el.value));
Actions.register("admin-backup-now", () => Admin.backupNow());
Actions.register("admin-backup-download", (el) => Admin.downloadBackup(el.dataset.name));
