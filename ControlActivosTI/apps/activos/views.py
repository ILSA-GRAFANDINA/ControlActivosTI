from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, QueryDict
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.asignaciones.models import AsignacionDetalle
from apps.catalogos.models import Empresa, EstadoActivo, TipoActivo
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
    FILTER_FIELDS = (
        "q",
        "estado",
        "disponibilidad",
        "empresa",
        "proveedor",
        "factura",
        "orden",
        "mostrar_eliminados",
    )
    FILTER_MULTI_FIELDS = ("tipo",)
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
        filtros["tipo"] = [valor.strip() for valor in source.getlist("tipo") if valor.strip().isdigit()]
        return filtros

    def _has_filter_params(self):
        source = self.request.POST if self.request.method == "POST" else self.request.GET
        return any(field in source for field in self.FILTER_FIELDS) or bool(
            [valor for valor in source.getlist("tipo") if valor.strip()]
        )

    def _reset_filter_state(self):
        self.request.session.pop(self.FILTER_SESSION_KEY, None)
        self.request.session.modified = True

    def get_active_filters(self):
        if self.request.GET.get("reset") == "1" or self.request.POST.get("reset") == "1":
            self._reset_filter_state()
            return {**{field: "" for field in self.FILTER_FIELDS}, "tipo": []}

        if self._has_filter_params():
            filtros = self._filters_from_request()
            self.request.session[self.FILTER_SESSION_KEY] = filtros
            self.request.session.modified = True
            return filtros

        filtros_guardados = self.request.session.get(self.FILTER_SESSION_KEY, {})
        if isinstance(filtros_guardados, dict):
            filtros = {field: (filtros_guardados.get(field, "") or "") for field in self.FILTER_FIELDS}
            tipo_guardado = filtros_guardados.get("tipo", [])
            if isinstance(tipo_guardado, str):
                tipo_guardado = [tipo for tipo in tipo_guardado.split(",") if tipo]
            filtros["tipo"] = [str(tipo) for tipo in tipo_guardado if str(tipo).strip()]
            return filtros

        return {**{field: "" for field in self.FILTER_FIELDS}, "tipo": []}

    def get_filtered_queryset(self):
        queryset = (
            Activo.objects.select_related("tipo_activo", "estado_activo", "empresa", "proveedor", "factura_compra")
            .prefetch_related(
                "fotos",
                "valores_atributos__atributo",
                "valores_atributos__valor_opcion",
            )
            .order_by("tipo_activo__nombre", "codigo")
        )

        busqueda = self.get_filter_value("q")
        if busqueda:
            queryset = queryset.filter(
                Q(codigo__icontains=busqueda)
                | Q(marca__icontains=busqueda)
                | Q(modelo__icontains=busqueda)
                | Q(serie__icontains=busqueda)
                | Q(codigo_sap__icontains=busqueda)
                | Q(empresa__nombre__icontains=busqueda)
                | Q(proveedor__razon_social__icontains=busqueda)
                | Q(proveedor__nombre_comercial__icontains=busqueda)
                | Q(proveedor__identificacion__icontains=busqueda)
                | Q(factura_compra__numero_factura__icontains=busqueda)
                | Q(
                    valores_atributos__vigente=True,
                    valores_atributos__atributo__configuraciones_tipo__filtrable=True,
                    valores_atributos__atributo__configuraciones_tipo__activo=True,
                    valores_atributos__atributo__configuraciones_tipo__tipo_activo_id=F("tipo_activo_id"),
                    valores_atributos__valor_texto__icontains=busqueda,
                )
                | Q(
                    valores_atributos__vigente=True,
                    valores_atributos__atributo__configuraciones_tipo__filtrable=True,
                    valores_atributos__atributo__configuraciones_tipo__tipo_activo_id=F("tipo_activo_id"),
                    valores_atributos__valor_opcion__nombre__icontains=busqueda,
                )
            )

        estado_id = self.get_filter_value("estado")
        if estado_id.isdigit():
            queryset = queryset.filter(estado_activo_id=estado_id)

        disponibilidad = self.get_filter_value("disponibilidad")
        if disponibilidad == "disponibles":
            queryset = (
                queryset.filter(
                    activo=True,
                    estado_activo__permite_asignacion=True,
                )
                .exclude(estado_activo__nombre__icontains="repar")
                .exclude(estado_activo__nombre__icontains="cuarentena")
            )
        elif disponibilidad == "asignados":
            queryset = queryset.filter(
                activo=True,
                estado_activo__nombre__iexact="Asignado",
            )

        tipo_ids = self.get_active_filters().get("tipo", [])
        if tipo_ids:
            queryset = queryset.filter(tipo_activo_id__in=tipo_ids)

        empresa_id = self.get_filter_value("empresa")
        if empresa_id.isdigit():
            queryset = queryset.filter(empresa_id=empresa_id)

        proveedor_id = self.get_filter_value("proveedor")
        if proveedor_id.isdigit():
            queryset = queryset.filter(proveedor_id=proveedor_id)

        factura_id = self.get_filter_value("factura")
        if factura_id.isdigit():
            queryset = queryset.filter(factura_compra_id=factura_id)
        elif factura_id == "sin_factura":
            queryset = queryset.filter(factura_compra__isnull=True)

        if self.get_filter_value("mostrar_eliminados") != "1":
            queryset = queryset.filter(activo=True)

        if self.get_filter_value("orden") == "recientes":
            queryset = queryset.order_by("-created_at", "-id")

        return queryset.distinct()

    def get_filter_context(self):
        filtros = self.get_active_filters()
        return {
            "busqueda": filtros["q"],
            "estado_seleccionado": filtros["estado"],
            "disponibilidad_seleccionada": filtros["disponibilidad"],
            "tipos_seleccionados": filtros["tipo"],
            "empresa_seleccionada": filtros["empresa"],
            "proveedor_seleccionado": filtros["proveedor"],
            "factura_seleccionada": filtros["factura"],
            "orden_seleccionado": filtros["orden"],
            "mostrar_eliminados": filtros["mostrar_eliminados"] == "1",
            "estados_activo": EstadoActivo.objects.filter(activo=True).order_by("nombre"),
            "tipos_activo": TipoActivo.objects.filter(activo=True).order_by("nombre"),
            "empresas_activo": Empresa.objects.filter(activo=True).order_by("nombre"),
            "proveedores": Proveedor.objects.order_by("razon_social"),
            "facturas_compra": FacturaCompra.objects.select_related("proveedor").order_by("-fecha_emision"),
        }

    def get_export_querystring(self):
        filtros = self.get_active_filters()
        params = self.request.GET.copy()
        params.pop("cols", None)
        params["q"] = filtros["q"]
        params["estado"] = filtros["estado"]
        params["disponibilidad"] = filtros["disponibilidad"]
        params.setlist("tipo", filtros["tipo"])
        params["empresa"] = filtros["empresa"]
        params["proveedor"] = filtros["proveedor"]
        params["factura"] = filtros["factura"]
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
        params["estado"] = filtros["estado"]
        params["disponibilidad"] = filtros["disponibilidad"]
        params.setlist("tipo", filtros["tipo"])
        params["empresa"] = filtros["empresa"]
        params["proveedor"] = filtros["proveedor"]
        params["factura"] = filtros["factura"]
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
        ("proveedor", "Proveedor"),
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
        context["hay_filtros_para_exportar"] = bool(
            context["busqueda"]
            or context["estado_seleccionado"]
            or context["disponibilidad_seleccionada"]
            or context["tipos_seleccionados"]
            or context["empresa_seleccionada"]
            or context["proveedor_seleccionado"]
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
        selected_ids = [pk for pk in request.POST.getlist("activos") if pk.isdigit()]
        if not selected_ids:
            context = self.get_context_data(
                error_exportacion="Debes seleccionar al menos un activo para exportar.",
                selected_ids=[],
            )
            return self.render_to_response(context)

        activos = list(self.get_filtered_queryset().filter(pk__in=selected_ids))
        if not activos:
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
        workbook.save(response)
        return response


class ActivoCreateView(LoginRequiredMixin, CreateView):
    model = Activo
    form_class = ActivoAdminForm
    template_name = "activos/formulario.html"
    context_object_name = "activo"
    edit_param_name = "editar"
    edit_pk_field_name = "activo_id"

    def _get_activo_en_edicion(self):
        raw_pk = (
            self.request.POST.get(self.edit_pk_field_name)
            or self.request.GET.get(self.edit_param_name)
            or ""
        ).strip()
        if not raw_pk.isdigit():
            return None

        return (
            Activo.objects.select_related("tipo_activo", "estado_activo", "empresa", "proveedor", "factura_compra")
            .prefetch_related("fotos")
            .filter(pk=raw_pk)
            .first()
        )

    def dispatch(self, request, *args, **kwargs):
        self.activo_en_edicion = self._get_activo_en_edicion()
        self.object = None
        return super().dispatch(request, *args, **kwargs)

    def _get_activo_contextual(self):
        return self.object or getattr(self, "activo_en_edicion", None)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["permitir_cambio_vigencia"] = False
        kwargs["usuario"] = self.request.user
        activo_en_edicion = getattr(self, "activo_en_edicion", None)
        if activo_en_edicion and kwargs.get("instance") is None:
            kwargs["instance"] = activo_en_edicion
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
        context["titulo_formulario"] = "Editar activo" if activo_contextual else "Nuevo activo"
        context["subtitulo_formulario"] = (
            "Actualiza la ficha del equipo y, si quieres, sus imagenes asociadas."
            if activo_contextual
            else "Registra la ficha del equipo y, si quieres, sus imagenes iniciales."
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
            else reverse("activos:nuevo")
        )
        context["activo_edicion_id"] = activo_contextual.pk if activo_contextual else None
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


class ActivoDetailView(LoginRequiredMixin, DetailView):
    model = Activo
    template_name = "activos/detalle.html"
    context_object_name = "activo"

    def get_queryset(self):
        return (
            Activo.objects.select_related("tipo_activo", "estado_activo", "empresa", "proveedor", "factura_compra", "factura_compra__proveedor", "factura_compra__empresa")
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
