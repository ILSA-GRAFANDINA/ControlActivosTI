import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect, QueryDict
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.actas.services import generar_o_actualizar_acta, generar_o_actualizar_actas_devolucion
from apps.catalogos.models import Empresa, EstadoActivo, TipoActivo
from apps.facturas.models import FacturaCompra
from apps.notificaciones.services import NotificationService
from apps.proveedores.models import Proveedor

from .forms import (
    AsignacionCreateForm,
    AsignacionDetalleDevolucionFormSet,
    DevolucionForm,
)
from .models import Asignacion, Devolucion


logger = logging.getLogger("controlactivos")


class AsignacionListView(LoginRequiredMixin, ListView):
    model = Asignacion
    template_name = "asignaciones/lista.html"
    context_object_name = "asignaciones"
    paginate_by = 10
    FILTER_SESSION_KEY = "asignaciones_filtros_guardados"
    FILTER_FIELDS = ("q", "fecha_desde", "fecha_hasta", "orden")
    FILTER_MULTI_FIELDS = ("estado", "acta", "cols")
    ESTADOS_FILTRO = (
        ("ABIERTAS", "Abiertas (activas y parciales)"),
        (Asignacion.EstadoAsignacion.ACTIVA, "Activa"),
        (Asignacion.EstadoAsignacion.PARCIAL, "Parcial"),
        (Asignacion.EstadoAsignacion.CERRADA, "Cerrada"),
    )
    ACTAS_FILTRO = (
        ("con", "Con acta"),
        ("sin", "Sin acta"),
    )
    COLUMNAS_DISPONIBLES = [
        ("activos", "Activos"),
        ("colaborador", "Colaborador"),
        ("fecha", "Fecha"),
        ("estado", "Estado"),
        ("responsable", "Responsable"),
    ]
    COLUMNAS_POR_DEFECTO = ["activos", "colaborador", "fecha", "estado", "responsable"]
    ORDENES_FECHA = {
        "recientes": ("-fecha_asignacion", "-id"),
        "actividad": ("-updated_at", "-id"),
        "antiguas": ("fecha_asignacion", "id"),
    }

    def _filters_from_request(self):
        source = self.request.GET
        filtros = {}
        for field in self.FILTER_FIELDS:
            value = (source.get(field, "") or "").strip()
            if field == "orden" and value not in self.ORDENES_FECHA:
                value = "recientes"
            filtros[field] = value
        if not filtros["orden"]:
            filtros["orden"] = "recientes"

        estado_validos = {value for value, _ in self.ESTADOS_FILTRO}
        acta_validos = {value for value, _ in self.ACTAS_FILTRO}
        filtros["estado"] = list(dict.fromkeys(value for value in source.getlist("estado") if value in estado_validos))
        filtros["acta"] = list(dict.fromkeys(value for value in source.getlist("acta") if value in acta_validos))
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        filtros["cols"] = list(dict.fromkeys(value for value in source.getlist("cols") if value in columnas_validas)) or self.COLUMNAS_POR_DEFECTO
        return filtros

    def _has_filter_params(self):
        return any(field in self.request.GET for field in (*self.FILTER_FIELDS, *self.FILTER_MULTI_FIELDS))

    def get_active_filters(self):
        if self.request.GET.get("reset") == "1":
            self.request.session.pop(self.FILTER_SESSION_KEY, None)
            self.request.session.modified = True
            return {
                **{field: "recientes" if field == "orden" else "" for field in self.FILTER_FIELDS},
                **{field: self.COLUMNAS_POR_DEFECTO if field == "cols" else [] for field in self.FILTER_MULTI_FIELDS},
            }

        if self._has_filter_params():
            filtros = self._filters_from_request()
            self.request.session[self.FILTER_SESSION_KEY] = filtros
            self.request.session.modified = True
            return filtros

        filtros_guardados = self.request.session.get(self.FILTER_SESSION_KEY, {})
        if isinstance(filtros_guardados, dict):
            filtros = {
                field: (filtros_guardados.get(field, "") or "")
                for field in self.FILTER_FIELDS
            }
            if filtros.get("orden") not in self.ORDENES_FECHA:
                filtros["orden"] = "recientes"
            for field in self.FILTER_MULTI_FIELDS:
                saved_values = filtros_guardados.get(field, [])
                if isinstance(saved_values, str):
                    saved_values = [value for value in saved_values.split(",") if value]
                filtros[field] = [str(value) for value in saved_values if str(value).strip()]
            columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
            filtros["cols"] = [col for col in filtros["cols"] if col in columnas_validas] or self.COLUMNAS_POR_DEFECTO
            return filtros

        return {
            **{field: "recientes" if field == "orden" else "" for field in self.FILTER_FIELDS},
            **{field: self.COLUMNAS_POR_DEFECTO if field == "cols" else [] for field in self.FILTER_MULTI_FIELDS},
        }

    def build_filter_querystring(self):
        filtros = self.get_active_filters()
        params = QueryDict("", mutable=True)
        if filtros["q"]:
            params["q"] = filtros["q"]
        params.setlist("estado", filtros["estado"])
        params.setlist("acta", filtros["acta"])
        if filtros["cols"] != self.COLUMNAS_POR_DEFECTO:
            params.setlist("cols", filtros["cols"])
        if filtros["fecha_desde"]:
            params["fecha_desde"] = filtros["fecha_desde"]
        if filtros["fecha_hasta"]:
            params["fecha_hasta"] = filtros["fecha_hasta"]
        if filtros["orden"] != "recientes":
            params["orden"] = filtros["orden"]
        return params.urlencode()

    def get_selected_columns(self):
        seleccionadas = self.get_active_filters()["cols"]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def estado_filter_to_values(self, estados):
        valores = set()
        if "ABIERTAS" in estados:
            valores.update(
                [
                    Asignacion.EstadoAsignacion.ACTIVA,
                    Asignacion.EstadoAsignacion.PARCIAL,
                ]
            )
        for estado in estados:
            if estado in {
                Asignacion.EstadoAsignacion.ACTIVA,
                Asignacion.EstadoAsignacion.PARCIAL,
                Asignacion.EstadoAsignacion.CERRADA,
            }:
                valores.add(estado)
        return valores

    def get_queryset(self):
        filtros = self.get_active_filters()
        queryset = (
            Asignacion.objects.select_related(
                "colaborador",
                "centro_costo",
                "usuario_responsable",
                "usuario_recepcion",
            )
            .prefetch_related(
                "actas",
                "devoluciones__actas",
                "devoluciones__usuario_recepcion",
                "devoluciones__detalles__detalle_asignacion__activo__tipo_activo",
                "devoluciones__detalles__estado_activo_devolucion",
                "detalles__activo__tipo_activo",
                "detalles__activo__estado_activo",
            )
        )

        busqueda = filtros["q"]
        if busqueda:
            queryset = queryset.filter(
                Q(codigo_asignacion__icontains=busqueda)
                | Q(colaborador__nombres__icontains=busqueda)
                | Q(colaborador__apellidos__icontains=busqueda)
                | Q(colaborador__cedula__icontains=busqueda)
                | Q(detalles__activo__codigo__icontains=busqueda)
            )

        estados = self.estado_filter_to_values(filtros["estado"])
        if estados:
            queryset = queryset.filter(estado_asignacion__in=estados)

        actas = filtros["acta"]
        if actas and set(actas) != {"con", "sin"}:
            if "con" in actas:
                queryset = queryset.filter(actas__isnull=False)
            elif "sin" in actas:
                queryset = queryset.filter(actas__isnull=True)

        fecha_desde = parse_date(filtros["fecha_desde"])
        if fecha_desde:
            queryset = queryset.filter(fecha_asignacion__gte=fecha_desde)

        fecha_hasta = parse_date(filtros["fecha_hasta"])
        if fecha_hasta:
            queryset = queryset.filter(fecha_asignacion__lte=fecha_hasta)

        orden = filtros["orden"]
        campos_orden = self.ORDENES_FECHA.get(orden, self.ORDENES_FECHA["recientes"])

        return queryset.distinct().order_by(*campos_orden)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.get_active_filters()
        context["busqueda"] = filtros["q"]
        context["estado_seleccionado"] = filtros["estado"][0] if filtros["estado"] else ""
        context["estados_seleccionados"] = filtros["estado"]
        context["acta_seleccionada"] = filtros["acta"][0] if filtros["acta"] else ""
        context["actas_seleccionadas"] = filtros["acta"]
        context["fecha_desde"] = filtros["fecha_desde"]
        context["fecha_hasta"] = filtros["fecha_hasta"]
        context["orden_seleccionado"] = filtros["orden"]
        context["estados_filtro"] = self.ESTADOS_FILTRO
        context["actas_filtro"] = self.ACTAS_FILTRO
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 2
        context["cantidad_filtros_activos"] = (
            len(filtros["estado"])
            + len(filtros["acta"])
            + bool(filtros["q"])
            + bool(filtros["fecha_desde"])
            + bool(filtros["fecha_hasta"])
            + (filtros["orden"] != "recientes")
        )
        context["query_string"] = self.build_filter_querystring()
        if context.get("is_paginated"):
            context["page_numbers"] = context["paginator"].get_elided_page_range(
                number=context["page_obj"].number,
                on_each_side=1,
                on_ends=1,
            )
        return context


