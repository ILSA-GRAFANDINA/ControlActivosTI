from django import forms
from django.db import transaction
from django.forms import inlineformset_factory
from django.utils import timezone

from apps.activos.models import Activo
from apps.catalogos.models import EstadoActivo
from apps.colaboradores.models import Colaborador

from .models import Asignacion, AsignacionDetalle, Devolucion, DevolucionDetalle


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


def get_activos_asignables_queryset():
    queryset = (
        Activo.objects.select_related("tipo_activo", "estado_activo")
        .filter(activo=True, estado_activo__activo=True)
        .prefetch_related("valores_atributos__atributo", "valores_atributos__valor_opcion")
        .order_by("codigo")
    )
    return queryset


class ActivoSelectMultiple(forms.SelectMultiple):
    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        activo = getattr(value, "instance", None)
        if activo:
            option["attrs"].update(
                {
                    "data-search": self._build_search_value(activo),
                    "data-codigo": activo.codigo,
                    "data-codigo-sap": activo.codigo_sap or "",
                    "data-tipo": activo.tipo_activo.nombre,
                    "data-marca-modelo": f"{activo.marca} {activo.modelo}".strip(),
                    "data-serie": activo.serie or "S/N",
                    "data-especificaciones": self._build_specs_value(activo),
                    "data-estado": activo.estado_activo.nombre,
                }
            )
        return option

    def _build_search_value(self, activo):
        from apps.activos.attribute_services import valores_visibles
        valores_dinamicos = [valor.valor_formateado for _config, valor in valores_visibles(activo)]
        valores = [
            activo.codigo,
            activo.codigo_sap,
            activo.tipo_activo.nombre,
            activo.marca,
            activo.modelo,
            activo.serie,
            activo.cpu,
            activo.ram,
            activo.disco,
            activo.sistema_operativo,
            activo.estado_activo.nombre,
            activo.observaciones,
            *valores_dinamicos,
        ]
        return " ".join(valor.strip() for valor in valores if valor).lower()

    def _build_specs_value(self, activo):
        from apps.activos.attribute_services import valores_visibles
        dinamicos = [
            f"{config.atributo.nombre}: {valor.valor_formateado}"
            for config, valor in valores_visibles(activo)
        ]
        if dinamicos:
            return " | ".join(dinamicos)
        specs = []
        if activo.cpu:
            specs.append(f"CPU: {activo.cpu}")
        if activo.ram:
            specs.append(f"RAM: {activo.ram}")
        if activo.disco:
            specs.append(f"Disco: {activo.disco}")
        if activo.sistema_operativo:
            specs.append(f"SO: {activo.sistema_operativo}")
        return " | ".join(specs) if specs else "Sin especificaciones registradas"


class ActivoMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        partes = [
            obj.codigo,
            obj.tipo_activo.nombre,
            f"{obj.marca} {obj.modelo}".strip(),
            f"Serie: {obj.serie or 'S/N'}",
        ]

        from apps.activos.attribute_services import valores_visibles
        specs = [
            f"{config.atributo.nombre}: {valor.valor_formateado}"
            for config, valor in valores_visibles(obj)
        ]
        if not specs and obj.cpu:
            specs.append(f"CPU: {obj.cpu}")
        if not specs and obj.ram:
            specs.append(f"RAM: {obj.ram}")
        if not specs and obj.disco:
            specs.append(f"Disco: {obj.disco}")
        if specs:
            partes.append(" | ".join(specs))

        partes.append(f"Estado: {obj.estado_activo.nombre}")
        return " | ".join(partes)


class ColaboradorSelect(forms.Select):
    """Expone metadatos para el buscador accesible de colaboradores."""

    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        colaborador = getattr(value, "instance", None)
        if colaborador:
            empresa = colaborador.empresa.nombre if colaborador.empresa else "Sin empresa"
            ubicacion = colaborador.ubicacion.nombre if colaborador.ubicacion else "Sin ubicación"
            ceco = str(colaborador.centro_costo) if colaborador.centro_costo else "Sin CECO"
            searchable = [
                colaborador.nombres,
                colaborador.apellidos,
                colaborador.cedula,
                colaborador.correo_corporativo,
                empresa,
                colaborador.area.nombre,
                colaborador.cargo.nombre,
                ubicacion,
                ceco,
            ]
            option["attrs"].update(
                {
                    "data-search": " ".join(str(value) for value in searchable if value),
                    "data-nombre": f"{colaborador.apellidos}, {colaborador.nombres}",
                    "data-cedula": colaborador.cedula,
                    "data-correo": colaborador.correo_corporativo,
                    "data-empresa": empresa,
                    "data-area": colaborador.area.nombre,
                    "data-cargo": colaborador.cargo.nombre,
                    "data-ubicacion": ubicacion,
                    "data-ceco": ceco,
                }
            )
        return option


