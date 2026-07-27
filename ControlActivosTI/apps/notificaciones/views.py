from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView

from .forms import NotificacionFiltroForm
from .models import Notificacion
from .services import prepare_notifications


class HistorialNotificacionesView(LoginRequiredMixin, ListView):
    model = Notificacion
    template_name = "notificaciones/historial.html"
    context_object_name = "notificaciones"
    paginate_by = 20

    def get_queryset(self):
        queryset = Notificacion.objects.filter(
            destinatario=self.request.user
        ).select_related("actor")
        self.filter_form = NotificacionFiltroForm(self.request.GET)
        if self.filter_form.is_valid():
            data = self.filter_form.cleaned_data
            if data["tipo"]:
                queryset = queryset.filter(tipo=data["tipo"])
            if data["fecha_desde"]:
                queryset = queryset.filter(created_at__date__gte=data["fecha_desde"])
            if data["fecha_hasta"]:
                queryset = queryset.filter(created_at__date__lte=data["fecha_hasta"])
        return queryset.order_by("-created_at", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notificaciones"] = prepare_notifications(context["notificaciones"], self.request.user)
        context["filter_form"] = self.filter_form
        params = self.request.GET.copy()
        params.pop("page", None)
        context["query_string"] = params.urlencode()
        if context.get("is_paginated"):
            context["page_numbers"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number
            )
        return context


class MarcarTodasLeidasView(LoginRequiredMixin, View):
    def post(self, request):
        updated = Notificacion.objects.filter(
            destinatario=request.user,
            read_at__isnull=True,
        ).update(read_at=timezone.now())
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"updated": updated, "unread_count": 0})
        return redirect(request.POST.get("next") or reverse("notificaciones:historial"))


class AbrirNotificacionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(
            Notificacion.objects.select_related("actor"),
            pk=pk,
            destinatario=request.user,
        )
        if not notification.read_at:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        prepare_notifications([notification], request.user)
        return redirect(notification.display_url or reverse("notificaciones:historial"))

