from django.contrib import admin

from .models import Proveedor


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("identificacion", "razon_social", "nombre_comercial", "nombre_contacto", "pais", "activo")
    search_fields = ("identificacion", "razon_social", "nombre_comercial", "nombre_contacto")
    list_filter = ("activo", "tipo_proveedor", "tipo_identificacion", "pais")
    readonly_fields = ("created_at", "updated_at")
