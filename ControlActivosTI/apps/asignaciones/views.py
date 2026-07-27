from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.actas.services import generar_o_actualizar_acta, generar_o_actualizar_actas_devolucion
from apps.notificaciones.services import NotificationService

from .forms import (
    AsignacionCreateForm,
    AsignacionDetalleDevolucionFormSet,
    DevolucionForm,
)
from .models import Asignacion, Devolucion


class AsignacionListView(LoginRequiredMixin, ListView):
    model = Asignacion
    template_name = "asignaciones/lista.html"
    context_object_name = "asignaciones"
    paginate_by = 10
    ORDENES_FECHA = {
        "recientes": ("-fecha_asignacion", "-id"),
        "actividad": ("-updated_at", "-id"),
        "antiguas": ("fecha_asignacion", "id"),
    }

    def get_queryset(self):
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

        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            queryset = queryset.filter(
                Q(codigo_asignacion__icontains=busqueda)
                | Q(colaborador__nombres__icontains=busqueda)
                | Q(colaborador__apellidos__icontains=busqueda)
                | Q(colaborador__cedula__icontains=busqueda)
                | Q(detalles__activo__codigo__icontains=busqueda)
            )

        estado = self.request.GET.get("estado", "").strip()
        if estado == "ABIERTAS":
            queryset = queryset.filter(
                estado_asignacion__in=[
                    Asignacion.EstadoAsignacion.ACTIVA,
                    Asignacion.EstadoAsignacion.PARCIAL,
                ]
            )
        elif estado in {
            Asignacion.EstadoAsignacion.ACTIVA,
            Asignacion.EstadoAsignacion.PARCIAL,
            Asignacion.EstadoAsignacion.CERRADA,
        }:
            queryset = queryset.filter(estado_asignacion=estado)

        acta = self.request.GET.get("acta", "").strip()
        if acta == "con":
            queryset = queryset.filter(actas__isnull=False)
        elif acta == "sin":
            queryset = queryset.filter(actas__isnull=True)

        fecha_desde = parse_date(self.request.GET.get("fecha_desde", "").strip())
        if fecha_desde:
            queryset = queryset.filter(fecha_asignacion__gte=fecha_desde)

        fecha_hasta = parse_date(self.request.GET.get("fecha_hasta", "").strip())
        if fecha_hasta:
            queryset = queryset.filter(fecha_asignacion__lte=fecha_hasta)

        orden = self.request.GET.get("orden", "recientes").strip()
        campos_orden = self.ORDENES_FECHA.get(orden, self.ORDENES_FECHA["recientes"])

        return queryset.distinct().order_by(*campos_orden)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["busqueda"] = self.request.GET.get("q", "").strip()
        context["estado_seleccionado"] = self.request.GET.get("estado", "").strip()
        context["acta_seleccionada"] = self.request.GET.get("acta", "").strip()
        context["fecha_desde"] = self.request.GET.get("fecha_desde", "").strip()
        context["fecha_hasta"] = self.request.GET.get("fecha_hasta", "").strip()
        context["orden_seleccionado"] = self.request.GET.get("orden", "recientes").strip()
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["query_string"] = query_params.urlencode()
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
        context["activos_disponibles"] = activos_disponibles
        context["activos_seleccionados"] = [int(activo_id) for activo_id in activos_seleccionados]
        context["estados_activo_filtro"] = sorted(
            {
                activo.estado_activo.nombre
                for activo in activos_disponibles
                if activo.estado_activo_id and activo.estado_activo.activo
            }
        )
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
            messages.warning(
                self.request,
                "La asignación fue creada correctamente, pero el acta no pudo generarse todavía.",
            )

        return HttpResponseRedirect(self.get_success_url())


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
