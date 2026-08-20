from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Case, Count, F, IntegerField, Prefetch, Q, Value, When
from django.forms.models import model_to_dict
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, QueryDict
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.asignaciones.models import AsignacionDetalle
from apps.catalogos.models import AtributoActivo, Empresa, EstadoActivo, TipoActivo, UbicacionFisicaActivo
from apps.facturas.models import FacturaCompra
from apps.notificaciones.services import NotificationService
from apps.depreciacion.services import DepreciationService
from apps.proveedores.models import Proveedor

from .forms import ActivoAdminForm, FotoActivoCreateFormSet
from .models import Activo, EventoActivo, FotoActivo, ValorAtributoActivo
from .services import build_activos_export_workbook
from .attribute_services import configuraciones_para_tipo, guardar_valores_atributos
from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar_evento


class ActivoFilterMixin:
    FILTER_SESSION_KEY = "activos_filtros_guardados"
    persist_filter_state = True
    FILTER_FIELDS = (
        "q",
        "orden",
        "mostrar_eliminados",
    )
    FILTER_MULTI_FIELDS = (
        "estado",
        "disponibilidad",
        "tipo",
        "empresa",
        "ubicacion_fisica",
        "proveedor",
        "modalidad_tenencia",
        "proveedor_propietario",
        "factura",
    )
    TAB_PARAM = "tab_tipo"

    def get_filter_value(self, name):
        return self.get_active_filters().get(name, "")

    def _filters_from_request(self):
        source = self.request.POST if self.request.method == "POST" else self.request.GET
        filtros = {}
        for field in self.FILTER_FIELDS:
            value = (source.get(field, "") or "").strip()
            if field == "mostrar_eliminados":
                value = "1" if source.get(field) in ("1", "on", "true", "True") else ""
            elif field == "orden" and value not in {"recientes"}:
                value = ""
            filtros[field] = value
        for field in self.FILTER_MULTI_FIELDS:
            values = [str(value).strip() for value in source.getlist(field)]
            if field == "disponibilidad":
                values = [value for value in values if value in {"disponibles", "asignados"}]
            elif field == "modalidad_tenencia":
                values = [
                    value
                    for value in values
                    if value in Activo.ModalidadTenencia.values
                ]
            elif field == "factura":
                values = [value for value in values if value.isdigit() or value == "sin_factura"]
            else:
                values = [value for value in values if value.isdigit()]
            filtros[field] = list(dict.fromkeys(values))
        return filtros

    def _has_filter_params(self):
        source = self.request.POST if self.request.method == "POST" else self.request.GET
        return any(field in source for field in (*self.FILTER_FIELDS, *self.FILTER_MULTI_FIELDS))

    def _reset_filter_state(self):
        self.request.session.pop(self.FILTER_SESSION_KEY, None)
        self.request.session.modified = True

    def get_active_filters(self):
        if self.request.GET.get("reset") == "1" or self.request.POST.get("reset") == "1":
            if self.persist_filter_state:
                self._reset_filter_state()
            return {
                **{field: "" for field in self.FILTER_FIELDS},
                **{field: [] for field in self.FILTER_MULTI_FIELDS},
            }

        if self._has_filter_params():
            filtros = self._filters_from_request()
            if self.persist_filter_state:
                self.request.session[self.FILTER_SESSION_KEY] = filtros
                self.request.session.modified = True
            return filtros

        filtros_guardados = self.request.session.get(self.FILTER_SESSION_KEY, {})
        if isinstance(filtros_guardados, dict):
            filtros = {field: (filtros_guardados.get(field, "") or "") for field in self.FILTER_FIELDS}
            for field in self.FILTER_MULTI_FIELDS:
                saved_values = filtros_guardados.get(field, [])
                if isinstance(saved_values, str):
                    saved_values = [value for value in saved_values.split(",") if value]
                filtros[field] = [str(value) for value in saved_values if str(value).strip()]
            return filtros

        return {
            **{field: "" for field in self.FILTER_FIELDS},
            **{field: [] for field in self.FILTER_MULTI_FIELDS},
        }

    def get_filtered_queryset(self):
        queryset = (
            Activo.objects.select_related(
                "tipo_activo",
                "estado_activo",
                "empresa",
                "ubicacion_fisica",
                "proveedor",
                "proveedor_propietario",
                "factura_compra",
            )
            .prefetch_related(
                "fotos",
                "valores_atributos__atributo",
                "valores_atributos__valor_opcion",
            )
            .order_by("tipo_activo__nombre", "codigo")
        )

        busqueda = self.get_filter_value("q")
        if busqueda:
            tipos_buscables = [
                tipo
                for tipo, _nombre in AtributoActivo.TipoDato.choices
                if tipo != AtributoActivo.TipoDato.TEXTO_PROTEGIDO
            ]
            criterio_configurado = Q(
                valores_atributos__vigente=True,
                valores_atributos__atributo__activo=True,
                valores_atributos__atributo__tipo_dato__in=tipos_buscables,
                valores_atributos__atributo__configuraciones_tipo__filtrable=True,
                valores_atributos__atributo__configuraciones_tipo__activo=True,
                valores_atributos__atributo__configuraciones_tipo__tipo_activo_id=F("tipo_activo_id"),
            )
            coincidencia_valor = (
                Q(valores_atributos__valor_texto__icontains=busqueda)
                | Q(valores_atributos__valor_opcion__nombre__icontains=busqueda)
                | Q(valores_atributos__valor_original_migracion__icontains=busqueda)
            )

            try:
                numero = Decimal(busqueda.replace(",", "."))
            except InvalidOperation:
                numero = None
            if numero is not None and numero.is_finite():
                if abs(numero) < Decimal("1e14"):
                    coincidencia_valor |= Q(valores_atributos__valor_decimal=numero)
                if (
                    numero == numero.to_integral_value()
                    and abs(numero) <= Decimal("9223372036854775807")
                ):
                    coincidencia_valor |= Q(valores_atributos__valor_entero=int(numero))

            for formato_fecha in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    fecha = datetime.strptime(busqueda, formato_fecha).date()
                except ValueError:
                    continue
                coincidencia_valor |= Q(valores_atributos__valor_fecha=fecha)
                break

            booleanos = {
                "si": True,
                "sí": True,
                "true": True,
                "no": False,
                "false": False,
            }
            if busqueda.casefold() in booleanos:
                coincidencia_valor |= Q(
                    valores_atributos__valor_booleano=booleanos[busqueda.casefold()]
                )

            queryset = queryset.filter(
                Q(codigo__icontains=busqueda)
                | Q(marca__icontains=busqueda)
                | Q(modelo__icontains=busqueda)
                | Q(serie__icontains=busqueda)
                | Q(codigo_sap__icontains=busqueda)
                | Q(empresa__nombre__icontains=busqueda)
                | Q(ubicacion_fisica__nombre__icontains=busqueda)
                | Q(proveedor__razon_social__icontains=busqueda)
                | Q(proveedor__nombre_comercial__icontains=busqueda)
                | Q(proveedor__identificacion__icontains=busqueda)
                | Q(proveedor_propietario__razon_social__icontains=busqueda)
                | Q(proveedor_propietario__nombre_comercial__icontains=busqueda)
                | Q(proveedor_propietario__identificacion__icontains=busqueda)
                | Q(factura_compra__numero_factura__icontains=busqueda)
                | (criterio_configurado & coincidencia_valor)
            )

        estado_ids = self.get_active_filters()["estado"]
        if estado_ids:
            queryset = queryset.filter(estado_activo_id__in=estado_ids)

        disponibilidades = self.get_active_filters()["disponibilidad"]
        if disponibilidades:
            filtro_disponibilidad = Q()
            if "disponibles" in disponibilidades:
                filtro_disponibilidad |= (
                    Q(estado_activo__permite_asignacion=True)
                    & ~Q(estado_activo__nombre__icontains="repar")
                    & ~Q(estado_activo__nombre__icontains="cuarentena")
                )
            if "asignados" in disponibilidades:
                filtro_disponibilidad |= Q(estado_activo__nombre__iexact="Asignado")
            queryset = queryset.filter(Q(activo=True) & filtro_disponibilidad)

        tipo_ids = self.get_active_filters().get("tipo", [])
        if tipo_ids:
            queryset = queryset.filter(tipo_activo_id__in=tipo_ids)

        empresa_ids = self.get_active_filters()["empresa"]
        if empresa_ids:
            queryset = queryset.filter(empresa_id__in=empresa_ids)

        ubicacion_fisica_ids = self.get_active_filters()["ubicacion_fisica"]
        if ubicacion_fisica_ids:
            queryset = queryset.filter(ubicacion_fisica_id__in=ubicacion_fisica_ids)

        proveedor_ids = self.get_active_filters()["proveedor"]
        if proveedor_ids:
            queryset = queryset.filter(proveedor_id__in=proveedor_ids)

        modalidades = self.get_active_filters()["modalidad_tenencia"]
        if modalidades:
            queryset = queryset.filter(modalidad_tenencia__in=modalidades)

        proveedor_propietario_ids = self.get_active_filters()["proveedor_propietario"]
        if proveedor_propietario_ids:
            queryset = queryset.filter(proveedor_propietario_id__in=proveedor_propietario_ids)

        facturas = self.get_active_filters()["factura"]
        if facturas:
            factura_ids = [value for value in facturas if value.isdigit()]
            filtro_factura = Q(factura_compra_id__in=factura_ids)
            if "sin_factura" in facturas:
                filtro_factura |= Q(factura_compra__isnull=True)
            queryset = queryset.filter(filtro_factura)

        if self.get_filter_value("mostrar_eliminados") != "1":
            queryset = queryset.filter(activo=True)

        if self.get_filter_value("orden") == "recientes":
            queryset = queryset.order_by("-created_at", "-id")

        return queryset.distinct()

    def get_filter_context(self):
        filtros = self.get_active_filters()
        return {
            "busqueda": filtros["q"],
            "estado_seleccionado": filtros["estado"][0] if filtros["estado"] else "",
            "estados_seleccionados": filtros["estado"],
            "disponibilidad_seleccionada": filtros["disponibilidad"][0] if filtros["disponibilidad"] else "",
            "disponibilidades_seleccionadas": filtros["disponibilidad"],
            "tipos_seleccionados": filtros["tipo"],
            "empresa_seleccionada": filtros["empresa"][0] if filtros["empresa"] else "",
            "empresas_seleccionadas": filtros["empresa"],
            "ubicacion_fisica_seleccionada": filtros["ubicacion_fisica"][0] if filtros["ubicacion_fisica"] else "",
            "ubicaciones_fisicas_seleccionadas": filtros["ubicacion_fisica"],
            "proveedor_seleccionado": filtros["proveedor"][0] if filtros["proveedor"] else "",
            "proveedores_seleccionados": filtros["proveedor"],
            "modalidad_tenencia_seleccionada": filtros["modalidad_tenencia"][0] if filtros["modalidad_tenencia"] else "",
            "modalidades_tenencia_seleccionadas": filtros["modalidad_tenencia"],
            "proveedor_propietario_seleccionado": filtros["proveedor_propietario"][0] if filtros["proveedor_propietario"] else "",
            "proveedores_propietarios_seleccionados": filtros["proveedor_propietario"],
            "factura_seleccionada": filtros["factura"][0] if filtros["factura"] else "",
            "facturas_seleccionadas": filtros["factura"],
            "orden_seleccionado": filtros["orden"],
            "mostrar_eliminados": filtros["mostrar_eliminados"] == "1",
            "cantidad_filtros_activos": (
                sum(len(filtros[field]) for field in self.FILTER_MULTI_FIELDS)
                + sum(bool(filtros[field]) for field in self.FILTER_FIELDS)
            ),
            "estados_activo": EstadoActivo.objects.filter(activo=True).order_by("nombre"),
            "tipos_activo": TipoActivo.objects.filter(activo=True).order_by("nombre"),
            "empresas_activo": Empresa.objects.filter(activo=True).order_by("nombre"),
            "ubicaciones_fisicas_activo": UbicacionFisicaActivo.objects.filter(activo=True).order_by("nombre"),
            "proveedores": Proveedor.objects.order_by("razon_social"),
            "modalidades_tenencia": Activo.ModalidadTenencia.choices,
            "proveedores_propietarios": Proveedor.objects.order_by("razon_social"),
            "facturas_compra": FacturaCompra.objects.select_related("proveedor").order_by("-fecha_emision"),
        }

    def get_export_querystring(self):
        filtros = self.get_active_filters()
        params = self.request.GET.copy()
        params.pop("cols", None)
        params["q"] = filtros["q"]
        for field in self.FILTER_MULTI_FIELDS:
            params.setlist(field, filtros[field])
        params["orden"] = filtros["orden"]
        if filtros["mostrar_eliminados"] == "1":
            params["mostrar_eliminados"] = "1"
        else:
            params.pop("mostrar_eliminados", None)
        params.pop("reset", None)
        querystring = params.urlencode()
        return f"?{querystring}" if querystring else ""

    def get_tab_summary(self, queryset):
        return list(
            queryset.values("tipo_activo_id", "tipo_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("tipo_activo__nombre")
        )

    def get_active_tab_type_id(self):
        source = self.request.POST if self.request.method == "POST" else self.request.GET
        raw_value = (source.get(self.TAB_PARAM, "") or "").strip()
        if not raw_value.isdigit():
            return ""
        if raw_value not in getattr(self, "available_tab_type_ids", set()):
            return ""
        return raw_value

    def build_filter_querystring(self, extra_params=None, include_columns=False):
        filtros = self.get_active_filters()
        params = QueryDict("", mutable=True)
        params["q"] = filtros["q"]
        for field in self.FILTER_MULTI_FIELDS:
            params.setlist(field, filtros[field])
        params["orden"] = filtros["orden"]
        if filtros["mostrar_eliminados"] == "1":
            params["mostrar_eliminados"] = "1"

        if include_columns and hasattr(self, "get_selected_columns"):
            for columna in self.get_selected_columns():
                params.appendlist("cols", columna)

        for key, value in (extra_params or {}).items():
            if value in ("", None, [], ()):
                continue
            if isinstance(value, (list, tuple)):
                params.setlist(key, [str(item) for item in value])
            else:
                params[key] = str(value)

        querystring = params.urlencode()
        return f"?{querystring}" if querystring else ""

    def build_tabs_context(self, base_url, summary, active_tab_type_id, include_columns=False):
        return [
            {
                "id": "",
                "nombre": "Todos",
                "total": sum(item["total"] for item in summary),
                "activa": not active_tab_type_id,
                "url": f"{base_url}{self.build_filter_querystring(include_columns=include_columns)}",
            },
            *[
                {
                    "id": str(item["tipo_activo_id"]),
                    "nombre": item["tipo_activo__nombre"],
                    "total": item["total"],
                    "activa": active_tab_type_id == str(item["tipo_activo_id"]),
                    "url": f"{base_url}{self.build_filter_querystring({self.TAB_PARAM: item['tipo_activo_id']}, include_columns=include_columns)}",
                }
                for item in summary
            ],
        ]


class ActivoListView(LoginRequiredMixin, ActivoFilterMixin, ListView):
    model = Activo
    template_name = "activos/lista.html"
    context_object_name = "activos"

    COLUMNAS_DISPONIBLES = [
        ("tipo_activo", "Tipo"),
        ("empresa", "Empresa"),
        ("ubicacion_fisica", "Ubicacion fisica"),
        ("proveedor", "Proveedor"),
        ("modalidad_tenencia", "Tenencia"),
        ("proveedor_propietario", "Proveedor propietario"),
        ("factura", "Factura"),
        ("marca", "Marca"),
        ("modelo", "Modelo"),
        ("serie", "Serie"),
        ("codigo_sap", "Codigo SAP"),
        ("cpu", "CPU"),
        ("ram", "RAM"),
        ("disco", "Disco"),
        ("sistema_operativo", "Sistema operativo"),
        ("fecha_compra", "Fecha de compra"),
        ("valor", "Valor de Compra"),
        ("estado_activo", "Estado"),
    ]

    COLUMNAS_POR_DEFECTO = [
        "tipo_activo",
        "empresa",
        "ubicacion_fisica",
        "proveedor",
        "marca",
        "modelo",
        "serie",
        "estado_activo",
    ]

    def get_selected_columns(self):
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        seleccionadas = [
            col for col in self.request.GET.getlist("cols")
            if col in columnas_validas
        ]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def get_queryset(self):
        queryset = self.get_filtered_queryset()
        resumen_tipos = self.get_tab_summary(queryset)
        self.tab_type_summary = resumen_tipos
        self.available_tab_type_ids = {str(item["tipo_activo_id"]) for item in resumen_tipos}
        self.active_tab_type_id = self.get_active_tab_type_id()

        if self.active_tab_type_id:
            queryset = queryset.filter(tipo_activo_id=self.active_tab_type_id)

        estados_seleccionados = self.get_active_filters()["estado"]
        self.agrupar_por_estado = len(estados_seleccionados) > 1
        if self.agrupar_por_estado:
            orden_interno = (
                ("-created_at", "-id")
                if self.get_filter_value("orden") == "recientes"
                else ("codigo",)
            )
            prioridad_disponible = Case(
                When(estado_activo__nombre__iexact="Disponible", then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
            queryset = queryset.order_by(
                "tipo_activo__nombre",
                prioridad_disponible,
                "estado_activo__nombre",
                *orden_interno,
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        # El número de fila y el código enlazado son columnas fijas.
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 2
        context.update(self.get_filter_context())
        context["total_activos_filtrados"] = len(context.get("activos", []))
        context["exportar_url"] = f"{reverse('activos:exportar')}{self.get_export_querystring()}"
        context["tab_tipo_activa"] = self.active_tab_type_id
        context["agrupar_por_estado"] = self.agrupar_por_estado
        context["hay_filtros_para_exportar"] = bool(
            context["busqueda"]
            or context["estado_seleccionado"]
            or context["disponibilidad_seleccionada"]
            or context["tipos_seleccionados"]
            or context["empresa_seleccionada"]
            or context["ubicacion_fisica_seleccionada"]
            or context["proveedor_seleccionado"]
            or context["modalidad_tenencia_seleccionada"]
            or context["proveedor_propietario_seleccionado"]
            or context["factura_seleccionada"]
            or context["orden_seleccionado"]
            or context["mostrar_eliminados"]
            or self.active_tab_type_id
        )
        context["exportar_sin_filtros_url"] = f"{reverse('activos:exportar')}?reset=1"
        context["tabs_tipo"] = self.build_tabs_context(
            reverse("activos:lista"),
            self.tab_type_summary,
            self.active_tab_type_id,
            include_columns=True,
        )
        return context


class ActivoExportView(LoginRequiredMixin, ActivoFilterMixin, TemplateView):
    template_name = "activos/exportar.html"
    # Exportar consume filtros, pero nunca debe sustituir la selección persistida
    # del listado principal con los campos auxiliares de su formulario.
    persist_filter_state = False

    def get_filtered_export_queryset(self):
        queryset = self.get_filtered_queryset()
        self.tab_type_summary = self.get_tab_summary(queryset)
        self.available_tab_type_ids = {str(item["tipo_activo_id"]) for item in self.tab_type_summary}
        self.active_tab_type_id = self.get_active_tab_type_id()
        if self.active_tab_type_id:
            queryset = queryset.filter(tipo_activo_id=self.active_tab_type_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activos = list(self.get_filtered_export_queryset())
        context.update(self.get_filter_context())
        context["activos"] = activos
        context["total_activos_filtrados"] = len(activos)
        context["volver_url"] = f"{reverse('activos:lista')}{self.get_export_querystring()}"
        context["error_exportacion"] = kwargs.get("error_exportacion", "")
        context["selected_ids"] = kwargs.get("selected_ids", [])
        context["tab_tipo_activa"] = self.active_tab_type_id
        context["tabs_tipo"] = self.build_tabs_context(
            reverse("activos:exportar"),
            self.tab_type_summary,
            self.active_tab_type_id,
        )
        return context

    def post(self, request, *args, **kwargs):
        is_async_download = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        selected_ids = [pk for pk in request.POST.getlist("activos") if pk.isdigit()]
        if not selected_ids:
            if is_async_download:
                return JsonResponse(
                    {"ok": False, "message": "Debes seleccionar al menos un activo para exportar."},
                    status=400,
                )
            context = self.get_context_data(
                error_exportacion="Debes seleccionar al menos un activo para exportar.",
                selected_ids=[],
            )
            return self.render_to_response(context)

        activos = list(self.get_filtered_queryset().filter(pk__in=selected_ids))
        if not activos:
            if is_async_download:
                return JsonResponse(
                    {"ok": False, "message": "Los activos seleccionados ya no están disponibles con estos filtros."},
                    status=400,
                )
            context = self.get_context_data(
                error_exportacion="Los activos seleccionados no estan disponibles con los filtros actuales.",
                selected_ids=selected_ids,
            )
            return self.render_to_response(context)

        workbook = build_activos_export_workbook(activos)
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        filename = f"activos_export_{timezone.localdate().isoformat()}.xlsx"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["X-Export-Message"] = f"Se exportaron {len(activos)} activo(s) correctamente."
        workbook.save(response)
        return response


class ActivoCreateView(LoginRequiredMixin, CreateView):
    model = Activo
    form_class = ActivoAdminForm
    template_name = "activos/formulario.html"
    context_object_name = "activo"
    edit_param_name = "editar"
    edit_pk_field_name = "activo_id"
    copy_param_name = "basado_en"
    copy_pk_field_name = "activo_base_id"

    def _get_activo_en_edicion(self):
        raw_pk = (
            self.request.POST.get(self.edit_pk_field_name)
            or self.request.GET.get(self.edit_param_name)
            or ""
        ).strip()
        if not raw_pk.isdigit():
            return None

        return (
            Activo.objects.select_related(
                "tipo_activo",
                "estado_activo",
                "empresa",
                  "ubicacion_fisica",
                  "proveedor",
                  "proveedor_propietario",
                  "factura_compra",
            )
            .prefetch_related("fotos")
            .filter(pk=raw_pk)
            .first()
        )

    def _get_activo_base(self):
        if getattr(self, "activo_en_edicion", None):
            return None
        raw_pk = (
            self.request.POST.get(self.copy_pk_field_name)
            or self.request.GET.get(self.copy_param_name)
            or ""
        ).strip()
        if not raw_pk.isdigit():
            return None
        return (
            Activo.objects.select_related(
                "tipo_activo",
                "estado_activo",
                "empresa",
                  "ubicacion_fisica",
                  "proveedor",
                  "proveedor_propietario",
                  "factura_compra",
            )
            .prefetch_related("valores_atributos__atributo", "valores_atributos__valor_opcion")
            .filter(pk=raw_pk)
            .first()
        )

    def dispatch(self, request, *args, **kwargs):
        self.activo_en_edicion = self._get_activo_en_edicion()
        self.activo_base = self._get_activo_base()
        self.object = None
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if not self.activo_en_edicion and not self.activo_base and request.GET.get("modo") != "cero":
            return render(
                request,
                "activos/nuevo_opcion.html",
                {
                    "crear_desde_cero_url": f"{reverse('activos:nuevo')}?modo=cero",
                    "seleccionar_base_url": reverse("activos:seleccionar-base"),
                    "volver_url": reverse("activos:lista"),
                },
            )
        return super().get(request, *args, **kwargs)

    def _get_activo_contextual(self):
        return self.object or getattr(self, "activo_en_edicion", None)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["permitir_cambio_vigencia"] = False
        kwargs["usuario"] = self.request.user
        activo_en_edicion = getattr(self, "activo_en_edicion", None)
        if activo_en_edicion and kwargs.get("instance") is None:
            kwargs["instance"] = activo_en_edicion
        activo_base = getattr(self, "activo_base", None)
        if activo_base and not activo_en_edicion:
            campos = [
                campo.name
                for campo in Activo._meta.fields
                if campo.editable and campo.name not in {"activo"}
            ]
            initial = model_to_dict(activo_base, fields=campos)
            estado_disponible_id = (
                EstadoActivo.objects.filter(activo=True, nombre__iexact="Disponible")
                .values_list("pk", flat=True)
                .first()
            )
            if estado_disponible_id:
                initial["estado_activo"] = estado_disponible_id
            kwargs["initial"] = initial
            kwargs["activo_base"] = activo_base
            kwargs["bloquear_tipo"] = True
        return kwargs

    def get_formset(self, data=None, files=None):
        activo_contextual = self._get_activo_contextual()
        kwargs = {
            "queryset": (
                activo_contextual.fotos.order_by("orden", "id")
                if activo_contextual
                else FotoActivo.objects.none()
            ),
            "prefix": "fotos",
        }
        if data is not None:
            kwargs["data"] = data
        if files is not None:
            kwargs["files"] = files
        return FotoActivoCreateFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("formset", self.get_formset())
        activo_contextual = self._get_activo_contextual()
        context["es_edicion"] = bool(activo_contextual)
        activo_base = getattr(self, "activo_base", None)
        context["es_copia"] = bool(activo_base and not activo_contextual)
        context["activo_base"] = activo_base
        context["titulo_formulario"] = (
            "Editar activo" if activo_contextual else "Nuevo activo basado en otro" if activo_base else "Nuevo activo"
        )
        context["subtitulo_formulario"] = (
            "Actualiza la ficha del equipo y, si quieres, sus imagenes asociadas."
            if activo_contextual
            else (
                f"Revisa los datos copiados de {activo_base.codigo}. Las fotos no se copiaran."
                if activo_base
                else "Registra la ficha del equipo y, si quieres, sus imagenes iniciales."
            )
        )
        context["texto_submit"] = "Guardar cambios" if activo_contextual else "Guardar activo"
        context["etiqueta_codigo"] = "Codigo automatico"
        context["volver_url"] = (
            reverse("activos:detalle", args=[activo_contextual.pk])
            if activo_contextual
            else reverse("activos:lista")
        )
        context["form_action_url"] = (
            f"{reverse('activos:nuevo')}?{self.edit_param_name}={activo_contextual.pk}"
            if activo_contextual
            else (
                f"{reverse('activos:nuevo')}?{self.copy_param_name}={activo_base.pk}"
                if activo_base
                else reverse("activos:nuevo")
            )
        )
        context["activo_edicion_id"] = activo_contextual.pk if activo_contextual else None
        context["activo_edicion_tipo_id"] = activo_contextual.tipo_activo_id if activo_contextual else None
        context["borrador_activo_habilitado"] = not activo_contextual and not activo_base
        context["restaurar_borrador_activo"] = not activo_contextual and not activo_base and self.request.method == "GET"
        return context

    def post(self, request, *args, **kwargs):
        self.activo_en_edicion = self._get_activo_en_edicion()
        self.object = None
        form = self.get_form()
        formset = self.get_formset(request.POST, request.FILES)

        if form.is_valid() and formset.is_valid():
            return self.forms_valid(form, formset)
        return self.forms_invalid(form, formset)

    def forms_valid(self, form, formset):
        es_edicion = bool(self.activo_en_edicion)
        tipo_anterior_id = self.activo_en_edicion.tipo_activo_id if self.activo_en_edicion else None
        campos_relevantes = set(form.changed_data) & {
            "marca",
            "modelo",
            "tipo_activo",
            "estado_activo",
            "empresa",
            "ubicacion_fisica",
            "activo",
            "proveedor",
            "factura_compra",
        }
        cambios_relevantes = {
            campo: (form.initial.get(campo), form.cleaned_data.get(campo))
            for campo in campos_relevantes
        }
        with transaction.atomic():
            self.object = form.save()
            # Los valores protegidos no se muestran ni se descifran. Al copiar,
            # se replica directamente el valor cifrado antes de procesar el
            # resto de atributos; si el usuario escribio uno nuevo, el servicio
            # habitual lo reemplazara a continuacion.
            if not es_edicion and self.activo_base:
                for valor in self.activo_base.valores_atributos.filter(
                    vigente=True,
                    atributo__tipo_dato=AtributoActivo.TipoDato.TEXTO_PROTEGIDO,
                ):
                    ValorAtributoActivo.objects.create(
                        activo=self.object,
                        atributo=valor.atributo,
                        tipo_activo_origen=self.object.tipo_activo,
                        valor_texto=valor.valor_texto,
                        vigente=True,
                        created_by=self.request.user,
                        updated_by=self.request.user,
                    )
            guardar_valores_atributos(
                self.object,
                form.valores_atributos_limpios(),
                usuario=self.request.user,
            )
            if tipo_anterior_id and tipo_anterior_id != self.object.tipo_activo_id:
                registrar_evento(
                    entidad="Activo",
                    objeto_id=self.object.pk,
                    accion=RegistroAuditoria.Accion.CAMBIAR_TIPO,
                    resumen=f"Cambio controlado de tipo del activo {self.object.codigo}",
                    usuario=self.request.user,
                    detalle={
                        "tipo_anterior_id": tipo_anterior_id,
                        "tipo_nuevo_id": self.object.tipo_activo_id,
                        "motivo": form.cleaned_data.get("motivo_cambio_tipo", ""),
                    },
                )
            fotos = formset.save(commit=False)
            for foto in fotos:
                foto.activo = self.object
                foto.save()
            if es_edicion:
                NotificationService.activo_cambiado(
                    self.object, self.request.user, cambios_relevantes
                )
            else:
                NotificationService.activo_creado(self.object, self.request.user)
        messages.success(
            self.request,
            (
                f"El activo {self.object.codigo} fue actualizado correctamente."
                if es_edicion
                else f"El activo {self.object.codigo} fue registrado correctamente."
            ),
        )
        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, form, formset):
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def get_success_url(self):
        return reverse("activos:detalle", args=[self.object.pk])


class ActivoBaseSelectView(LoginRequiredMixin, ActivoFilterMixin, ListView):
    model = Activo
    template_name = "activos/seleccionar_base.html"
    context_object_name = "activos"
    paginate_by = 25
    FILTER_SESSION_KEY = "activos_filtros_copia"
    persist_filter_state = False

    def get_queryset(self):
        return self.get_filtered_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_filter_context())
        context["volver_url"] = reverse("activos:nuevo")
        pagination_params = self.request.GET.copy()
        pagination_params.pop("page", None)
        encoded_params = pagination_params.urlencode()
        context["pagination_prefix"] = f"{encoded_params}&" if encoded_params else ""
        return context


class TipoActivoAtributosJsonView(LoginRequiredMixin, View):
    def get(self, request, tipo_id, *args, **kwargs):
        tipo = get_object_or_404(TipoActivo, pk=tipo_id, activo=True)
        atributos = []
        for configuracion in configuraciones_para_tipo(tipo.pk):
            atributo = configuracion.atributo
            unidad = configuracion.unidad_efectiva
            ayuda = configuracion.texto_ayuda or atributo.descripcion
            if unidad and atributo.tipo_dato in {
                AtributoActivo.TipoDato.ENTERO,
                AtributoActivo.TipoDato.DECIMAL,
            }:
                instruccion = f"Ingresa solo el valor numerico; {unidad} se agrega automaticamente."
                ayuda = f"{ayuda} {instruccion}".strip()
            atributos.append(
                {
                    "clave": atributo.clave,
                    "nombre": atributo.nombre,
                    "tipo": atributo.tipo_dato,
                    "obligatorio": configuracion.obligatorio,
                    "ayuda": ayuda,
                    "unidad": unidad,
                    "valor_predeterminado": configuracion.valor_predeterminado,
                    "minimo": str(configuracion.valor_minimo) if configuracion.valor_minimo is not None else None,
                    "maximo": str(configuracion.valor_maximo) if configuracion.valor_maximo is not None else None,
                    "longitud_maxima": configuracion.longitud_maxima,
                    "opciones": [
                        {"id": opcion.pk, "nombre": opcion.nombre}
                        for opcion in atributo.opciones.all()
                        if opcion.activo
                    ],
                }
            )
        return JsonResponse({"tipo": tipo.nombre, "atributos": atributos})


class FacturasProveedorJsonView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        proveedor_ids = [
            value
            for value in request.GET.getlist("proveedor")
            if str(value).isdigit()
        ]
        factura_ids = [
            value
            for value in request.GET.getlist("factura")
            if str(value).isdigit()
        ]
        if not proveedor_ids:
            return JsonResponse({"facturas": []})

        facturas = FacturaCompra.objects.filter(
            Q(activa=True) | Q(pk__in=factura_ids),
            proveedor_id__in=proveedor_ids,
        ).select_related("proveedor", "empresa").order_by("-fecha_emision", "numero_factura")
        return JsonResponse(
            {
                "facturas": [
                    {
                        "id": factura.pk,
                        "numero": factura.numero_factura,
                        "proveedor_id": factura.proveedor_id,
                        "proveedor": str(factura.proveedor),
                        "empresa": factura.empresa.nombre if factura.empresa_id else "",
                        "fecha": factura.fecha_emision.isoformat() if factura.fecha_emision else "",
                        "label": f"{factura.numero_factura} - {factura.proveedor}",
                    }
                    for factura in facturas
                ]
            }
        )


class ActivoDetailView(LoginRequiredMixin, DetailView):
    model = Activo
    template_name = "activos/detalle.html"
    context_object_name = "activo"

    def get_queryset(self):
        return (
            Activo.objects.select_related(
                "tipo_activo",
                "estado_activo",
                "empresa",
                  "ubicacion_fisica",
                  "proveedor",
                  "proveedor_propietario",
                  "factura_compra",
                "factura_compra__proveedor",
                "factura_compra__empresa",
            )
            .prefetch_related(
                Prefetch(
                    "valores_atributos",
                    queryset=ValorAtributoActivo.objects.select_related(
                        "atributo", "valor_opcion", "tipo_activo_origen"
                    ).order_by("atributo__nombre"),
                ),
                Prefetch(
                    "fotos",
                    queryset=FotoActivo.objects.order_by("orden", "id"),
                ),
                Prefetch(
                    "eventos",
                    queryset=EventoActivo.objects.select_related(
                        "tipo_evento",
                        "usuario_responsable",
                    ).order_by("-fecha_evento", "-id"),
                ),
                Prefetch(
                    "detalles_asignacion",
                    queryset=AsignacionDetalle.objects.select_related(
                        "asignacion",
                        "asignacion__colaborador",
                        "asignacion__usuario_responsable",
                        "asignacion__usuario_recepcion",
                        "estado_activo_devolucion",
                    ).order_by("-asignacion__fecha_asignacion", "-id"),
                ),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activo = self.object

        detalles_asignacion = list(activo.detalles_asignacion.all())
        historial_reciente = detalles_asignacion[:5]
        historial_completo = detalles_asignacion[5:]
        detalle_activo = next(
            (detalle for detalle in detalles_asignacion if detalle.activa),
            None,
        )

        context["asignacion_activa"] = detalle_activo.asignacion if detalle_activo else None
        context["detalle_asignacion_activa"] = detalle_activo
        context["editar_url"] = f"{reverse('activos:nuevo')}?{ActivoCreateView.edit_param_name}={activo.pk}"
        context["fotos_activo"] = list(activo.fotos.all())
        context["historial_asignaciones"] = historial_reciente
        context["historial_asignaciones_completo"] = historial_completo
        context["total_historial_asignaciones"] = len(detalles_asignacion)
        context["historial_eventos"] = list(activo.eventos.all())
        from .attribute_services import atributos_para_detalle
        context["atributos_configurables"] = atributos_para_detalle(activo)
        context["valores_atributos_historicos"] = [
            valor for valor in activo.valores_atributos.all() if not valor.vigente
        ]
        configuracion_depreciacion = DepreciationService.configuracion()
        context["calculo_depreciacion"] = DepreciationService.calcular(activo)
        context["mostrar_valor_residual"] = (
            configuracion_depreciacion.mostrar_valor_residual
        )
        context["vida_util_texto"] = "3 años"
        return context


class ActivoVigenciaView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "activos.change_activo"
    raise_exception = True
    template_name = "activos/confirmar_vigencia.html"
    acciones_validas = {"eliminar", "restaurar"}

    def dispatch(self, request, *args, **kwargs):
        self.accion = kwargs["accion"]
        if self.accion not in self.acciones_validas:
            return redirect("activos:detalle", pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def _get_activo(self):
        return get_object_or_404(
            Activo.objects.select_related("tipo_activo", "estado_activo"),
            pk=self.kwargs["pk"],
        )

    @staticmethod
    def _get_asignacion_activa(activo):
        detalle = (
            activo.detalles_asignacion.filter(activa=True)
            .select_related("asignacion", "asignacion__colaborador")
            .first()
        )
        return detalle.asignacion if detalle else None

    def get(self, request, *args, **kwargs):
        activo = self._get_activo()
        if self.accion == "eliminar" and not activo.activo:
            messages.info(request, f"El activo {activo.codigo} ya está eliminado.")
            return redirect("activos:detalle", pk=activo.pk)
        if self.accion == "restaurar" and activo.activo:
            messages.info(request, f"El activo {activo.codigo} ya está activo.")
            return redirect("activos:detalle", pk=activo.pk)
        return render(
            request,
            self.template_name,
            {
                "activo": activo,
                "accion": self.accion,
                "asignacion_activa": self._get_asignacion_activa(activo),
            },
        )

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            activo = get_object_or_404(
                Activo.objects.select_for_update().select_related(
                    "tipo_activo", "estado_activo"
                ),
                pk=self.kwargs["pk"],
            )
            estado_anterior = activo.activo
            estado_nuevo = self.accion == "restaurar"

            if estado_anterior == estado_nuevo:
                messages.info(
                    request,
                    f"El activo {activo.codigo} ya tiene el estado solicitado.",
                )
                return redirect("activos:detalle", pk=activo.pk)

            asignacion_activa = self._get_asignacion_activa(activo)
            if self.accion == "eliminar" and asignacion_activa:
                messages.error(
                    request,
                    "No se puede eliminar un activo con una asignación vigente. "
                    "Registra primero su devolución.",
                )
                return redirect("activos:detalle", pk=activo.pk)

            if self.accion == "restaurar" and not activo.estado_activo.activo:
                messages.error(
                    request,
                    "No se puede restaurar el activo porque su estado de catálogo está inactivo.",
                )
                return redirect("activos:detalle", pk=activo.pk)
            if (
                self.accion == "restaurar"
                and activo.estado_activo.nombre_normalizado == "asignado"
            ):
                messages.error(
                    request,
                    "No se puede restaurar un activo con estado “Asignado” sin una "
                    "asignación vigente. Actualiza primero su estado operativo.",
                )
                return redirect("activos:detalle", pk=activo.pk)

            activo.activo = estado_nuevo
            activo.save(update_fields=["activo", "updated_at"])
            NotificationService.activo_cambiado(
                activo,
                request.user,
                {"activo": (estado_anterior, estado_nuevo)},
            )

        messages.success(
            request,
            (
                f"El activo {activo.codigo} fue reactivado correctamente."
                if estado_nuevo
                else f"El activo {activo.codigo} fue eliminado correctamente."
            ),
        )
        return redirect("activos:detalle", pk=activo.pk)