class AsignacionDetailView(LoginRequiredMixin, DetailView):
    model = Asignacion
    template_name = "asignaciones/detalle.html"
    context_object_name = "asignacion"

    def get_queryset(self):
        return (
            Asignacion.objects.select_related(
                "colaborador",
                "colaborador__empresa",
                "colaborador__area",
                "colaborador__cargo",
                "colaborador__ubicacion",
                "centro_costo",
                "usuario_responsable",
                "usuario_recepcion",
            )
            .prefetch_related(
                "actas",
                "devoluciones__actas",
                "devoluciones__usuario_recepcion",
                "devoluciones__detalles__detalle_asignacion__activo__tipo_activo",
                "devoluciones__detalles__estado_activo_devolucion",
                "detalles__activo__tipo_activo",
                "detalles__activo__estado_activo",
                "detalles__activo__fotos",
            )
        )


class DevolucionDetailView(LoginRequiredMixin, DetailView):
    model = Devolucion
    template_name = "asignaciones/devolucion_detalle.html"
    context_object_name = "devolucion"

    def get_queryset(self):
        return (
            Devolucion.objects.select_related(
                "asignacion",
                "asignacion__colaborador",
                "asignacion__colaborador__empresa",
                "asignacion__colaborador__area",
                "asignacion__colaborador__cargo",
                "usuario_recepcion",
            )
            .prefetch_related(
                "actas",
                "detalles__detalle_asignacion__activo__tipo_activo",
                "detalles__detalle_asignacion__activo__estado_activo",
                "detalles__estado_activo_devolucion",
            )
        )


