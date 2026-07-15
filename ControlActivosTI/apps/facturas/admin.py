from django.contrib import admin

from .models import EventoFactura, FacturaCompra, ReemplazoDocumentoFactura


@admin.register(FacturaCompra)
class FacturaCompraAdmin(admin.ModelAdmin):
    list_display = ("numero_factura", "proveedor", "empresa", "fecha_emision", "activa", "tamano_almacenado")
    list_filter = ("activa", "empresa", "proveedor", "estado_compresion", "fecha_emision")
    search_fields = ("numero_factura", "proveedor__razon_social", "proveedor__identificacion")
    list_select_related = ("proveedor", "empresa", "cargado_por")
    readonly_fields = (
        "nombre_original", "tamano_original", "tamano_almacenado", "estado_compresion",
        "checksum_sha256", "numero_paginas", "cargado_por", "created_at", "updated_at",
    )


@admin.register(ReemplazoDocumentoFactura)
class ReemplazoDocumentoFacturaAdmin(admin.ModelAdmin):
    list_display = ("factura", "reemplazado_por", "created_at")
    readonly_fields = [field.name for field in ReemplazoDocumentoFactura._meta.fields]


@admin.register(EventoFactura)
class EventoFacturaAdmin(admin.ModelAdmin):
    list_display = ("numero_factura", "accion", "usuario", "created_at")
    list_filter = ("accion", "created_at")
    search_fields = ("numero_factura", "usuario__username")
    readonly_fields = [field.name for field in EventoFactura._meta.fields]
