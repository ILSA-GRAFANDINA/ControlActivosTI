from django.contrib import admin
from django.utils.html import format_html

from .forms import ActivoAdminForm, EventoActivoAdminForm, FotoActivoInlineForm
from .models import Activo, EventoActivo, FotoActivo


class FotoActivoInline(admin.TabularInline):
    model = FotoActivo
    form = FotoActivoInlineForm
    extra = 1
    max_num = 5
    fields = ("imagen", "vista_previa", "descripcion", "orden")
    readonly_fields = ("vista_previa",)

    def vista_previa(self, obj):
        if obj.pk and obj.imagen:
            return format_html(
                '<img src="{}" style="max-height: 80px; max-width: 120px; border-radius: 6px;" />',
                obj.preview_url,
            )
        return "Sin imagen"

    vista_previa.short_description = "Vista previa"


@admin.register(Activo)
class ActivoAdmin(admin.ModelAdmin):
    form = ActivoAdminForm
    list_display = (
        "codigo",
        "tipo_activo",
        "marca",
        "modelo",
        "serie",
        "codigo_sap",
        "fecha_compra",
        "valor",
        "estado_activo",
        "activo",
        "sistema_operativo",
        "cantidad_fotos",
        "miniatura_principal",
    )
    search_fields = (
        "codigo",
        "marca",
        "modelo",
        "serie",
        "codigo_sap",
        "cpu",
        "ram",
        "disco",
    )
    list_filter = (
        "tipo_activo",
        "estado_activo",
        "activo",
        "marca",
        "sistema_operativo",
        "fecha_compra",
    )
    list_select_related = ("tipo_activo", "estado_activo")
    inlines = [FotoActivoInline]

    class Media:
        js = ("admin/activos/activo_admin.js",)

    def miniatura_principal(self, obj):
        primera_foto = obj.fotos.order_by("orden", "id").first()
        if primera_foto and primera_foto.imagen:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 80px; border-radius: 4px;" />',
                primera_foto.imagen_thumb_url,
            )
        return "Sin imagen"

    miniatura_principal.short_description = "Imagen"

    def cantidad_fotos(self, obj):
        return obj.fotos.count()

    cantidad_fotos.short_description = "Fotos"


@admin.register(EventoActivo)
class EventoActivoAdmin(admin.ModelAdmin):
    form = EventoActivoAdminForm
    list_display = (
        "activo",
        "tipo_evento",
        "campo_afectado",
        "valor_anterior",
        "valor_nuevo",
        "costo_adicional",
        "sumar_costo_al_valor",
        "fecha_evento",
        "usuario_responsable",
    )
    fields = (
        "activo",
        "tipo_evento",
        "fecha_evento",
        "detalle",
        "campo_afectado",
        "valor_anterior_registrado",
        "valor_nuevo",
        "resumen_impacto",
        "costo_adicional",
        "sumar_costo_al_valor",
        "nuevo_estado_activo",
        "usuario_responsable",
    )
    readonly_fields = ("valor_anterior_registrado", "resumen_impacto")
    search_fields = (
        "activo__codigo",
        "activo__serie",
        "tipo_evento__nombre",
        "detalle",
        "valor_anterior",
        "valor_nuevo",
    )
    list_filter = (
        "tipo_evento",
        "campo_afectado",
        "sumar_costo_al_valor",
        "nuevo_estado_activo",
        "fecha_evento",
    )
    list_select_related = (
        "activo",
        "tipo_evento",
        "usuario_responsable",
        "nuevo_estado_activo",
    )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        activo_id = request.GET.get("activo", "").strip()
        if activo_id.isdigit():
            initial["activo"] = int(activo_id)
        return initial

    def valor_anterior_registrado(self, obj):
        if obj and obj.valor_anterior:
            return obj.valor_anterior
        return "Se capturara automaticamente al guardar el evento."

    valor_anterior_registrado.short_description = "Valor anterior del dato seleccionado"

    def resumen_impacto(self, obj):
        if not obj or not obj.pk:
            return "Despues de guardar, aqui veras el resumen del cambio aplicado al activo."

        cambios = []
        if obj.campo_afectado != EventoActivo.CampoAfectado.NINGUNO:
            cambios.append(
                f"{obj.get_campo_afectado_display()}: {obj.valor_anterior or '-'} -> {obj.valor_nuevo or '-'}"
            )
        if obj.sumar_costo_al_valor and obj.costo_adicional:
            cambios.append(f"Valor del activo: +${obj.costo_adicional}")
        if obj.nuevo_estado_activo_id:
            cambios.append(f"Estado final: {obj.nuevo_estado_activo}")

        return " | ".join(cambios) if cambios else "Evento informativo: no modifica la ficha del activo."

    resumen_impacto.short_description = "Resumen del impacto"
