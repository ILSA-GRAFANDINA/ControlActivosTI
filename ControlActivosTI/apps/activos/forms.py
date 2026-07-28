from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory
from pathlib import Path
from django.db.models import Q

from apps.proveedores.models import Proveedor
from apps.facturas.models import FacturaCompra
from apps.catalogos.models import EstadoActivo

from .models import (
    Activo,
    EventoActivo,
    FotoActivo,
    TIPOS_ACTIVO_CON_ESPECIFICACIONES,
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
        permitir_cambio_vigencia = kwargs.pop("permitir_cambio_vigencia", True)
        super().__init__(*args, **kwargs)
        for nombre_campo in self.campos_tecnicos:
            self.fields[nombre_campo].required = False

        etiquetas = {
            "tipo_activo": "Tipo de activo",
            "empresa": "Empresa",
            "proveedor": "Proveedor de adquisicion",
            "factura_compra": "Factura de compra",
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
        ayuda_codigo_sap = "Opcional por ahora. Si lo ingresas, debe ser unico."

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
                format="%Y-%m-%d",
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

        if "estado_activo" in self.fields:
            estado_actual_id = (
                self.instance.estado_activo_id
                if self.instance and self.instance.pk
                else None
            )
            estados = EstadoActivo.objects.filter(activo=True)
            if estado_actual_id:
                estados = EstadoActivo.objects.filter(
                    Q(activo=True) | Q(pk=estado_actual_id)
                )
            self.fields["estado_activo"].queryset = estados.order_by("nombre")
            self.fields["estado_activo"].help_text = (
                "“Dado de baja” mantiene el activo visible, pero impide nuevas asignaciones."
            )

        if "proveedor" in self.fields:
            proveedor_actual_id = self.instance.proveedor_id if self.instance and self.instance.pk else None
            filtro = Q(activo=True)
            if proveedor_actual_id:
                filtro |= Q(pk=proveedor_actual_id)
            self.fields["proveedor"].queryset = Proveedor.objects.filter(filtro).order_by("razon_social")
            self.fields["proveedor"].required = False
            self.fields["proveedor"].help_text = "Opcional. En altas solo se muestran proveedores activos."

        if "factura_compra" in self.fields:
            factura_actual_id = self.instance.factura_compra_id if self.instance and self.instance.pk else None
            proveedor_id = self.data.get("proveedor") or getattr(self.instance, "proveedor_id", None)
            empresa_id = self.data.get("empresa") or getattr(self.instance, "empresa_id", None)
            filtro_factura = Q(activa=True)
            if factura_actual_id:
                filtro_factura |= Q(pk=factura_actual_id)
            facturas = FacturaCompra.objects.filter(filtro_factura).select_related("proveedor", "empresa")
            if str(proveedor_id or "").isdigit():
                facturas = facturas.filter(proveedor_id=proveedor_id)
            if str(empresa_id or "").isdigit():
                facturas = facturas.filter(empresa_id=empresa_id)
            self.fields["factura_compra"].queryset = facturas.order_by("-fecha_emision", "numero_factura")
            self.fields["factura_compra"].required = False
            self.fields["factura_compra"].help_text = "Opcional. Solo se muestran facturas compatibles con proveedor y empresa."

        if not permitir_cambio_vigencia:
            self.fields.pop("activo", None)

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
        if codigo_sap:
            cleaned_data["codigo_sap"] = codigo_sap.upper()
        else:
            cleaned_data["codigo_sap"] = None

        proveedor = cleaned_data.get("proveedor")
        proveedor_actual_id = self.instance.proveedor_id if self.instance and self.instance.pk else None
        if proveedor and not proveedor.activo and proveedor.pk != proveedor_actual_id:
            self.add_error("proveedor", "El proveedor seleccionado esta inactivo.")

        factura = cleaned_data.get("factura_compra")
        empresa = cleaned_data.get("empresa")
        factura_actual_id = self.instance.factura_compra_id if self.instance and self.instance.pk else None
        if factura:
            if not factura.activa and factura.pk != factura_actual_id:
                self.add_error("factura_compra", "La factura seleccionada esta archivada.")
            if proveedor and factura.proveedor_id != proveedor.pk:
                self.add_error("factura_compra", "La factura no corresponde al proveedor seleccionado.")
            if empresa and factura.empresa_id != empresa.pk:
                self.add_error("factura_compra", "La factura no corresponde a la empresa seleccionada.")
            if not proveedor:
                cleaned_data["proveedor"] = factura.proveedor
            if not empresa:
                cleaned_data["empresa"] = factura.empresa

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

        if "nuevo_estado_activo" in self.fields:
            self.fields["nuevo_estado_activo"].queryset = (
                EstadoActivo.objects.filter(activo=True)
                .order_by("nombre")
            )

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
                "Opcional. Úsalo si el evento deja el activo en otro estado operativo, "
                "por ejemplo Mantenimiento o Dado de baja."
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
