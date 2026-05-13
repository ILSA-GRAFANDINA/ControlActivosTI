from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView

from apps.asignaciones.models import AsignacionDetalle
from apps.catalogos.models import EstadoActivo, TipoActivo

from .forms import ActivoAdminForm, FotoActivoCreateFormSet
from .models import Activo, EventoActivo, FotoActivo


class ActivoListView(LoginRequiredMixin, ListView):
    model = Activo
    template_name = "activos/lista.html"
    context_object_name = "activos"

    COLUMNAS_DISPONIBLES = [
        ("codigo", "Código"),
        ("tipo_activo", "Tipo"),
        ("marca", "Marca"),
        ("modelo", "Modelo"),
        ("serie", "Serie"),
        ("cpu", "CPU"),
        ("ram", "RAM"),
        ("disco", "Disco"),
        ("sistema_operativo", "Sistema operativo"),
        ("fecha_compra", "Fecha de compra"),
        ("valor", "Valor"),
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
        queryset = (
            Activo.objects.select_related("tipo_activo", "estado_activo")
            .prefetch_related("fotos")
            .order_by("tipo_activo__nombre", "codigo")
        )

        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            queryset = queryset.filter(
                Q(codigo__icontains=busqueda)
                | Q(marca__icontains=busqueda)
                | Q(modelo__icontains=busqueda)
                | Q(serie__icontains=busqueda)
            )

        estado_id = self.request.GET.get("estado", "").strip()
        if estado_id.isdigit():
            queryset = queryset.filter(estado_activo_id=estado_id)

        tipo_id = self.request.GET.get("tipo", "").strip()
        if tipo_id.isdigit():
            queryset = queryset.filter(tipo_activo_id=tipo_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 1
        context["busqueda"] = self.request.GET.get("q", "").strip()
        context["estado_seleccionado"] = self.request.GET.get("estado", "").strip()
        context["tipo_seleccionado"] = self.request.GET.get("tipo", "").strip()
        context["estados_activo"] = EstadoActivo.objects.filter(activo=True).order_by("nombre")
        context["tipos_activo"] = TipoActivo.objects.filter(activo=True).order_by("nombre")
        return context


class ActivoCreateView(LoginRequiredMixin, CreateView):
    model = Activo
    form_class = ActivoAdminForm
    template_name = "activos/formulario.html"
    context_object_name = "activo"

    def get_formset(self, data=None, files=None):
        kwargs = {
            "queryset": FotoActivo.objects.none(),
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
        context["volver_url"] = reverse("activos:lista")
        return context

    def post(self, request, *args, **kwargs):
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
        context["admin_change_url"] = reverse("admin:activos_activo_change", args=[activo.pk])
        context["fotos_activo"] = list(activo.fotos.all())
        context["historial_asignaciones"] = historial_reciente
        context["historial_asignaciones_completo"] = historial_completo
        context["total_historial_asignaciones"] = len(detalles_asignacion)
        context["historial_eventos"] = list(activo.eventos.all())
        return context
