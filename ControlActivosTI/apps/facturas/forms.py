from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.activos.models import Activo
from apps.catalogos.models import Empresa
from apps.proveedores.models import Proveedor

from .models import FacturaCompra, normalizar_numero_factura
from .services import validar_y_optimizar_pdf


BASE_CLASS = (
    "w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-900 "
    "shadow-sm outline-none transition duration-200 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-100"
)
FILE_CLASS = (
    "block w-full text-sm text-slate-700 file:mr-4 file:rounded-lg file:border-0 "
    "file:bg-cyan-600 file:px-4 file:py-2 file:font-semibold file:text-white hover:file:bg-cyan-700"
)


class FacturaCompraForm(forms.ModelForm):
    class Meta:
        model = FacturaCompra
        fields = ("proveedor", "empresa", "numero_factura", "fecha_emision", "archivo", "observaciones")
        widgets = {
            "fecha_emision": forms.DateInput(attrs={"type": "date"}),
            "observaciones": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        es_edicion = bool(self.instance and self.instance.pk)
        proveedor_actual = self.instance.proveedor_id if es_edicion else None
        empresa_actual = self.instance.empresa_id if es_edicion else None
        filtro_proveedor = Q(activo=True) | Q(pk=proveedor_actual)
        filtro_empresa = Q(activo=True) | Q(pk=empresa_actual)
        self.fields["proveedor"].queryset = Proveedor.objects.filter(filtro_proveedor).order_by("razon_social")
        self.fields["empresa"].queryset = Empresa.objects.filter(filtro_empresa).order_by("nombre")
        self.fields["archivo"].required = not es_edicion
        if es_edicion:
            self.fields.pop("archivo")
        for campo in self.fields.values():
            campo.widget.attrs["class"] = FILE_CLASS if isinstance(campo.widget, forms.ClearableFileInput) else BASE_CLASS
        if "archivo" in self.fields:
            max_mb = int(getattr(settings, "FACTURAS_PDF_MAX_SIZE", 15 * 1024 * 1024)) / (1024 * 1024)
            self.fields["archivo"].widget.attrs["accept"] = "application/pdf,.pdf"
            self.fields["archivo"].help_text = f"Solo PDF valido. Tamano maximo: {max_mb:g} MB."
        self._pdf_procesado = None

    def clean_archivo(self):
        archivo = self.cleaned_data.get("archivo")
        if not archivo:
            return archivo
        try:
            self._pdf_procesado = validar_y_optimizar_pdf(archivo)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages) from exc
        duplicada = FacturaCompra.objects.filter(
            checksum_sha256=self._pdf_procesado.checksum_sha256,
            proveedor=self.data.get("proveedor") or None,
            empresa=self.data.get("empresa") or None,
        ).first()
        if duplicada:
            raise forms.ValidationError(
                f"Este mismo documento ya fue registrado como factura {duplicada.numero_factura}."
            )
        return archivo

    def clean(self):
        cleaned = super().clean()
        proveedor = cleaned.get("proveedor")
        empresa = cleaned.get("empresa")
        numero = normalizar_numero_factura(cleaned.get("numero_factura"))
        if proveedor and empresa and numero:
            duplicadas = FacturaCompra.objects.filter(
                proveedor=proveedor, empresa=empresa, numero_factura=numero
            )
            if self.instance.pk:
                duplicadas = duplicadas.exclude(pk=self.instance.pk)
            if duplicadas.exists():
                self.add_error(
                    "numero_factura",
                    "Ya existe una factura con este numero para el proveedor y la empresa seleccionados.",
                )
        if proveedor and not proveedor.activo and proveedor.pk != getattr(self.instance, "proveedor_id", None):
            self.add_error("proveedor", "El proveedor seleccionado esta inactivo.")
        return cleaned

    def save(self, commit=True):
        factura = super().save(commit=False)
        if self._pdf_procesado:
            pdf = self._pdf_procesado
            factura.archivo = pdf.archivo
            factura.nombre_original = pdf.nombre_original
            factura.tamano_original = pdf.tamano_original
            factura.tamano_almacenado = pdf.tamano_almacenado
            factura.checksum_sha256 = pdf.checksum_sha256
            factura.numero_paginas = pdf.paginas
            factura.estado_compresion = pdf.estado_compresion
        if not factura.pk and self.user:
            factura.cargado_por = self.user
        if commit:
            factura.save()
        return factura


class AsociarActivosForm(forms.Form):
    activos = forms.ModelMultipleChoiceField(
        queryset=Activo.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Activos compatibles",
    )

    def __init__(self, *args, factura, **kwargs):
        self.factura = factura
        super().__init__(*args, **kwargs)
        self.fields["activos"].queryset = Activo.objects.filter(
            Q(factura_compra__isnull=True) | Q(factura_compra=factura),
            Q(proveedor__isnull=True) | Q(proveedor=factura.proveedor),
            Q(empresa__isnull=True) | Q(empresa=factura.empresa),
        ).select_related(
            "tipo_activo", "estado_activo", "proveedor", "empresa", "factura_compra"
        ).order_by("codigo")
        self.fields["activos"].initial = factura.activos.values_list("pk", flat=True)


class ReemplazarDocumentoForm(forms.Form):
    archivo = forms.FileField(widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf", "class": FILE_CLASS}))
    motivo = forms.CharField(widget=forms.Textarea(attrs={"rows": 4, "class": BASE_CLASS}), min_length=8)

    def clean_archivo(self):
        archivo = self.cleaned_data["archivo"]
        try:
            self.pdf_procesado = validar_y_optimizar_pdf(archivo)
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages) from exc
        return archivo
