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

    document.querySelectorAll("[data-toast]").forEach((toast) => {
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
    });
})();
