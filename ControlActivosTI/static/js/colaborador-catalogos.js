(() => {
    const dialog = document.querySelector("[data-catalogo-dialog]");
    if (!dialog) {
        return;
    }

    const form = dialog.querySelector("[data-catalogo-form]");
    const title = dialog.querySelector("[data-catalogo-titulo]");
    const catalogType = dialog.querySelector("[data-catalogo-tipo]");
    const codeField = dialog.querySelector("[data-catalogo-codigo]");
    const codeInput = codeField.querySelector("input");
    const companyField = dialog.querySelector("[data-catalogo-empresa]");
    const companySelect = companyField.querySelector("select");
    const errorBox = dialog.querySelector("[data-catalogo-errors]");
    const saveButton = dialog.querySelector("[data-catalogo-guardar]");

    const catalogLabels = {
        empresa: "empresa",
        cargo: "cargo",
        area: "área",
        ubicacion: "ubicación",
        centro_costo: "centro de costo",
    };

    const resetErrors = () => {
        errorBox.hidden = true;
        errorBox.replaceChildren();
    };

    const openDialog = (catalog) => {
        form.reset();
        resetErrors();
        catalogType.value = catalog;
        title.textContent = `Agregar ${catalogLabels[catalog]}`;
        const isCostCenter = catalog === "centro_costo";
        codeField.hidden = !isCostCenter;
        companyField.hidden = !isCostCenter;
        codeInput.required = isCostCenter;
        dialog.showModal();
        window.setTimeout(() => {
            (isCostCenter ? codeInput : form.elements.nombre).focus();
        }, 0);
    };

    const addOption = (select, id, label, selected = false) => {
        let option = Array.from(select.options).find((item) => item.value === String(id));
        if (!option) {
            option = new Option(label, id);
            select.add(option);
        }
        if (selected) {
            select.value = String(id);
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }
    };

    const showErrors = (errors) => {
        const list = document.createElement("ul");
        list.className = "list-disc space-y-1 pl-5";
        Object.values(errors || {}).flat().forEach((message) => {
            const item = document.createElement("li");
            item.textContent = message;
            list.append(item);
        });
        if (!list.children.length) {
            const item = document.createElement("li");
            item.textContent = "No se pudo guardar. Revisa la información e inténtalo nuevamente.";
            list.append(item);
        }
        errorBox.replaceChildren(list);
        errorBox.hidden = false;
    };

    document.querySelectorAll("[data-catalogo-rapido]").forEach((button) => {
        button.addEventListener("click", () => openDialog(button.dataset.catalogoRapido));
    });

    dialog.querySelectorAll("[data-catalogo-cerrar]").forEach((button) => {
        button.addEventListener("click", () => dialog.close());
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        resetErrors();
        saveButton.disabled = true;
        const originalText = saveButton.textContent;
        saveButton.textContent = "Guardando...";

        try {
            const response = await fetch(dialog.dataset.endpoint, {
                method: "POST",
                body: new FormData(form),
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                showErrors(data.errors);
                return;
            }

            const targetSelect = document.getElementById(`id_${data.catalogo}`);
            if (targetSelect) {
                addOption(targetSelect, data.id, data.label, true);
            }
            if (data.catalogo === "empresa") {
                addOption(companySelect, data.id, data.label);
            }

            dialog.close();
            window.showAppToast?.(
                `${data.catalogo_label} creado y seleccionado correctamente.`,
                "success",
            );
        } catch (error) {
            showErrors({
                general: ["No fue posible conectar con el servidor. Inténtalo nuevamente."],
            });
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = originalText;
        }
    });
})();
