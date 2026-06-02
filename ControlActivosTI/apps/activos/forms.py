from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from pathlib import Path

from .models import (
    Activo,
    EventoActivo,
    FotoActivo,
    TIPOS_ACTIVO_CON_ESPECIFICACIONES,
    tipo_activo_requiere_codigo_sap,
)


BASE_INPUT_CLASS = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 "
    "shadow-sm outline-none transition duration-200 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100"
)
CHECKBOX_CLASS = "h-5 w-5 rounded border-slate-300 text-cyan-600 focus:ring-cyan-500"
TEXTAREA_CLASS = BASE_INPUT_CLASS
FILE_INPUT_CLASS = (
    "block w-full text-sm text-slate-700 file:mr-4 file:rounded-lg file:border-0 "
    "file:bg-cyan-600 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white "
    "hover:file:bg-cyan-700"
)
FOTO_ACTIVO_MAX_FORMS = 5
FOTO_ACTIVO_INITIAL_FORMS = 2
FOTO_ACTIVO_ALLOWED_EXTENSIONS = ("jpg", "jpeg", "png", "webp")


def _widget_input_type(widget):
    if hasattr(widget, "input_type"):
        return widget.input_type
    nested_widget = getattr(widget, "widget", None)
    return getattr(nested_widget, "input_type", None)


class CommaDecimalField(forms.DecimalField):
    def to_python(self, value):
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return super().to_python(value)


class ActivoAdminForm(forms.ModelForm):
    campos_tecnicos = ("cpu", "ram", "disco", "sistema_operativo")

    class Meta:
        model = Activo
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre_campo in self.campos_tecnicos:
            self.fields[nombre_campo].required = False

        etiquetas = {
            "tipo_activo": "Tipo de activo",
            "marca": "Marca",
            "modelo": "Modelo",
            "serie": "Serie",
            "codigo_sap": "Codigo SAP",
            "cpu": "CPU",
            "ram": "RAM",
            "disco": "Disco",
            "sistema_operativo": "Sistema operativo",
            "fecha_compra": "Fecha de compra",
            "valor": "Valor de Compra",
            "estado_activo": "Estado del activo",
            "activo": "Activo en inventario",
            "observaciones": "Observaciones",
        }

        ayuda_tecnica = "Solo aplica para laptops, PC o equipos de escritorio."
        ayuda_codigo_sap = "Obligatorio para laptops y PCs. Debe ser unico."

        for nombre_campo, etiqueta in etiquetas.items():
            if nombre_campo in self.fields:
                self.fields[nombre_campo].label = etiqueta

        for nombre_campo in self.fields:
            widget = self.fields[nombre_campo].widget
            input_type = _widget_input_type(widget)
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 4)
                widget.attrs["class"] = TEXTAREA_CLASS
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = CHECKBOX_CLASS
            elif input_type == "file":
                widget.attrs["class"] = FILE_INPUT_CLASS
            else:
                widget.attrs["class"] = BASE_INPUT_CLASS

        if "fecha_compra" in self.fields:
            self.fields["fecha_compra"].widget = forms.DateInput(
                attrs={
                    "type": "date",
                    "class": BASE_INPUT_CLASS,
                }
            )
        if "valor" in self.fields:
            valor_field = self.fields["valor"]
            self.fields["valor"] = CommaDecimalField(
                max_digits=valor_field.max_digits,
                decimal_places=valor_field.decimal_places,
                required=valor_field.required,
                label="Valor de Compra",
                help_text=valor_field.help_text,
                widget=forms.TextInput(
                    attrs={
                        "class": BASE_INPUT_CLASS,
                        "inputmode": "decimal",
                        "placeholder": "Ej: 10,482.00",
                    }
                ),
            )

        self.fields["cpu"].help_text = ayuda_tecnica
        self.fields["ram"].help_text = ayuda_tecnica
        self.fields["disco"].help_text = ayuda_tecnica
        self.fields["sistema_operativo"].help_text = ayuda_tecnica
        if "valor" in self.fields:
            self.fields["valor"].help_text = (
                "Usa coma para miles y punto para decimales, por ejemplo 10,482.00."
            )
        if "codigo_sap" in self.fields:
            self.fields["codigo_sap"].help_text = ayuda_codigo_sap

    def clean(self):
        cleaned_data = super().clean()
        tipo_activo = cleaned_data.get("tipo_activo")
        nombre_tipo = (tipo_activo.nombre if tipo_activo else "").strip().lower()
        requiere_especificaciones = any(
            clave in nombre_tipo
            for clave in TIPOS_ACTIVO_CON_ESPECIFICACIONES
        )

        if not requiere_especificaciones:
            for nombre_campo in self.campos_tecnicos:
                cleaned_data[nombre_campo] = ""

        codigo_sap = (cleaned_data.get("codigo_sap") or "").strip()
        if tipo_activo_requiere_codigo_sap(nombre_tipo):
            if not codigo_sap:
                raise ValidationError({"codigo_sap": "Debes registrar el Codigo SAP para laptops y PCs."})
            cleaned_data["codigo_sap"] = codigo_sap.upper()
        else:
            cleaned_data["codigo_sap"] = None

        return cleaned_data