class AsignacionCreateView(LoginRequiredMixin, CreateView):
    model = Asignacion
    form_class = AsignacionCreateForm
    template_name = "asignaciones/formulario.html"
    success_url = reverse_lazy("asignaciones:lista")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context["form"]
        activos_seleccionados = form["activos"].value() or []
        activos_disponibles = form.fields["activos"].queryset
        activos_recientes = list(
            activos_disponibles.filter(estado_activo__permite_asignacion=True)
            .exclude(estado_activo__nombre__icontains="repar")
            .exclude(estado_activo__nombre__icontains="cuarentena")
            .order_by("-created_at", "-id")[:5]
        )
        activos_recientes_ids = [activo.pk for activo in activos_recientes]
        context["activos_recientes"] = activos_recientes
        context["activos_disponibles"] = activos_disponibles.exclude(
            pk__in=activos_recientes_ids
        )
        context["activos_seleccionados"] = [int(activo_id) for activo_id in activos_seleccionados]
        context["estados_activo_filtro"] = EstadoActivo.objects.filter(activo=True).order_by("nombre")
        context["tipos_activo_filtro"] = TipoActivo.objects.filter(activo=True).order_by("nombre")
        context["empresas_activo_filtro"] = Empresa.objects.filter(activo=True).order_by("nombre")
        context["proveedores_activo_filtro"] = Proveedor.objects.order_by("razon_social")
        context["facturas_activo_filtro"] = FacturaCompra.objects.select_related(
            "proveedor"
        ).order_by("-fecha_emision", "-id")
        return context

    def form_valid(self, form):
        form.instance.usuario_responsable = self.request.user
        with transaction.atomic():
            self.object = form.save()
            NotificationService.asignacion_creada(self.object, self.request.user)

        try:
            generar_o_actualizar_acta(self.object, self.request.user)
            messages.success(
                self.request,
                "La asignación fue creada correctamente y el acta fue generada.",
            )
        except Exception:
            logger.exception(
                "No se pudo generar el acta de entrega asignacion_id=%s usuario_id=%s",
                self.object.pk,
                self.request.user.pk,
            )
            messages.warning(
                self.request,
                "La asignación fue creada correctamente, pero el acta no pudo generarse todavía.",
            )
            return HttpResponseRedirect(self.get_success_url())

        return HttpResponseRedirect(
            reverse(
                "actas:descargar_por_asignacion",
                args=[self.object.pk, "ENTREGA"],
            )
        )


