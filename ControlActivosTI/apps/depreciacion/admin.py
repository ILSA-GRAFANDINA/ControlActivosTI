from django.contrib import admin

from .models import ConfiguracionAlertasDepreciacion, EventoNotificacionDepreciacion


@admin.register(ConfiguracionAlertasDepreciacion)
class ConfiguracionAlertasDepreciacionAdmin(admin.ModelAdmin):
    list_display = (
        "alerta_previa_meses",
        "frecuencia_recordatorio_meses",
        "mostrar_valor_residual",
        "updated_at",
    )

    def has_add_permission(self, request):
        return not ConfiguracionAlertasDepreciacion.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EventoNotificacionDepreciacion)
class EventoNotificacionDepreciacionAdmin(admin.ModelAdmin):
    list_display = (
        "activo",
        "tipo",
        "fecha_programada",
        "destinatarios",
        "omitido",
        "created_at",
    )
    list_filter = ("tipo", "omitido", "fecha_programada")
    search_fields = ("activo__codigo",)
    readonly_fields = tuple(
        field.name for field in EventoNotificacionDepreciacion._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
