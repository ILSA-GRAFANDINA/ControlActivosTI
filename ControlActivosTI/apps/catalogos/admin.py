from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from urllib.parse import parse_qs

from .models import (
    AtributoActivo,
    Area,
    Cargo,
    CentroCosto,
    DepartamentoEmpresa,
    Empresa,
    Ubicacion,
    TipoActivo,
    TipoActivoAtributo,
    OpcionAtributoActivo,
    EstadoActivo,
    TipoEventoActivo,
)
from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar_evento


class CentroCostoAdminForm(forms.ModelForm):
    class Meta:
        model = CentroCosto
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "departamentos" in self.fields:
            departamentos = DepartamentoEmpresa.objects.select_related("empresa").filter(activo=True)
            empresa_id = self.data.get("empresa") if self.is_bound else None

            if empresa_id:
                departamentos = departamentos.filter(empresa_id=empresa_id)
            elif self.instance and self.instance.pk and self.instance.empresa_id:
                departamentos = departamentos.filter(empresa_id=self.instance.empresa_id)

            self.fields["departamentos"].queryset = departamentos.order_by("empresa__nombre", "nombre")

    def clean(self):
        cleaned_data = super().clean()
        empresa = cleaned_data.get("empresa")
        departamentos = cleaned_data.get("departamentos")

        if departamentos and not empresa:
            self.add_error("empresa", "Debes seleccionar una empresa antes de asignar departamentos.")
            return cleaned_data

        if empresa and departamentos:
            departamentos_invalidos = [
                departamento.nombre
                for departamento in departamentos
                if departamento.empresa_id != empresa.id
            ]
            if departamentos_invalidos:
                nombres = ", ".join(departamentos_invalidos)
                self.add_error(
                    "departamentos",
                    (
                        "Todos los departamentos deben pertenecer a la misma empresa del CECO. "
                        f"No corresponden a {empresa.nombre}: {nombres}."
                    ),
                )

        return cleaned_data


class AtributoActivoAdminForm(forms.ModelForm):
    class Meta:
        model = AtributoActivo
        fields = ("nombre", "clave", "descripcion", "tipo_dato", "unidad", "activo")

    def clean_clave(self):
        return AtributoActivo.normalizar_clave(self.cleaned_data["clave"])

    def clean(self):
        cleaned = super().clean()
        texto = f"{cleaned.get('nombre', '')} {cleaned.get('clave', '')}".lower()
        tipo_dato = cleaned.get("tipo_dato")
        palabras_prohibidas = ("password", "contrasena", "contraseña", "token", "clave_privada", "api_key", "secreto")
        if tipo_dato != AtributoActivo.TipoDato.TEXTO_PROTEGIDO and any(palabra in texto for palabra in palabras_prohibidas):
            raise forms.ValidationError(
                "Los atributos normales no pueden almacenar contrasenas, tokens, claves privadas ni secretos."
            )
        return cleaned


class TipoActivoAtributoAdminForm(forms.ModelForm):
    class Meta:
        model = TipoActivoAtributo
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk:
            tipo_activo = cleaned.get("tipo_activo")
            if tipo_activo:
                ultimo_orden = (
                    TipoActivoAtributo.objects.filter(
                        tipo_activo=tipo_activo,
                        activo=True,
                    ).aggregate(maximo=Max("orden"))["maximo"]
                    or 0
                )
                self.instance.orden = ultimo_orden + 1
        return cleaned


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(DepartamentoEmpresa)
class DepartamentoEmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "activo", "created_at")
    search_fields = ("nombre", "empresa__nombre")
    list_filter = ("empresa", "activo")
    list_select_related = ("empresa",)
    autocomplete_fields = ("empresa",)


