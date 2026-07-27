(() => {
    const root = document.querySelector("[data-notification-menu]");
    const trigger = root?.querySelector("[data-notification-trigger]");
    const panel = root?.querySelector("[data-notification-panel]");
    const closeButton = root?.querySelector("[data-notification-close]");
    const badge = root?.querySelector("[data-notification-badge]");
    const markAllForm = root?.querySelector("[data-mark-all-form]");
    if (!root || !trigger || !panel || !markAllForm) return;

    let marked = false;
    const csrfToken = markAllForm.querySelector("[name=csrfmiddlewaretoken]")?.value;

    const positionPanel = () => {
        if (panel.hidden) return;
        if (!window.matchMedia("(max-width: 639px)").matches) {
            panel.style.removeProperty("top");
            panel.style.removeProperty("right");
            panel.style.removeProperty("left");
            return;
        }
        const triggerRect = trigger.getBoundingClientRect();
        panel.style.top = `${Math.round(triggerRect.bottom + 8)}px`;
        panel.style.right = "10px";
        panel.style.left = "10px";
    };

    const markAll = async () => {
        if (marked) return;
        marked = true;
        try {
            const response = await fetch(markAllForm.action, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            badge?.classList.add("is-hidden");
            trigger.setAttribute("aria-label", "Notificaciones");
            root.querySelectorAll("[data-notification-item].is-unread").forEach(
                (item) => item.classList.remove("is-unread")
            );
        } catch (_) {
            marked = false;
        }
    };

    const openPanel = () => {
        panel.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
        positionPanel();
        markAll();
        closeButton?.focus({ preventScroll: true });
    };

    const closePanel = ({ restoreFocus = false } = {}) => {
        if (panel.hidden) return;
        panel.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
        if (restoreFocus) trigger.focus({ preventScroll: true });
    };

    trigger.addEventListener("click", () => {
        if (panel.hidden) openPanel();
        else closePanel({ restoreFocus: true });
    });
    closeButton?.addEventListener("click", () => closePanel({ restoreFocus: true }));
    markAllForm.addEventListener("submit", (event) => {
        event.preventDefault();
        markAll();
    });
    document.addEventListener("pointerdown", (event) => {
        if (!panel.hidden && !root.contains(event.target) && !panel.contains(event.target)) {
            closePanel();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !panel.hidden) closePanel({ restoreFocus: true });
    });
    window.addEventListener("resize", positionPanel, { passive: true });
    window.addEventListener("scroll", positionPanel, { passive: true });
})();
