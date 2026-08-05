from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("created_at", "entidad", "objeto_id", "accion", "resumen", "usuario")
    list_filter = ("accion", "entidad", "created_at")
    search_fields = ("entidad", "objeto_id", "resumen", "usuario__username")
    readonly_fields = ("entidad", "objeto_id", "accion", "resumen", "detalle", "usuario", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
