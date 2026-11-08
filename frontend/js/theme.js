// Colour theme: "auto" follows the device (prefers-color-scheme), "light" and
// "dark" force one. Loaded in <head> so the theme applies before the first paint.
const Theme = {
    KEY: "kiosk_theme",
    MODES: ["auto", "light", "dark"],
    LABELS: { auto: "◐ Theme: Auto", light: "☀ Theme: Light", dark: "☾ Theme: Dark" },

    get() {
        let mode = null;
        try {
            mode = localStorage.getItem(this.KEY);
        } catch {}
        return this.MODES.includes(mode) ? mode : "auto";
    },

    apply(mode) {
        const root = document.documentElement;
        if (mode === "auto") delete root.dataset.theme;
        else root.dataset.theme = mode;
        const btn = document.getElementById("theme-btn");
        if (btn) {
            btn.textContent = this.LABELS[mode];
            btn.title = "Switch between automatic, light and dark colours";
        }
    },

    set(mode) {
        try {
            if (mode === "auto") localStorage.removeItem(this.KEY);
            else localStorage.setItem(this.KEY, mode);
        } catch {}
        this.apply(mode);
    },

    cycle() {
        const next = this.MODES[(this.MODES.indexOf(this.get()) + 1) % this.MODES.length];
        this.set(next);
    },
};

Theme.apply(Theme.get());
document.addEventListener("DOMContentLoaded", () => Theme.apply(Theme.get()));
