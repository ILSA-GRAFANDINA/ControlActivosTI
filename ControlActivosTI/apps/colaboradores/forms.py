from django import forms
from django.db.models import Q

from apps.catalogos.models import Area, Cargo, CentroCosto, Empresa, Ubicacion

from .models import Colaborador


BASE_CLASS = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 "
    "shadow-sm outline-none transition duration-200 "
    "focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100"
)
TEXTAREA_CLASS = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 "
    "shadow-sm outline-none transition duration-200 resize-none "
    "focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100"
)


class ColaboradorForm(forms.ModelForm):
    class Meta:
        model = Colaborador
        fields = [
            "nombres",
            "apellidos",
            "cedula",
            "correo_corporativo",
            "empresa",
            "cargo",
            "area",
            "ubicacion",
            "centro_costo",
            "estado",
            "fecha_ingreso",
            "observaciones",
        ]
        widgets = {
            "fecha_ingreso": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "observaciones": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance if self.instance and self.instance.pk else None

        def activos_o_actuales(model, field_name):
            actual_id = getattr(instance, f"{field_name}_id", None) if instance else None
            filtro = Q(activo=True)
            if actual_id:
                filtro |= Q(pk=actual_id)
            return model.objects.filter(filtro)

        self.fields["empresa"].queryset = activos_o_actuales(
            Empresa, "empresa"
        ).order_by("nombre")
        self.fields["cargo"].queryset = activos_o_actuales(
            Cargo, "cargo"
        ).order_by("nombre")
        self.fields["area"].queryset = activos_o_actuales(
            Area, "area"
        ).order_by("nombre")
        self.fields["ubicacion"].queryset = activos_o_actuales(
            Ubicacion, "ubicacion"
        ).order_by("nombre")
        self.fields["centro_costo"].queryset = (
            activos_o_actuales(CentroCosto, "centro_costo").order_by("codigo")
        )
        self.fields["estado"].initial = Colaborador.EstadoColaborador.ACTIVO

        etiquetas = {
            "nombres": "Nombres",
            "apellidos": "Apellidos",
            "cedula": "Cédula",
            "correo_corporativo": "Correo corporativo",
            "empresa": "Empresa",
            "cargo": "Cargo",
            "area": "Área",
            "ubicacion": "Ubicación",
            "centro_costo": "Centro de costo",
            "estado": "Estado",
            "fecha_ingreso": "Fecha de ingreso",
            "observaciones": "Observaciones",
        }

        for nombre_campo, etiqueta in etiquetas.items():
            if nombre_campo in self.fields:
                self.fields[nombre_campo].label = etiqueta

        for nombre_campo, field in self.fields.items():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = TEXTAREA_CLASS
            else:
                field.widget.attrs["class"] = BASE_CLASS


class CentroCostoRapidoForm(forms.ModelForm):
    codigo = forms.CharField(max_length=30)

    class Meta:
        model = CentroCosto
        fields = ["codigo", "nombre", "empresa", "descripcion"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].queryset = Empresa.objects.filter(activo=True).order_by(
            "nombre"
        )

    def clean_codigo(self):
        return self.cleaned_data["codigo"].strip().upper()


CATALOGOS_RAPIDOS = {
    "empresa": {
        "model": Empresa,
        "fields": ["nombre", "descripcion"],
        "label": "Empresa",
    },
    "cargo": {
        "model": Cargo,
        "fields": ["nombre", "descripcion"],
        "label": "Cargo",
    },
    "area": {
        "model": Area,
        "fields": ["nombre", "descripcion"],
        "label": "Área",
    },
    "ubicacion": {
        "model": Ubicacion,
        "fields": ["nombre", "descripcion"],
        "label": "Ubicación",
    },
}


def get_catalogo_rapido_form(catalogo):
    if catalogo == "centro_costo":
        return CentroCostoRapidoForm
    config = CATALOGOS_RAPIDOS.get(catalogo)
    if not config:
        return None
    return forms.modelform_factory(config["model"], fields=config["fields"])


def get_catalogo_rapido_label(catalogo):
    if catalogo == "centro_costo":
        return "Centro de costo"
    config = CATALOGOS_RAPIDOS.get(catalogo)
    return config["label"] if config else ""
