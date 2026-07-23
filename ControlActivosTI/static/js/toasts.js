(() => {
    const removeToast = (toast) => {
        if (!toast || toast.classList.contains("is-leaving")) {
            return;
        }
        toast.classList.add("is-leaving");
        window.setTimeout(() => {
            const region = toast.closest("[data-toast-region]");
            toast.remove();
            if (region && !region.querySelector("[data-toast]")) {
                region.remove();
            }
        }, 230);
    };

    const activateToast = (toast) => {
        const closeButton = toast.querySelector("[data-toast-close]");
        const timeout = Number.parseInt(toast.dataset.toastTimeout || "0", 10);
        let timer = null;
        let remaining = timeout;
        let startedAt = 0;

        const startTimer = () => {
            if (remaining <= 0) {
                return;
            }
            startedAt = Date.now();
            timer = window.setTimeout(() => removeToast(toast), remaining);
        };

        const pauseTimer = () => {
            if (!timer) {
                return;
            }
            window.clearTimeout(timer);
            timer = null;
            remaining = Math.max(0, remaining - (Date.now() - startedAt));
        };

        closeButton?.addEventListener("click", () => removeToast(toast));
        toast.addEventListener("mouseenter", pauseTimer);
        toast.addEventListener("mouseleave", startTimer);
        toast.addEventListener("focusin", pauseTimer);
        toast.addEventListener("focusout", startTimer);
        startTimer();
    };

    document.querySelectorAll("[data-toast]").forEach(activateToast);

    window.showAppToast = (message, type = "info") => {
        const allowedTypes = new Set(["success", "warning", "error", "info"]);
        const safeType = allowedTypes.has(type) ? type : "info";
        let region = document.querySelector("[data-toast-region]");
        if (!region) {
            region = document.createElement("section");
            region.className = "toast-region";
            region.dataset.toastRegion = "";
            region.setAttribute("aria-label", "Notificaciones");
            region.setAttribute("aria-live", "polite");
            region.setAttribute("aria-relevant", "additions removals");
            document.body.append(region);
        }

        const titles = {
            success: "Operación exitosa",
            warning: "Atención",
            error: "No se pudo completar",
            info: "Información",
        };
        const icons = { success: "✓", warning: "!", error: "×", info: "i" };
        const toast = document.createElement("article");
        toast.className = `app-toast app-toast--${safeType}`;
        toast.dataset.toast = "";
        toast.dataset.toastTimeout = "2500";
        toast.setAttribute("role", safeType === "error" || safeType === "warning" ? "alert" : "status");

        const icon = document.createElement("span");
        icon.className = "app-toast__icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = icons[safeType];

        const content = document.createElement("span");
        content.className = "app-toast__content";
        const title = document.createElement("strong");
        title.className = "app-toast__title";
        title.textContent = titles[safeType];
        const copy = document.createElement("span");
        copy.className = "app-toast__message";
        copy.textContent = message;
        content.append(title, copy);

        const close = document.createElement("button");
        close.type = "button";
        close.className = "app-toast__close";
        close.dataset.toastClose = "";
        close.setAttribute("aria-label", "Cerrar notificación");
        close.textContent = "×";

        toast.append(icon, content, close);
        region.append(toast);
        activateToast(toast);
    };
})();
