from django.contrib import admin
from django.utils.html import format_html

from .models import Notificacion, is_safe_internal_path


class EstadoLecturaFilter(admin.SimpleListFilter):
    title = "estado de lectura"
    parameter_name = "estado_lectura"

    def lookups(self, request, model_admin):
        return (("pendiente", "No leída"), ("leida", "Leída"))

    def queryset(self, request, queryset):
        if self.value() == "pendiente":
            return queryset.filter(read_at__isnull=True)
        if self.value() == "leida":
            return queryset.filter(read_at__isnull=False)
        return queryset


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "tipo",
        "titulo",
        "destinatario",
        "actor",
        "estado_lectura",
        "objeto_relacionado",
    )
    list_filter = (
        "tipo",
        EstadoLecturaFilter,
        "destinatario",
        "actor",
        "entidad_tipo",
        "created_at",
    )
    search_fields = (
        "titulo",
        "mensaje",
        "destinatario__username",
        "destinatario__first_name",
        "destinatario__last_name",
        "actor__username",
        "actor__first_name",
        "actor__last_name",
    )
    date_hierarchy = "created_at"
    autocomplete_fields = ("destinatario", "actor")
    list_select_related = ("destinatario", "actor")
    list_per_page = 50
    ordering = ("-created_at", "-id")
    readonly_fields = tuple(field.name for field in Notificacion._meta.fields)

    @admin.display(description="Lectura", ordering="read_at", boolean=True)
    def estado_lectura(self, obj):
        return obj.read_at is not None

    @admin.display(description="Objeto relacionado")
    def objeto_relacionado(self, obj):
        label = f"{obj.get_entidad_tipo_display()} #{obj.entidad_id}" if obj.entidad_id else "-"
        if is_safe_internal_path(obj.ruta):
            return format_html('<a href="{}">{}</a>', obj.ruta, label)
        return label

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("notificaciones.view_all_notificacion")

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm(
            "notificaciones.view_all_notificacion"
        )
