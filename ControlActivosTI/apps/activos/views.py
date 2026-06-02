from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.asignaciones.models import AsignacionDetalle
from apps.catalogos.models import EstadoActivo, TipoActivo

from .forms import ActivoAdminForm, FotoActivoCreateFormSet
from .models import Activo, EventoActivo, FotoActivo
from .services import build_activos_export_workbook


class ActivoFilterMixin:
    def get_filter_value(self, name):
        if self.request.method == "POST":
            return self.request.POST.get(name, self.request.GET.get(name, "")).strip()
        return self.request.GET.get(name, "").strip()

    def get_filtered_queryset(self):
        queryset = (
            Activo.objects.select_related("tipo_activo", "estado_activo")
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
            )

        estado_id = self.get_filter_value("estado")
        if estado_id.isdigit():
            queryset = queryset.filter(estado_activo_id=estado_id)

        tipo_id = self.get_filter_value("tipo")
        if tipo_id.isdigit():
            queryset = queryset.filter(tipo_activo_id=tipo_id)

        if self.get_filter_value("ocultar_deshabilitados") == "1":
            queryset = queryset.filter(activo=True)

        return queryset

    def get_filter_context(self):
        return {
            "busqueda": self.get_filter_value("q"),
            "estado_seleccionado": self.get_filter_value("estado"),
            "tipo_seleccionado": self.get_filter_value("tipo"),
            "ocultar_deshabilitados": self.get_filter_value("ocultar_deshabilitados") == "1",
            "estados_activo": EstadoActivo.objects.filter(activo=True).order_by("nombre"),
            "tipos_activo": TipoActivo.objects.filter(activo=True).order_by("nombre"),
        }

    def get_export_querystring(self):
        params = self.request.GET.copy()
        params.pop("cols", None)
        querystring = params.urlencode()
        return f"?{querystring}" if querystring else ""


class ActivoListView(LoginRequiredMixin, ActivoFilterMixin, ListView):
    model = Activo
    template_name = "activos/lista.html"
    context_object_name = "activos"

    COLUMNAS_DISPONIBLES = [
        ("codigo", "Código"),
        ("tipo_activo", "Tipo"),
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
        return self.get_filtered_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 1
        context.update(self.get_filter_context())
        context["exportar_url"] = f"{reverse('activos:exportar')}{self.get_export_querystring()}"
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
            Activo.objects.select_related("tipo_activo", "estado_activo")
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
            Activo.objects.select_related("tipo_activo", "estado_activo")
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
