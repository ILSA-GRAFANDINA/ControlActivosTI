from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseRedirect
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

    def get_selected_columns(self):
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        seleccionadas = [
            columna for columna in self.request.GET.getlist("cols")
            if columna in columnas_validas
        ]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def get_queryset(self):
        queryset = Proveedor.objects.annotate(activos_count=Count("activos", distinct=True))
        q = self.request.GET.get("q", "").strip()
        if q:
            queryset = queryset.filter(
                Q(identificacion__icontains=q) | Q(razon_social__icontains=q)
                | Q(nombre_comercial__icontains=q) | Q(nombre_contacto__icontains=q)
            )
        estado = self.request.GET.get("estado", "").strip()
        if estado in {"activo", "inactivo"}:
            queryset = queryset.filter(activo=estado == "activo")
        return queryset.order_by("razon_social", "identificacion")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 1
        context["busqueda"] = self.request.GET.get("q", "").strip()
        context["estado_seleccionado"] = self.request.GET.get("estado", "").strip()
        params = self.request.GET.copy()
        params.pop("page", None)
        context["query_string"] = params.urlencode()
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