class FotoActivoInlineForm(forms.ModelForm):
    class Meta:
        model = FotoActivo
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre_campo in self.fields:
            widget = self.fields[nombre_campo].widget
            input_type = _widget_input_type(widget)
            if input_type == "file":
                widget.attrs["class"] = FILE_INPUT_CLASS
                widget.attrs["accept"] = "image/*,.jpg,.jpeg,.png,.webp"
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)
                widget.attrs["class"] = TEXTAREA_CLASS
            else:
                widget.attrs["class"] = BASE_INPUT_CLASS

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")
        if self.instance.pk and not imagen:
            return self.instance.imagen
        if not imagen:
            return imagen

        extension = Path(getattr(imagen, "name", "")).suffix.lower().lstrip(".")
        if extension not in FOTO_ACTIVO_ALLOWED_EXTENSIONS:
            raise ValidationError("Solo se permiten imagenes en formato JPG, JPEG, PNG o WEBP.")

        content_type = getattr(imagen, "content_type", "") or ""
        if content_type and not content_type.startswith("image/"):
            raise ValidationError("El archivo cargado debe ser una imagen valida.")

        return imagen


class EventoActivoAdminForm(forms.ModelForm):
    class Meta:
        model = EventoActivo
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        etiquetas = {
            "activo": "Activo afectado",
            "tipo_evento": "Tipo de evento",
            "fecha_evento": "Fecha del evento",
            "detalle": "Detalle del trabajo realizado",
            "campo_afectado": "Dato del activo que se actualizara",
            "valor_nuevo": "Nuevo valor final del dato seleccionado",
            "costo_adicional": "Costo del repuesto o mejora",
            "sumar_costo_al_valor": "Sumar este costo al valor del activo",
            "nuevo_estado_activo": "Estado final del activo",
            "usuario_responsable": "Responsable del registro",
        }
        ayudas = {
            "campo_afectado": (
                "Elige RAM, disco, procesador o sistema operativo solo si este evento debe "
                "modificar la ficha actual del activo."
            ),
            "valor_nuevo": (
                "No es el precio. Es el dato tecnico final que quedara en el activo, "
                "por ejemplo: 16 GB, 512 GB SSD o Windows 11."
            ),
            "costo_adicional": (
                "Usa este campo solo si se compro una pieza o mejora. Para mantenimiento "
                "o limpieza simple, dejalo vacio."
            ),
            "sumar_costo_al_valor": (
                "Activalo solo cuando el costo adicional deba aumentar el valor registrado del activo."
            ),
            "nuevo_estado_activo": (
                "Opcional. Usalo si el evento deja el activo en otro estado, por ejemplo Mantenimiento o Baja."
            ),
        }
        placeholders = {
            "valor_nuevo": "Ej: 16 GB, 1 TB SSD, Intel Core i7, Windows 11",
            "costo_adicional": "Ej: 40.00",
        }

        for nombre_campo, etiqueta in etiquetas.items():
            if nombre_campo in self.fields:
                self.fields[nombre_campo].label = etiqueta

        for nombre_campo, ayuda in ayudas.items():
            if nombre_campo in self.fields:
                self.fields[nombre_campo].help_text = ayuda

        for nombre_campo, placeholder in placeholders.items():
            if nombre_campo in self.fields:
                self.fields[nombre_campo].widget.attrs["placeholder"] = placeholder


FotoActivoCreateFormSet = modelformset_factory(
    FotoActivo,
    form=FotoActivoInlineForm,
    fields=("imagen", "descripcion", "orden"),
    extra=FOTO_ACTIVO_INITIAL_FORMS,
    max_num=FOTO_ACTIVO_MAX_FORMS,
    can_delete=False,
)
