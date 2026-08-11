from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseRedirect, QueryDict
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.notificaciones.services import NotificationService

from .forms import ProveedorForm
from .models import Proveedor

class ProveedorListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "proveedores.view_proveedor"
    raise_exception = True
    model = Proveedor
    template_name = "proveedores/lista.html"
    context_object_name = "proveedores"
    paginate_by = 10
    FILTER_SESSION_KEY = "proveedores_filtros_guardados"
    FILTER_FIELDS = ("q", "orden")
    FILTER_MULTI_FIELDS = (
        "estado",
        "tipo_proveedor",
        "tipo_identificacion",
        "pais",
        "relaciones",
        "cols",
    )

    COLUMNAS_DISPONIBLES = [
        ("proveedor", "Proveedor"),
        ("identificacion", "Identificacion"),
        ("tipo_proveedor", "Tipo de proveedor"),
        ("contacto", "Contacto"),
        ("correo", "Correo"),
        ("telefono", "Telefono"),
        ("ubicacion", "Ubicacion"),
        ("estado", "Estado"),
        ("activos", "Activos"),
        ("actualizado", "Ultima modificacion"),
    ]
    COLUMNAS_POR_DEFECTO = [
        "proveedor",
        "identificacion",
        "ubicacion",
        "estado",
        "activos",
    ]
    ESTADOS_FILTRO = (
        ("activo", "Activos"),
        ("inactivo", "Inactivos"),
    )
    RELACIONES_FILTRO = (
        ("con_activos", "Con activos"),
        ("sin_activos", "Sin activos"),
        ("con_facturas", "Con facturas"),
        ("sin_facturas", "Sin facturas"),
    )
    ORDENES = {
        "nombre_asc": ("razon_social", "identificacion"),
        "nombre_desc": ("-razon_social", "-identificacion"),
        "actualizado_reciente": ("-updated_at", "-id"),
        "actualizado_antiguo": ("updated_at", "id"),
    }
    ORDENES_CHOICES = (
        ("nombre_asc", "Proveedor: A a Z"),
        ("nombre_desc", "Proveedor: Z a A"),
        ("actualizado_reciente", "Actualización más reciente"),
        ("actualizado_antiguo", "Actualización más antigua"),
    )

    def _default_filters(self):
        return {
            **{
                field: "nombre_asc" if field == "orden" else ""
                for field in self.FILTER_FIELDS
            },
            **{field: [] for field in self.FILTER_MULTI_FIELDS},
        }

    def _sanitize_filters(self, filtros):
        filtros = {**self._default_filters(), **(filtros or {})}
        filtros["q"] = (filtros.get("q", "") or "").strip()
        filtros["orden"] = (
            filtros["orden"] if filtros.get("orden") in self.ORDENES else "nombre_asc"
        )
        estados_validos = {value for value, _ in self.ESTADOS_FILTRO}
        tipos_proveedor_validos = {value for value, _ in Proveedor.TipoProveedor.choices}
        tipos_identificacion_validos = {
            value for value, _ in Proveedor.TipoIdentificacion.choices
        }
        relaciones_validas = {value for value, _ in self.RELACIONES_FILTRO}
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        validadores = {
            "estado": lambda value: value in estados_validos,
            "tipo_proveedor": lambda value: value in tipos_proveedor_validos,
            "tipo_identificacion": lambda value: value in tipos_identificacion_validos,
            "pais": lambda value: bool(value),
            "relaciones": lambda value: value in relaciones_validas,
            "cols": lambda value: value in columnas_validas,
        }
        for field in self.FILTER_MULTI_FIELDS:
            values = filtros.get(field, [])
            if isinstance(values, str):
                values = [value for value in values.split(",") if value]
            filtros[field] = list(
                dict.fromkeys(
                    str(value).strip()
                    for value in values
                    if str(value).strip() and validadores[field](str(value).strip())
                )
            )
        return filtros

    def _filters_from_request(self):
        source = self.request.GET
        filtros = {
            field: (source.get(field, "") or "").strip()
            for field in self.FILTER_FIELDS
        }
        filtros["orden"] = filtros["orden"] or "nombre_asc"
        for field in self.FILTER_MULTI_FIELDS:
            filtros[field] = source.getlist(field)
        return self._sanitize_filters(filtros)

    def _has_filter_params(self):
        return any(
            field in self.request.GET
            for field in (*self.FILTER_FIELDS, *self.FILTER_MULTI_FIELDS)
        )

    def get_active_filters(self):
        if hasattr(self, "_active_filters"):
            return self._active_filters

        if self.request.GET.get("reset") == "1":
            self.request.session.pop(self.FILTER_SESSION_KEY, None)
            self.request.session.modified = True
            self._active_filters = self._default_filters()
            return self._active_filters

        if self._has_filter_params():
            self._active_filters = self._filters_from_request()
            self.request.session[self.FILTER_SESSION_KEY] = self._active_filters
            self.request.session.modified = True
            return self._active_filters

        filtros_guardados = self.request.session.get(self.FILTER_SESSION_KEY, {})
        self._active_filters = self._sanitize_filters(
            filtros_guardados if isinstance(filtros_guardados, dict) else {}
        )
        return self._active_filters

    def build_filter_querydict(self, filtros=None):
        filtros = filtros or self.get_active_filters()
        params = QueryDict("", mutable=True)
        if filtros["q"]:
            params["q"] = filtros["q"]
        for field in self.FILTER_MULTI_FIELDS:
            values = filtros[field]
            if field == "cols" and (not values or values == self.COLUMNAS_POR_DEFECTO):
                continue
            params.setlist(field, values)
        if filtros["orden"] != "nombre_asc":
            params["orden"] = filtros["orden"]
        return params

    def get_selected_columns(self):
        seleccionadas = self.get_active_filters()["cols"]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def get_queryset(self):
        filtros = self.get_active_filters()
        queryset = Proveedor.objects.annotate(
            activos_count=Count("activos", distinct=True),
            facturas_count=Count("facturas", distinct=True),
        )
        q = filtros["q"]
        if q:
            queryset = queryset.filter(
                Q(identificacion__icontains=q) | Q(razon_social__icontains=q)
                | Q(nombre_comercial__icontains=q) | Q(nombre_contacto__icontains=q)
            )

        estados = filtros["estado"]
        if estados and set(estados) != {"activo", "inactivo"}:
            queryset = queryset.filter(activo="activo" in estados)
        if filtros["tipo_proveedor"]:
            queryset = queryset.filter(tipo_proveedor__in=filtros["tipo_proveedor"])
        if filtros["tipo_identificacion"]:
            queryset = queryset.filter(tipo_identificacion__in=filtros["tipo_identificacion"])
        if filtros["pais"]:
            queryset = queryset.filter(pais__in=filtros["pais"])

        relaciones = filtros["relaciones"]
        if "con_activos" in relaciones and "sin_activos" not in relaciones:
            queryset = queryset.filter(activos_count__gt=0)
        elif "sin_activos" in relaciones and "con_activos" not in relaciones:
            queryset = queryset.filter(activos_count=0)
        if "con_facturas" in relaciones and "sin_facturas" not in relaciones:
            queryset = queryset.filter(facturas_count__gt=0)
        elif "sin_facturas" in relaciones and "con_facturas" not in relaciones:
            queryset = queryset.filter(facturas_count=0)

        return queryset.order_by(*self.ORDENES[filtros["orden"]])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.get_active_filters()
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 1
        context["busqueda"] = filtros["q"]
        context["estado_seleccionado"] = filtros["estado"][0] if filtros["estado"] else ""
        context["estados_seleccionados"] = filtros["estado"]
        context["tipos_proveedor_seleccionados"] = filtros["tipo_proveedor"]
        context["tipos_identificacion_seleccionados"] = filtros["tipo_identificacion"]
        context["paises_seleccionados"] = filtros["pais"]
        context["relaciones_seleccionadas"] = filtros["relaciones"]
        context["orden_seleccionado"] = filtros["orden"]
        context["estados_filtro"] = self.ESTADOS_FILTRO
        context["tipos_proveedor"] = Proveedor.TipoProveedor.choices
        context["tipos_identificacion"] = Proveedor.TipoIdentificacion.choices
        context["relaciones_filtro"] = self.RELACIONES_FILTRO
        context["ordenes_disponibles"] = self.ORDENES_CHOICES
        context["paises"] = (
            Proveedor.objects.exclude(pais="")
            .order_by("pais")
            .values_list("pais", flat=True)
            .distinct()
        )
        context["cantidad_filtros_activos"] = (
            bool(filtros["q"])
            + sum(len(filtros[field]) for field in self.FILTER_MULTI_FIELDS if field != "cols")
            + (filtros["orden"] != "nombre_asc")
        )
        context["query_string"] = self.build_filter_querydict(filtros).urlencode()
        if context.get("is_paginated"):
            context["page_numbers"] = context["paginator"].get_elided_page_range(context["page_obj"].number)
        return context


class ProveedorCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "proveedores.add_proveedor"
    raise_exception = True
    model = Proveedor
    form_class = ProveedorForm
    template_name = "proveedores/formulario.html"
    success_url = reverse_lazy("proveedores:lista")

    def form_valid(self, form):
        response = super().form_valid(form)
        NotificationService.proveedor_guardado(
            self.object, self.request.user, creado=True
        )
        messages.success(self.request, "Proveedor registrado correctamente.")
        return response


class ProveedorUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "proveedores.change_proveedor"
    raise_exception = True
    model = Proveedor
    form_class = ProveedorForm
    template_name = "proveedores/formulario.html"

    def form_valid(self, form):
        cambios = set(form.changed_data) & {
            "identificacion",
            "razon_social",
            "nombre_comercial",
            "nombre_contacto",
            "correo_electronico",
            "telefono",
            "direccion",
            "ciudad",
            "pais",
        }
        response = super().form_valid(form)
        NotificationService.proveedor_guardado(
            self.object, self.request.user, cambios=cambios
        )
        messages.success(self.request, "Proveedor actualizado correctamente.")
        return response

    def get_success_url(self):
        return reverse("proveedores:detalle", args=[self.object.pk])


class ProveedorDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "proveedores.view_proveedor"
    raise_exception = True
    model = Proveedor
    template_name = "proveedores/detalle.html"
    context_object_name = "proveedor"

    def get_queryset(self):
        return Proveedor.objects.annotate(
            activos_count=Count("activos", distinct=True),
            facturas_count=Count("facturas", distinct=True),
        ).prefetch_related("facturas__empresa", "facturas__activos")


class ProveedorEstadoView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "proveedores.change_proveedor_status"
    raise_exception = True

    def post(self, request, pk):
        proveedor = get_object_or_404(Proveedor, pk=pk)
        proveedor.activo = not proveedor.activo
        proveedor.save(update_fields=["activo", "updated_at"])
        NotificationService.proveedor_guardado(
            proveedor, request.user, cambios={"activo"}
        )
        accion = "activado" if proveedor.activo else "desactivado"
        messages.success(request, f"Proveedor {accion} correctamente.")
        return HttpResponseRedirect(reverse("proveedores:detalle", args=[pk]))


class ProveedorDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = "proveedores.delete_proveedor"
    raise_exception = True
    model = Proveedor
    template_name = "proveedores/confirmar_eliminar.html"
    success_url = reverse_lazy("proveedores:lista")

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "No se puede eliminar el proveedor porque tiene activos o facturas relacionados. Desactivalo en su lugar.")
            return HttpResponseRedirect(reverse("proveedores:detalle", args=[self.object.pk]))
        messages.success(self.request, "Proveedor eliminado correctamente.")
        return response
