from django.contrib import admin
from .models import (
    Asignacion,
    AsignacionDetalle,
    Devolucion,
    DevolucionDetalle,
    EvidenciaDevolucion,
    EvidenciaEntrega,
)


class EvidenciaEntregaInline(admin.TabularInline):
    model = EvidenciaEntrega
    extra = 0
    fields = ("imagen", "descripcion", "orden", "created_at")
    readonly_fields = ("created_at",)


class EvidenciaDevolucionInline(admin.TabularInline):
    model = EvidenciaDevolucion
    extra = 0
    fields = ("imagen", "descripcion", "orden", "created_at")
    readonly_fields = ("created_at",)


class AsignacionDetalleInline(admin.TabularInline):
    model = AsignacionDetalle
    extra = 0
    fields = (
        "activo",
        "orden",
        "activa",
        "estado_activo_devolucion",
        "observaciones_linea",
        "observaciones_devolucion",
    )
    raw_id_fields = ("activo", "estado_activo_devolucion")


@admin.register(Asignacion)
class AsignacionAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_asignacion",
        "colaborador",
        "mostrar_ceco",
        "estado_asignacion",
        "fecha_asignacion",
        "mostrar_total_activos",
        "mostrar_activos",
        "usuario_responsable",
        "fecha_devolucion",
    )
    list_filter = (
        "estado_asignacion",
        "fecha_asignacion",
        "fecha_devolucion",
        "centro_costo",
    )
    search_fields = (
        "codigo_asignacion",
        "colaborador__nombres",
        "colaborador__apellidos",
        "colaborador__cedula",
        "centro_costo_codigo",
        "centro_costo_nombre",
        "detalles__activo__codigo",
        "detalles__activo__serie",
    )
    readonly_fields = (
        "codigo_asignacion",
        "centro_costo",
        "centro_costo_codigo",
        "centro_costo_nombre",
        "centro_costo_empresa",
        "mostrar_ceco",
        "created_at",
        "updated_at",
    )
    list_select_related = ("colaborador", "centro_costo", "usuario_responsable", "usuario_recepcion")
    inlines = [AsignacionDetalleInline, EvidenciaEntregaInline]

    fieldsets = (
        (
            "Asignacion",
            {
                "fields": (
                    "codigo_asignacion",
                    "colaborador",
                    "fecha_asignacion",
                    "usuario_responsable",
                    "estado_asignacion",
                    "observaciones_entrega",
                )
            },
        ),
        (
            "CECO historico",
            {
                "fields": (
                    "mostrar_ceco",
                    "centro_costo",
                    "centro_costo_codigo",
                    "centro_costo_nombre",
                    "centro_costo_empresa",
                )
            },
        ),
        (
            "Devolucion",
            {
                "fields": (
                    "fecha_devolucion",
                    "usuario_recepcion",
                    "observaciones_devolucion",
                )
            },
        ),
        (
            "Auditoria",
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Total activos")
    def mostrar_total_activos(self, obj):
        return obj.total_activos

    @admin.display(description="Activos")
    def mostrar_activos(self, obj):
        return obj.resumen_activos or "-"

    @admin.display(description="CECO")
    def mostrar_ceco(self, obj):
        return obj.centro_costo_snapshot


@admin.register(AsignacionDetalle)
class AsignacionDetalleAdmin(admin.ModelAdmin):
    list_display = (
        "asignacion",
        "activo",
        "orden",
        "activa",
        "estado_activo_devolucion",
        "updated_at",
    )
    list_filter = (
        "activa",
        "estado_activo_devolucion",
    )
    search_fields = (
        "asignacion__codigo_asignacion",
        "activo__codigo",
        "activo__serie",
        "activo__modelo",
    )
    raw_id_fields = (
        "asignacion",
        "activo",
        "estado_activo_devolucion",
    )


class DevolucionDetalleInline(admin.TabularInline):
    model = DevolucionDetalle
    extra = 0
    fields = ("detalle_asignacion", "estado_activo_devolucion", "observaciones")
    raw_id_fields = ("detalle_asignacion", "estado_activo_devolucion")


@admin.register(Devolucion)
class DevolucionAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_devolucion",
        "asignacion",
        "fecha_devolucion",
        "usuario_recepcion",
        "updated_at",
    )
    list_filter = ("fecha_devolucion",)
    search_fields = (
        "codigo_devolucion",
        "asignacion__codigo_asignacion",
        "asignacion__colaborador__nombres",
        "asignacion__colaborador__apellidos",
        "detalles__detalle_asignacion__activo__codigo",
    )
    readonly_fields = ("codigo_devolucion", "created_at", "updated_at")
    raw_id_fields = ("asignacion", "usuario_recepcion")
    inlines = [DevolucionDetalleInline, EvidenciaDevolucionInline]


@admin.register(DevolucionDetalle)
class DevolucionDetalleAdmin(admin.ModelAdmin):
    list_display = (
        "devolucion",
        "detalle_asignacion",
        "estado_activo_devolucion",
        "updated_at",
    )
    list_filter = ("estado_activo_devolucion",)
    search_fields = (
        "devolucion__codigo_devolucion",
        "detalle_asignacion__asignacion__codigo_asignacion",
        "detalle_asignacion__activo__codigo",
    )
    raw_id_fields = ("devolucion", "detalle_asignacion", "estado_activo_devolucion")
