from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, HttpResponseRedirect, QueryDict
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.asignaciones.models import AsignacionDetalle
from apps.catalogos.models import Empresa, EstadoActivo, TipoActivo

from .forms import ActivoAdminForm, FotoActivoCreateFormSet
from .models import Activo, EventoActivo, FotoActivo
from .services import build_activos_export_workbook


class ActivoFilterMixin:
    FILTER_SESSION_KEY = "activos_filtros_guardados"
    FILTER_FIELDS = ("q", "estado", "empresa", "ocultar_deshabilitados")
    FILTER_MULTI_FIELDS = ("tipo",)

    def get_filter_value(self, name):
        return self.get_active_filters().get(name, "")

    def _filters_from_request(self):
        source = self.request.POST if self.request.method == "POST" else self.request.GET
        filtros = {}
        for field in self.FILTER_FIELDS:
            value = (source.get(field, "") or "").strip()
            if field == "ocultar_deshabilitados":
                value = "1" if source.get(field) in ("1", "on", "true", "True") else ""
            filtros[field] = value
        filtros["tipo"] = [valor.strip() for valor in source.getlist("tipo") if valor.strip().isdigit()]
        return filtros

    def _has_filter_params(self):
        source = self.request.POST if self.request.method == "POST" else self.request.GET
        return any(source.get(field) not in (None, "") for field in self.FILTER_FIELDS) or bool(
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
            Activo.objects.select_related("tipo_activo", "estado_activo", "empresa")
            .prefetch_related("fotos")
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
            )

        estado_id = self.get_filter_value("estado")
        if estado_id.isdigit():
            queryset = queryset.filter(estado_activo_id=estado_id)

        tipo_ids = self.get_active_filters().get("tipo", [])
        if tipo_ids:
            queryset = queryset.filter(tipo_activo_id__in=tipo_ids)

        empresa_id = self.get_filter_value("empresa")
        if empresa_id.isdigit():
            queryset = queryset.filter(empresa_id=empresa_id)

        if self.get_filter_value("ocultar_deshabilitados") == "1":
            queryset = queryset.filter(activo=True)

        return queryset

    def get_filter_context(self):
        filtros = self.get_active_filters()
        return {
            "busqueda": filtros["q"],
            "estado_seleccionado": filtros["estado"],
            "tipos_seleccionados": filtros["tipo"],
            "empresa_seleccionada": filtros["empresa"],
            "ocultar_deshabilitados": filtros["ocultar_deshabilitados"] == "1",
            "estados_activo": EstadoActivo.objects.filter(activo=True).order_by("nombre"),
            "tipos_activo": TipoActivo.objects.filter(activo=True).order_by("nombre"),
            "empresas_activo": Empresa.objects.filter(activo=True).order_by("nombre"),
        }

    def get_export_querystring(self):
        filtros = self.get_active_filters()
        params = self.request.GET.copy()
        params.pop("cols", None)
        params["q"] = filtros["q"]
        params["estado"] = filtros["estado"]
        params.setlist("tipo", filtros["tipo"])
        params["empresa"] = filtros["empresa"]
        if filtros["ocultar_deshabilitados"] == "1":
            params["ocultar_deshabilitados"] = "1"
        else:
            params.pop("ocultar_deshabilitados", None)
        params.pop("reset", None)
        querystring = params.urlencode()
        return f"?{querystring}" if querystring else ""


