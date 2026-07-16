import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.core.files.storage import storages
from django.utils import timezone


def normalizar_numero_factura(valor):
    return re.sub(r"\s+", "", (valor or "").strip()).upper()


def ruta_factura(instance, filename):
    year = instance.fecha_emision.year if instance.fecha_emision else timezone.localdate().year
    return f"facturas/{year}/{uuid.uuid4().hex}.pdf"


def ruta_factura_historica(instance, filename):
    return f"facturas/historial/{timezone.localdate().year}/{uuid.uuid4().hex}.pdf"


def almacenamiento_facturas():
    return storages["facturas"]


class FacturaCompra(models.Model):
    class EstadoCompresion(models.TextChoices):
        COMPRIMIDO = "comprimido", "Comprimido"
        SIN_REDUCCION = "sin_reduccion", "Original ya optimizado"
        FIRMA_DIGITAL = "firma_digital", "Original conservado por firma digital"
        FALLO_COMPRESION = "fallo_compresion", "Original conservado por fallo de optimizacion"

    proveedor = models.ForeignKey(
        "proveedores.Proveedor", on_delete=models.PROTECT, related_name="facturas"
    )
    empresa = models.ForeignKey(
        "catalogos.Empresa", on_delete=models.PROTECT, related_name="facturas_compra"
    )
    numero_factura = models.CharField(max_length=80, db_index=True)
    fecha_emision = models.DateField(db_index=True)
    archivo = models.FileField(storage=almacenamiento_facturas, upload_to=ruta_factura, max_length=255)
    nombre_original = models.CharField(max_length=255, editable=False)
    tamano_original = models.PositiveBigIntegerField(default=0, editable=False)
    tamano_almacenado = models.PositiveBigIntegerField(default=0, editable=False)
    estado_compresion = models.CharField(
        max_length=24,
        choices=EstadoCompresion.choices,
        default=EstadoCompresion.SIN_REDUCCION,
        editable=False,
    )
    checksum_sha256 = models.CharField(max_length=64, db_index=True, editable=False)
    numero_paginas = models.PositiveIntegerField(default=0, editable=False)
    observaciones = models.TextField(blank=True)
    activa = models.BooleanField(default=True, db_index=True)
    cargado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="facturas_cargadas",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_emision", "-id"]
        verbose_name = "Factura de compra"
        verbose_name_plural = "Facturas de compra"
        constraints = [
            models.UniqueConstraint(
                fields=["proveedor", "numero_factura", "empresa"],
                name="factura_unica_proveedor_numero_empresa",
            )
        ]
        permissions = [
            ("associate_facturacompra", "Puede asociar o desvincular activos de facturas"),
            ("download_facturacompra", "Puede visualizar o descargar facturas"),
            ("replace_facturacompra", "Puede reemplazar el PDF de una factura"),
            ("archive_facturacompra", "Puede archivar o activar facturas"),
        ]

    def __str__(self):
        return f"{self.numero_factura} - {self.proveedor}"

    @property
    def porcentaje_reduccion(self):
        if not self.tamano_original or self.tamano_almacenado >= self.tamano_original:
            return 0
        return round((1 - self.tamano_almacenado / self.tamano_original) * 100, 1)

    def clean(self):
        super().clean()
        self.numero_factura = normalizar_numero_factura(self.numero_factura)
        errores = {}
        if not self.numero_factura:
            errores["numero_factura"] = "El numero de factura es obligatorio."
        if self.fecha_emision and self.fecha_emision > timezone.localdate():
            errores["fecha_emision"] = "La fecha de emision no puede ser futura."
        if self.pk:
            anterior = type(self).objects.filter(pk=self.pk).only("proveedor_id", "empresa_id").first()
            if anterior and self.activos.exists():
                if anterior.proveedor_id != self.proveedor_id:
                    errores["proveedor"] = "Desvincula los activos antes de cambiar el proveedor."
                if anterior.empresa_id != self.empresa_id:
                    errores["empresa"] = "Desvincula los activos antes de cambiar la empresa compradora."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.numero_factura = normalizar_numero_factura(self.numero_factura)
        self.full_clean()
        return super().save(*args, **kwargs)


class ReemplazoDocumentoFactura(models.Model):
    factura = models.ForeignKey(FacturaCompra, on_delete=models.CASCADE, related_name="reemplazos")
    archivo_anterior = models.FileField(
        storage=almacenamiento_facturas, upload_to=ruta_factura_historica, max_length=255
    )
    checksum_anterior = models.CharField(max_length=64)
    archivo_nuevo = models.CharField(max_length=255)
    checksum_nuevo = models.CharField(max_length=64)
    motivo = models.TextField()
    reemplazado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reemplazos_factura"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Reemplazo de documento de factura"
        verbose_name_plural = "Reemplazos de documentos de factura"


class EventoFactura(models.Model):
    class Accion(models.TextChoices):
        CREACION = "creacion", "Creacion"
        EDICION = "edicion", "Edicion de metadatos"
        ASOCIACION = "asociacion", "Actualizacion de activos asociados"
        REEMPLAZO = "reemplazo", "Reemplazo de documento"
        ESTADO = "estado", "Cambio de estado"
        ELIMINACION = "eliminacion", "Eliminacion"
        DESCARGA = "descarga", "Descarga de documento"

    factura = models.ForeignKey(
        FacturaCompra, on_delete=models.SET_NULL, related_name="eventos", null=True, blank=True
    )
    numero_factura = models.CharField(max_length=80)
    accion = models.CharField(max_length=20, choices=Accion.choices)
    detalle = models.JSONField(default=dict, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_factura"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Evento de factura"
        verbose_name_plural = "Eventos de facturas"
