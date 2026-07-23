(() => {
    const root = document.querySelector("[data-admin2-search]");
    if (!root) {
        return;
    }

    const input = root.querySelector("[data-admin2-search-input]");
    const clearButton = root.querySelector("[data-admin2-search-clear]");
    const resultsContainer = root.querySelector("[data-admin2-search-results]");
    const status = root.querySelector("[data-admin2-search-status]");
    const emptyState = root.querySelector("[data-admin2-search-empty]");

    const normalize = (value) => (
        (value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLocaleLowerCase("es")
            .replace(/\s+/g, " ")
            .trim()
    );

    const sources = Array.from(document.querySelectorAll("[data-admin2-search-source]"))
        .map((element) => {
            const titleElement = element.querySelector(":scope > strong");
            const descriptionElement = element.querySelector(":scope > p");
            const title = titleElement?.textContent.trim() || "";
            const description = descriptionElement?.textContent.trim() || "";
            const group = element.dataset.searchGroup || "";
            const kind = element.dataset.searchKind || "";
            return {
                title,
                description,
                group,
                kind,
                url: element.getAttribute("href") || "#",
                searchable: normalize([title, description, group, kind].join(" ")),
                normalizedTitle: normalize(title),
                normalizedGroup: normalize(group),
            };
        })
        .filter((item) => item.title && item.url);

    const clearResults = () => {
        resultsContainer.replaceChildren();
        resultsContainer.hidden = true;
        emptyState.hidden = true;
    };

    const resultIcon = (title) => {
        const words = title.split(/\s+/).filter(Boolean);
        return words.slice(0, 2).map((word) => word[0]).join("").toLocaleUpperCase("es");
    };

    const buildResult = (item) => {
        const link = document.createElement("a");
        link.href = item.url;
        link.className = "admin2-search-result";
        link.setAttribute("role", "listitem");

        const icon = document.createElement("span");
        icon.className = "admin2-search-result__icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = resultIcon(item.title);

        const copy = document.createElement("span");
        copy.className = "admin2-search-result__copy";

        const title = document.createElement("strong");
        title.textContent = item.title;

        const description = document.createElement("span");
        description.textContent = item.description;

        copy.append(title, description);

        const group = document.createElement("span");
        group.className = "admin2-search-result__group";
        group.textContent = item.group.split(" ").slice(0, 3).join(" ");

        const arrow = document.createElement("span");
        arrow.className = "admin2-search-result__arrow";
        arrow.setAttribute("aria-hidden", "true");
        arrow.textContent = "→";

        link.append(icon, copy, group, arrow);
        return link;
    };

    const search = () => {
        const rawQuery = input.value.trim();
        const query = normalize(rawQuery);
        clearButton.hidden = !rawQuery;

        if (!query) {
            clearResults();
            status.textContent = "Escribe para encontrar rápidamente el acceso que necesitas.";
            return;
        }

        const terms = query.split(" ").filter(Boolean);
        const matches = sources
            .filter((item) => terms.every((term) => item.searchable.includes(term)))
            .map((item) => {
                let score = 0;
                if (item.normalizedTitle === query) score += 120;
                if (item.normalizedTitle.startsWith(query)) score += 90;
                else if (item.normalizedTitle.includes(query)) score += 65;
                if (item.normalizedGroup.startsWith(query)) score += 40;
                terms.forEach((term) => {
                    if (item.normalizedTitle.startsWith(term)) score += 20;
                    else if (item.normalizedTitle.includes(term)) score += 10;
                    if (item.normalizedGroup.includes(term)) score += 5;
                });
                return { ...item, score };
            })
            .sort((left, right) => (
                right.score - left.score
                || left.title.localeCompare(right.title, "es", { sensitivity: "base" })
            ))
            .slice(0, 10);

        resultsContainer.replaceChildren(...matches.map(buildResult));
        resultsContainer.hidden = matches.length === 0;
        emptyState.hidden = matches.length !== 0;
        status.textContent = matches.length
            ? `${matches.length} resultado${matches.length === 1 ? "" : "s"} para “${rawQuery}”.`
            : `No hay resultados para “${rawQuery}”.`;
    };

    const reset = () => {
        input.value = "";
        clearButton.hidden = true;
        clearResults();
        status.textContent = "Escribe para encontrar rápidamente el acceso que necesitas.";
        input.focus();
    };

    input.addEventListener("input", search);
    clearButton.addEventListener("click", reset);
    input.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
            const firstResult = resultsContainer.querySelector("a");
            if (firstResult) {
                event.preventDefault();
                firstResult.focus();
            }
        } else if (event.key === "Escape" && input.value) {
            event.preventDefault();
            reset();
        }
    });

    document.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase("es") === "k") {
            event.preventDefault();
            input.focus();
            input.select();
        }
    });
})();