class ActivoListView(LoginRequiredMixin, ActivoFilterMixin, ListView):
    model = Activo
    template_name = "activos/lista.html"
    context_object_name = "activos"
    TAB_PARAM = "tab_tipo"

    COLUMNAS_DISPONIBLES = [
        ("codigo", "Código"),
        ("tipo_activo", "Tipo"),
        ("empresa", "Empresa"),
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
        "codigo",
        "tipo_activo",
        "empresa",
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

    def get_active_tab_type_id(self):
        raw_value = (self.request.GET.get(self.TAB_PARAM, "") or "").strip()
        if not raw_value.isdigit():
            return ""
        if raw_value not in getattr(self, "available_tab_type_ids", set()):
            return ""
        return raw_value

    def build_list_querystring(self, tab_tipo=None):
        filtros = self.get_active_filters()
        params = QueryDict("", mutable=True)
        params["q"] = filtros["q"]
        params["estado"] = filtros["estado"]
        params.setlist("tipo", filtros["tipo"])
        params["empresa"] = filtros["empresa"]
        if filtros["ocultar_deshabilitados"] == "1":
            params["ocultar_deshabilitados"] = "1"

        for columna in self.get_selected_columns():
            params.appendlist("cols", columna)

        if tab_tipo:
            params[self.TAB_PARAM] = str(tab_tipo)

        querystring = params.urlencode()
        return f"?{querystring}" if querystring else ""

    def get_queryset(self):
        queryset = self.get_filtered_queryset()
        resumen_tipos = list(
            queryset.values("tipo_activo_id", "tipo_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("tipo_activo__nombre")
        )
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
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 2
        context.update(self.get_filter_context())
        context["total_activos_filtrados"] = len(context.get("activos", []))
        context["exportar_url"] = f"{reverse('activos:exportar')}{self.get_export_querystring()}"
        context["tab_tipo_activa"] = self.active_tab_type_id
        context["tabs_tipo"] = [
            {
                "id": "",
                "nombre": "Todos",
                "total": sum(item["total"] for item in self.tab_type_summary),
                "activa": not self.active_tab_type_id,
                "url": f"{reverse('activos:lista')}{self.build_list_querystring()}",
            },
            *[
                {
                    "id": str(item["tipo_activo_id"]),
                    "nombre": item["tipo_activo__nombre"],
                    "total": item["total"],
                    "activa": self.active_tab_type_id == str(item["tipo_activo_id"]),
                    "url": f"{reverse('activos:lista')}{self.build_list_querystring(item['tipo_activo_id'])}",
                }
                for item in self.tab_type_summary
            ],
        ]
        return context


class ActivoExportView(LoginRequiredMixin, ActivoFilterMixin, TemplateView):
    template_name = "activos/exportar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activos = list(self.get_filtered_queryset())
        context.update(self.get_filter_context())
        context["activos"] = activos
        context["total_activos_filtrados"] = len(activos)
        context["volver_url"] = f"{reverse('activos:lista')}{self.get_export_querystring()}"
        context["error_exportacion"] = kwargs.get("error_exportacion", "")
        context["selected_ids"] = kwargs.get("selected_ids", [])
        return context

    def post(self, request, *args, **kwargs):
        selected_ids = [pk for pk in request.POST.getlist("activos") if pk.isdigit()]
        if not selected_ids:
            context = self.get_context_data(
                error_exportacion="Debes seleccionar al menos un activo para exportar.",
                selected_ids=[],
            )
            return self.render_to_response(context)

        activos = list(
            self.get_filtered_queryset().filter(pk__in=selected_ids).order_by("tipo_activo__nombre", "codigo")
        )
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
            Activo.objects.select_related("tipo_activo", "estado_activo", "empresa")
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
        with transaction.atomic():
            self.object = form.save()
            fotos = formset.save(commit=False)
            for foto in fotos:
                foto.activo = self.object
                foto.save()
        return HttpResponseRedirect(self.get_success_url())

    def forms_invalid(self, form, formset):
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def get_success_url(self):
        return reverse("activos:detalle", args=[self.object.pk])


class ActivoDetailView(LoginRequiredMixin, DetailView):
    model = Activo
    template_name = "activos/detalle.html"
    context_object_name = "activo"

    def get_queryset(self):
        return (
            Activo.objects.select_related("tipo_activo", "estado_activo", "empresa")
            .prefetch_related(
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
        return context
