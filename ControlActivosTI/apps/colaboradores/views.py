from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

from apps.activos.models import FotoActivo
from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.catalogos.models import Area, Empresa, Ubicacion

from .forms import ColaboradorForm
from .models import Colaborador

ASIGNACIONES_ABIERTAS = [
    Asignacion.EstadoAsignacion.ACTIVA,
    Asignacion.EstadoAsignacion.PARCIAL,
]


class ColaboradorListView(LoginRequiredMixin, ListView):
    model = Colaborador
    template_name = "colaboradores/lista.html"
    context_object_name = "colaboradores"
    paginate_by = 10

    COLUMNAS_DISPONIBLES = [
        ("apellidos", "Apellidos"),
        ("nombres", "Nombres"),
        ("cedula", "Cédula"),
        ("correo_corporativo", "Correo"),
        ("empresa", "Empresa"),
        ("area", "Área"),
        ("cargo", "Cargo"),
        ("ubicacion", "Ubicación"),
        ("estado", "Estado"),
        ("activos_asignados", "Activos asignados"),
        ("fecha_ingreso", "Fecha de ingreso"),
    ]

    COLUMNAS_POR_DEFECTO = [
        "apellidos",
        "nombres",
        "cedula",
        "empresa",
        "area",
        "cargo",
        "estado",
    ]

    def get_selected_columns(self):
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        seleccionadas = [
            col for col in self.request.GET.getlist("cols") if col in columnas_validas
        ]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def get_queryset(self):
        queryset = (
            Colaborador.objects.select_related("empresa", "area", "cargo", "ubicacion")
            .annotate(
                activos_asignados_count=Count(
                    "asignaciones__detalles",
                    filter=Q(
                        asignaciones__estado_asignacion__in=ASIGNACIONES_ABIERTAS,
                        asignaciones__detalles__activa=True,
                    ),
                    distinct=True,
                )
            )
            .order_by("empresa__nombre", "apellidos", "nombres")
        )

        busqueda = self.request.GET.get("q", "").strip()
        if busqueda:
            queryset = queryset.filter(
                Q(nombres__icontains=busqueda)
                | Q(apellidos__icontains=busqueda)
                | Q(cedula__icontains=busqueda)
                | Q(correo_corporativo__icontains=busqueda)
            )

        estado = self.request.GET.get("estado", "").strip()
        estados_validos = {choice[0] for choice in Colaborador.EstadoColaborador.choices}
        if estado in estados_validos:
            queryset = queryset.filter(estado=estado)

        empresa_id = self.request.GET.get("empresa", "").strip()
        if empresa_id.isdigit():
            queryset = queryset.filter(empresa_id=empresa_id)

        area_id = self.request.GET.get("area", "").strip()
        if area_id.isdigit():
            queryset = queryset.filter(area_id=area_id)

        ubicacion_id = self.request.GET.get("ubicacion", "").strip()
        if ubicacion_id.isdigit():
            queryset = queryset.filter(ubicacion_id=ubicacion_id)

        activos = self.request.GET.get("activos", "").strip()
        if activos == "con":
            queryset = queryset.filter(activos_asignados_count__gt=0)
        elif activos == "sin":
            queryset = queryset.filter(activos_asignados_count=0)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        # El identificador visual es una columna fija, fuera del selector.
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 1
        context["busqueda"] = self.request.GET.get("q", "").strip()
        context["estado_seleccionado"] = self.request.GET.get("estado", "").strip()
        context["empresa_seleccionada"] = self.request.GET.get("empresa", "").strip()
        context["area_seleccionada"] = self.request.GET.get("area", "").strip()
        context["ubicacion_seleccionada"] = self.request.GET.get("ubicacion", "").strip()
        context["activos_seleccionado"] = self.request.GET.get("activos", "").strip()
        context["estados_colaborador"] = Colaborador.EstadoColaborador.choices
        context["empresas"] = Empresa.objects.filter(activo=True).order_by("nombre")
        context["areas"] = Area.objects.filter(activo=True).order_by("nombre")
        context["ubicaciones"] = Ubicacion.objects.filter(activo=True).order_by("nombre")
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


class ColaboradorCreateView(LoginRequiredMixin, CreateView):
    model = Colaborador
    form_class = ColaboradorForm
    template_name = "colaboradores/formulario.html"
    success_url = reverse_lazy("colaboradores:lista")

    def form_valid(self, form):
        self.object = form.save()
        return HttpResponseRedirect(self.get_success_url())


class ColaboradorDetailView(LoginRequiredMixin, DetailView):
    model = Colaborador
    template_name = "colaboradores/detalle.html"
    context_object_name = "colaborador"

    def get_queryset(self):
        detalles_qs = (
            AsignacionDetalle.objects.select_related(
                "activo",
                "activo__tipo_activo",
                "activo__estado_activo",
                "estado_activo_devolucion",
            )
            .prefetch_related(
                Prefetch(
                    "activo__fotos",
                    queryset=FotoActivo.objects.order_by("orden", "id"),
                )
            )
            .order_by("orden", "id")
        )

        asignaciones_qs = (
            Asignacion.objects.select_related(
                "usuario_responsable",
                "usuario_recepcion",
            )
            .prefetch_related(Prefetch("detalles", queryset=detalles_qs))
            .order_by("-fecha_asignacion", "-id")
        )

        return (
            Colaborador.objects.select_related("empresa", "area", "cargo", "ubicacion", "centro_costo")
            .prefetch_related(Prefetch("asignaciones", queryset=asignaciones_qs))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        colaborador = self.object
        context["admin_change_url"] = reverse(
            "admin:colaboradores_colaborador_change",
            args=[colaborador.pk],
        )
        asignaciones = list(colaborador.asignaciones.all())

        detalles_activos_actuales = []
        historial_detalles = []

        for asignacion in asignaciones:
            detalles = list(asignacion.detalles.all())
            historial_detalles.extend(detalles)

            if asignacion.estado_asignacion in ASIGNACIONES_ABIERTAS:
                detalles_activos_actuales.extend(
                    [detalle for detalle in detalles if detalle.activa]
                )

        context["detalles_activos_actuales"] = detalles_activos_actuales
        context["historial_asignaciones"] = historial_detalles
        context["total_activos_asignados"] = len(detalles_activos_actuales)
        context["valor_total_activos_asignados"] = sum(
            (
                detalle.activo.valor or Decimal("0.00")
                for detalle in detalles_activos_actuales
            ),
            Decimal("0.00"),
        )
        context["puede_generar_acta"] = bool(detalles_activos_actuales)
        return context