class AsignacionCreateForm(forms.ModelForm):
    activos = ActivoMultipleChoiceField(
        queryset=Activo.objects.none(),
        widget=ActivoSelectMultiple(
            attrs={
                "size": 10,
                "data-role": "activo-select",
            }
        ),
        label="Activos",
    )

    class Meta:
        model = Asignacion
        fields = [
            "colaborador",
            "fecha_asignacion",
            "observaciones_entrega",
            "activos",
        ]
        widgets = {
            "colaborador": ColaboradorSelect(attrs={"data-role": "colaborador-select"}),
            "fecha_asignacion": forms.DateInput(attrs={"type": "date"}),
            "observaciones_entrega": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["colaborador"].queryset = (
            Colaborador.objects.select_related(
                "area",
                "cargo",
                "centro_costo",
                "centro_costo__empresa",
                "empresa",
                "ubicacion",
            )
            .filter(estado=Colaborador.EstadoColaborador.ACTIVO)
            .order_by("apellidos", "nombres")
        )
        self.fields["activos"].queryset = get_activos_asignables_queryset()
        self.fields["fecha_asignacion"].initial = timezone.localdate()

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = TEXTAREA_CLASS
            else:
                field.widget.attrs["class"] = BASE_CLASS
            if name == "activos":
                field.help_text = "Usa el buscador y selecciona uno o varios activos con los checks."

    def clean_activos(self):
        activos = self.cleaned_data.get("activos")
        if not activos:
            raise forms.ValidationError("Debes seleccionar al menos un activo.")

        no_asignables = [
            activo
            for activo in activos
            if not activo.activo or not activo.estado_activo.es_asignable_para_nueva_asignacion
        ]
        if no_asignables:
            codigos = ", ".join(activo.codigo for activo in no_asignables)
            raise forms.ValidationError(
                f"No puedes asignar los activos seleccionados porque no están disponibles o deshabilitados: {codigos}."
            )
        return activos

    def clean_colaborador(self):
        colaborador = self.cleaned_data["colaborador"]
        ceco = colaborador.centro_costo

        if not ceco:
            raise forms.ValidationError("El colaborador debe tener un CECO vigente antes de asignar activos.")

        if not ceco.activo or not ceco.acepta_asignaciones:
            raise forms.ValidationError("El CECO del colaborador no esta habilitado para asignaciones.")

        return colaborador

    def save(self, commit=True):
        if not commit:
            raise ValueError("AsignacionCreateForm requiere commit=True.")

        activos = list(self.cleaned_data.pop("activos"))

        with transaction.atomic():
            asignacion = super().save(commit=True)
            for orden, activo in enumerate(activos, start=1):
                AsignacionDetalle.objects.create(
                    asignacion=asignacion,
                    activo=activo,
                    orden=orden,
                )
        return asignacion


class DevolucionForm(forms.ModelForm):
    class Meta:
        model = Devolucion
        fields = [
            "fecha_devolucion",
            "observaciones",
        ]
        widgets = {
            "fecha_devolucion": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        self.asignacion = kwargs.pop("asignacion")
        super().__init__(*args, **kwargs)
        self.fields["fecha_devolucion"].initial = timezone.localdate()
        self.fields["fecha_devolucion"].widget.attrs["class"] = BASE_CLASS
        self.fields["observaciones"].widget.attrs["class"] = TEXTAREA_CLASS

    def clean_fecha_devolucion(self):
        fecha_devolucion = self.cleaned_data["fecha_devolucion"]
        if self.asignacion.fecha_asignacion and fecha_devolucion < self.asignacion.fecha_asignacion:
            raise forms.ValidationError(
                "La fecha de devolución no puede ser anterior a la fecha de asignación."
            )
        return fecha_devolucion


class AsignacionDetalleDevolucionForm(forms.ModelForm):
    devolver = forms.BooleanField(required=False)

    class Meta:
        model = AsignacionDetalle
        fields = ["estado_activo_devolucion", "observaciones_devolucion"]
        widgets = {
            "observaciones_devolucion": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado_activo_devolucion"].queryset = (
            EstadoActivo.objects.filter(activo=True)
            .exclude(nombre__iexact="Asignado")
            .order_by("nombre")
        )
        self.fields["estado_activo_devolucion"].required = False
        self.fields["devolver"].widget.attrs["class"] = "h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-500"
        self.fields["estado_activo_devolucion"].widget.attrs["class"] = BASE_CLASS
        self.fields["observaciones_devolucion"].widget.attrs["class"] = TEXTAREA_CLASS

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("devolver") and not cleaned_data.get("estado_activo_devolucion"):
            self.add_error("estado_activo_devolucion", "Debes indicar el estado final del activo.")
        return cleaned_data

    def _post_clean(self):
        # Este formulario no edita el detalle original; solo captura que lineas
        # se recibiran en un evento de devolucion.
        return None

    def save_devolucion_detalle(self, devolucion):
        if not self.cleaned_data.get("devolver"):
            return None
        return DevolucionDetalle.objects.create(
            devolucion=devolucion,
            detalle_asignacion=self.instance,
            estado_activo_devolucion=self.cleaned_data["estado_activo_devolucion"],
            observaciones=self.cleaned_data.get("observaciones_devolucion", ""),
        )


AsignacionDetalleDevolucionFormSet = inlineformset_factory(
    Asignacion,
    AsignacionDetalle,
    form=AsignacionDetalleDevolucionForm,
    extra=0,
    can_delete=False,
)
