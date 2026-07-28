from django import forms

from .models import ConfiguracionAlertasDepreciacion


class ConfiguracionAlertasForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionAlertasDepreciacion
        fields = (
            "alerta_previa_meses",
            "frecuencia_recordatorio_meses",
            "mostrar_valor_residual",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (
                    "h-5 w-5 rounded border-slate-300 text-cyan-600 "
                    "focus:ring-cyan-500"
                )
                continue
            field.widget.attrs["class"] = (
                "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 "
                "text-sm text-slate-900 shadow-sm outline-none transition "
                "duration-200 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100"
            )
            field.widget.attrs["min"] = "0"