class AsignacionDevolucionView(LoginRequiredMixin, UpdateView):
    model = Asignacion
    form_class = DevolucionForm
    template_name = "asignaciones/devolucion.html"
    success_url = reverse_lazy("asignaciones:lista")

    def get_queryset(self):
        return (
            Asignacion.objects.select_related(
                "colaborador",
                "usuario_responsable",
            )
            .prefetch_related(
                "detalles__activo__tipo_activo",
                "detalles__activo__estado_activo",
            )
            .filter(
                estado_asignacion__in=[
                    Asignacion.EstadoAsignacion.ACTIVA,
                    Asignacion.EstadoAsignacion.PARCIAL,
                ]
            )
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.pop("instance", None)
        kwargs["asignacion"] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        detalles_pendientes = self.object.detalles.filter(activa=True)
        if self.request.method == "POST":
            context["formset"] = AsignacionDetalleDevolucionFormSet(
                self.request.POST,
                instance=self.object,
                queryset=detalles_pendientes,
                prefix="detalles",
            )
        else:
            context["formset"] = AsignacionDetalleDevolucionFormSet(
                instance=self.object,
                queryset=detalles_pendientes,
                prefix="detalles",
            )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = AsignacionDetalleDevolucionFormSet(
            request.POST,
            instance=self.object,
            queryset=self.object.detalles.filter(activa=True),
            prefix="detalles",
        )

        if form.is_valid() and formset.is_valid():
            seleccionados = [
                detalle_form
                for detalle_form in formset.forms
                if detalle_form.cleaned_data.get("devolver")
            ]
            if not seleccionados:
                form.add_error(None, "Selecciona al menos un activo para registrar la devolucion.")
                return self.forms_invalid(form, formset)
            return self.forms_valid(form, formset)
        return self.forms_invalid(form, formset)

    def forms_valid(self, form, formset):
        codigos_devueltos = [
            detalle_form.instance.activo.codigo
            for detalle_form in formset.forms
            if detalle_form.cleaned_data.get("devolver")
        ]
        with transaction.atomic():
            devolucion = form.save(commit=False)
            devolucion.asignacion = self.object
            devolucion.usuario_recepcion = self.request.user
            devolucion.save()

            if not self.object.actas.filter(tipo="ENTREGA").exclude(archivo="").exists():
                generar_o_actualizar_acta(self.object, self.request.user)

            for detalle_form in formset.forms:
                detalle_form.save_devolucion_detalle(devolucion)

            generar_o_actualizar_actas_devolucion(devolucion, self.request.user)
            self.object.refresh_from_db(fields=["estado_asignacion", "updated_at"])
            NotificationService.asignacion_devuelta(
                self.object,
                devolucion,
                self.request.user,
                codigos_devueltos,
            )

        messages.success(self.request, "La devolución fue registrada correctamente.")
        return HttpResponseRedirect(reverse("asignaciones:devolucion_detalle", args=[devolucion.pk]))

    def forms_invalid(self, form, formset):
        return self.render_to_response(self.get_context_data(form=form, formset=formset))