@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
    form = CentroCostoAdminForm
    list_display = (
        "codigo",
        "nombre",
        "empresa",
        "mostrar_departamentos",
        "padre",
        "tipo",
        "responsable",
        "acepta_asignaciones",
        "activo",
        "fecha_inicio",
        "fecha_fin",
    )
    search_fields = (
        "codigo",
        "nombre",
        "empresa__nombre",
        "departamentos__nombre",
        "padre__codigo",
        "padre__nombre",
    )
    list_filter = (
        "activo",
        "acepta_asignaciones",
        "tipo",
        "empresa",
        "departamentos",
    )
    list_select_related = ("empresa", "padre", "responsable")
    autocomplete_fields = ("empresa", "padre", "responsable", "departamentos")
    readonly_fields = ("created_at", "updated_at", "mostrar_ruta_jerarquia", "mostrar_departamentos")
    fieldsets = (
        (
            "Datos maestros",
            {
                "fields": (
                    "codigo",
                    "nombre",
                    "empresa",
                    "tipo",
                    "padre",
                    "mostrar_ruta_jerarquia",
                    "departamentos",
                    "mostrar_departamentos",
                    "responsable",
                )
            },
        ),
        (
            "Control operativo",
            {
                "fields": (
                    "activo",
                    "acepta_asignaciones",
                    "fecha_inicio",
                    "fecha_fin",
                    "descripcion",
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

    @admin.display(description="Ruta jerarquica")
    def mostrar_ruta_jerarquia(self, obj):
        return obj.ruta_jerarquia if obj.pk else "-"

    @admin.display(description="Departamentos incluidos")
    def mostrar_departamentos(self, obj):
        return obj.departamentos_resumen if obj.pk else "-"


@admin.register(TipoActivo)
class TipoActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "uso_atributos", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("activo",)

    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.has_perm("catalogos.manage_asset_attribute_schema")

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def uso_atributos(self, obj):
        from django.conf import settings
        usados = obj.configuraciones_atributos.filter(activo=True).count()
        limite = int(getattr(settings, "MAX_ATRIBUTOS_ACTIVOS_POR_TIPO", 10))
        url = reverse("admin:catalogos_tipoactivoatributo_changelist")
        url = f"{url}?{urlencode({'tipo_activo__id__exact': obj.pk})}"
        return format_html(
            '<a href="{}">{} de {} atributos configurados</a>',
            url,
            usados,
            limite,
        )

    uso_atributos.short_description = "Atributos"


@admin.register(EstadoActivo)
class EstadoActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "permite_asignacion", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("permite_asignacion", "activo")


@admin.register(TipoEventoActivo)
class TipoEventoActivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "created_at")
    search_fields = ("nombre",)
    list_filter = ("activo",)

class OpcionAtributoActivoInline(admin.TabularInline):
    model = OpcionAtributoActivo
    extra = 1
    fields = ("clave", "nombre", "orden", "activo")


@admin.register(AtributoActivo)
class AtributoActivoAdmin(admin.ModelAdmin):
    form = AtributoActivoAdminForm
    list_display = ("nombre", "clave", "tipo_dato", "unidad", "activo", "tipos_que_lo_usan", "updated_at")
    search_fields = ("nombre", "clave", "descripcion")
    list_filter = ("tipo_dato", "activo")
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at", "tipos_que_lo_usan")
    inlines = (OpcionAtributoActivoInline,)

    def tipos_que_lo_usan(self, obj):
        if not obj or not obj.pk:
            return "-"
        nombres = obj.configuraciones_tipo.filter(activo=True).select_related("tipo_activo").order_by("tipo_activo__nombre").values_list("tipo_activo__nombre", flat=True)
        return ", ".join(nombres) or "Sin tipos asociados"

    tipos_que_lo_usan.short_description = "Tipos que lo utilizan"

    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.has_perm("catalogos.manage_asset_attribute_schema")

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request) and not (obj and obj.valores.exists())

    def save_model(self, request, obj, form, change):
        anterior_activo = None
        if change:
            anterior_activo = AtributoActivo.objects.filter(pk=obj.pk).values_list("activo", flat=True).first()
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        accion = RegistroAuditoria.Accion.MODIFICAR if change else RegistroAuditoria.Accion.CREAR
        if change and anterior_activo != obj.activo:
            accion = RegistroAuditoria.Accion.ACTIVAR if obj.activo else RegistroAuditoria.Accion.DESACTIVAR
        registrar_evento(
            entidad="AtributoActivo", objeto_id=obj.pk, accion=accion,
            resumen=f"{obj.nombre} ({obj.clave})", usuario=request.user,
            detalle={"campos": form.changed_data},
        )


@admin.register(TipoActivoAtributo)
class TipoActivoAtributoAdmin(admin.ModelAdmin):
    form = TipoActivoAtributoAdminForm
    list_display = (
        "tipo_activo", "atributo", "orden", "obligatorio", "activo",
        "mostrar_detalle", "mostrar_actas", "filtrable",
    )
    list_filter = ("tipo_activo", "obligatorio", "activo", "mostrar_actas", "filtrable")
    search_fields = ("tipo_activo__nombre", "atributo__nombre", "atributo__clave")
    list_select_related = ("tipo_activo", "atributo")
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    actions = ("quitar_del_tipo",)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        changelist_filters = request.GET.get("_changelist_filters", "")
        tipo_activo_id = parse_qs(changelist_filters).get("tipo_activo__id__exact", [None])[0]
        if tipo_activo_id and "tipo_activo" not in initial:
            initial["tipo_activo"] = tipo_activo_id
        return initial

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or ())
        if obj is None:
            # Excluirlo al construir el ModelForm evita que Django Admin intente
            # renderizar un campo retirado posteriormente. En edicion permanece
            # disponible para reorganizaciones manuales.
            exclude.append("orden")
        return exclude

    def has_module_permission(self, request):
        return request.user.is_superuser or request.user.has_perm("catalogos.manage_asset_attribute_schema")

    has_view_permission = AtributoActivoAdmin.has_view_permission
    has_add_permission = AtributoActivoAdmin.has_add_permission
    has_change_permission = AtributoActivoAdmin.has_change_permission

    def has_delete_permission(self, request, obj=None):
        # Quitar un atributo de un tipo siempre es una desactivacion reversible.
        # La asociacion se conserva para proteger configuracion, auditoria y valores historicos.
        return False

    @admin.action(description="Quitar del tipo seleccionado (conservar historial)")
    def quitar_del_tipo(self, request, queryset):
        configuraciones = list(
            queryset.filter(activo=True).select_related("tipo_activo", "atributo")
        )
        for configuracion in configuraciones:
            configuracion.activo = False
            configuracion.updated_by = request.user
            configuracion.save(update_fields=("activo", "updated_by", "updated_at"))
            registrar_evento(
                entidad="TipoActivoAtributo",
                objeto_id=configuracion.pk,
                accion=RegistroAuditoria.Accion.DESACTIVAR,
                resumen=(
                    f"{configuracion.atributo.nombre} fue quitado de "
                    f"{configuracion.tipo_activo.nombre}"
                ),
                usuario=request.user,
                detalle={
                    "tipo_activo_id": configuracion.tipo_activo_id,
                    "atributo_id": configuracion.atributo_id,
                    "historial_conservado": True,
                },
            )
        self.message_user(
            request,
            f"Se quitaron {len(configuraciones)} asociaciones. Los valores historicos se conservaron.",
        )

    def save_model(self, request, obj, form, change):
        anterior_activo = None
        if change:
            anterior_activo = type(obj).objects.filter(pk=obj.pk).values_list("activo", flat=True).first()
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        if change:
            super().save_model(request, obj, form, change)
        else:
            # El bloqueo evita que dos altas simultaneas reciban el mismo orden.
            with transaction.atomic():
                TipoActivo.objects.select_for_update().get(pk=obj.tipo_activo_id)
                ultimo_orden = (
                    type(obj).objects.filter(
                        tipo_activo_id=obj.tipo_activo_id,
                        activo=True,
                    ).aggregate(maximo=Max("orden"))["maximo"]
                    or 0
                )
                obj.orden = ultimo_orden + 1
                super().save_model(request, obj, form, change)
        accion = RegistroAuditoria.Accion.MODIFICAR if change else RegistroAuditoria.Accion.ASOCIAR
        if change and anterior_activo != obj.activo:
            accion = RegistroAuditoria.Accion.ACTIVAR if obj.activo else RegistroAuditoria.Accion.DESACTIVAR
        registrar_evento(
            entidad="TipoActivoAtributo", objeto_id=obj.pk,
            accion=accion,
            resumen=f"{obj.atributo.nombre} en {obj.tipo_activo.nombre}", usuario=request.user,
            detalle={"campos": form.changed_data, "orden": obj.orden, "obligatorio": obj.obligatorio},
        )
