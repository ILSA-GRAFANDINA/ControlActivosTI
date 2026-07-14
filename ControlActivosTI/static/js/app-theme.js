(() => {
    const root = document.documentElement;
    const body = document.body;
    const storageKey = "controlactivos-theme";
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const toggle = document.querySelector("[data-theme-toggle]");
    const themeColor = document.querySelector("[data-theme-color]");
    const sidebar = document.getElementById("app-sidebar");
    const sidebarOpen = document.querySelector("[data-sidebar-open]");
    const sidebarClose = document.querySelector("[data-sidebar-close]");
    const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
    const sidebarStorageKey = "controlactivos-sidebar";

    const currentTheme = () => root.classList.contains("dark") ? "dark" : "light";

    const syncThemeControls = () => {
        const dark = currentTheme() === "dark";
        root.style.colorScheme = dark ? "dark" : "light";

        if (toggle) {
            toggle.setAttribute("aria-label", dark ? "Cambiar a tema claro" : "Cambiar a tema oscuro");
            toggle.setAttribute("title", dark ? "Cambiar a tema claro" : "Cambiar a tema oscuro");
            toggle.setAttribute("aria-pressed", String(dark));
        }

        if (themeColor) {
            themeColor.setAttribute("content", dark ? "#17182d" : "#f4f6fb");
        }
    };

    const applyTheme = (theme, persist = false) => {
        root.classList.toggle("dark", theme === "dark");
        if (persist) {
            localStorage.setItem(storageKey, theme);
        }
        syncThemeControls();
        window.dispatchEvent(new CustomEvent("app:themechange", { detail: { theme } }));
    };

    toggle?.addEventListener("click", () => {
        applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
    });

    media.addEventListener?.("change", (event) => {
        if (!localStorage.getItem(storageKey)) {
            applyTheme(event.matches ? "dark" : "light");
        }
    });

    const setSidebar = (open) => {
        body.classList.toggle("sidebar-open", open);
        sidebarOpen?.setAttribute("aria-expanded", String(open));
    };

    const syncSidebarToggle = () => {
        const collapsed = root.classList.contains("sidebar-collapsed");
        sidebarToggle?.setAttribute("aria-expanded", String(!collapsed));
        sidebarToggle?.setAttribute("aria-label", collapsed ? "Expandir menú" : "Contraer menú");
        sidebarToggle?.setAttribute("title", collapsed ? "Expandir menú" : "Contraer menú");
    };

    sidebarOpen?.addEventListener("click", () => setSidebar(true));
    sidebarClose?.addEventListener("click", () => setSidebar(false));
    sidebarToggle?.addEventListener("click", () => {
        const collapsed = !root.classList.contains("sidebar-collapsed");
        root.classList.toggle("sidebar-collapsed", collapsed);
        localStorage.setItem(sidebarStorageKey, collapsed ? "collapsed" : "expanded");
        syncSidebarToggle();
    });
    sidebar?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => setSidebar(false)));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            setSidebar(false);
        }
    });

    syncThemeControls();
    syncSidebarToggle();
})();
