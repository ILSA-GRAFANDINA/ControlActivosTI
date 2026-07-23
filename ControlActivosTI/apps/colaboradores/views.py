from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.activos.models import FotoActivo
from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.catalogos.models import Area, Ubicacion

from .forms import (
    ColaboradorForm,
    get_catalogo_rapido_form,
    get_catalogo_rapido_label,
)
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

    ORDENES = {
        "nombre_asc": ("empresa__nombre", "nombres", "apellidos", "id"),
        "nombre_desc": ("empresa__nombre", "-nombres", "-apellidos", "-id"),
        "ingreso_reciente": (
            "empresa__nombre",
            "-fecha_ingreso",
            "nombres",
            "apellidos",
            "id",
        ),
        "ingreso_antiguo": (
            "empresa__nombre",
            "fecha_ingreso",
            "nombres",
            "apellidos",
            "id",
        ),
    }

    ORDENES_CHOICES = [
        ("nombre_asc", "Nombre: A a Z"),
        ("nombre_desc", "Nombre: Z a A"),
        ("ingreso_reciente", "Ingreso más reciente"),
        ("ingreso_antiguo", "Ingreso más antiguo"),
    ]

    COLUMNAS_DISPONIBLES = [
        ("nombre_completo", "Nombre completo"),
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
        "nombre_completo",
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

    def get_company_tab_summary(self, queryset):
        colaboradores_filtrados = Colaborador.objects.filter(
            pk__in=queryset.values("pk")
        )
        return list(
            colaboradores_filtrados.values("empresa_id", "empresa__nombre")
            .annotate(total=Count("pk"))
            .order_by("empresa__nombre")
        )

    def get_selected_company(self, summary):
        empresa_solicitada = self.request.GET.get("empresa", "").strip()
        empresas_disponibles = {
            "sin_empresa" if item["empresa_id"] is None else str(item["empresa_id"])
            for item in summary
        }
        return empresa_solicitada if empresa_solicitada in empresas_disponibles else ""

    def build_company_tabs(self, summary):
        base_params = self.request.GET.copy()
        base_params.pop("page", None)
        base_params.pop("empresa", None)
        base_url = reverse("colaboradores:lista")

        def build_url(empresa_id=""):
            params = base_params.copy()
            if empresa_id:
                params["empresa"] = empresa_id
            query_string = params.urlencode()
            return f"{base_url}?{query_string}" if query_string else base_url

        tabs = [
            {
                "id": "",
                "nombre": "Todos",
                "total": sum(item["total"] for item in summary),
                "activa": not self.empresa_seleccionada,
                "url": build_url(),
            }
        ]
        for item in summary:
            empresa_id = (
                "sin_empresa" if item["empresa_id"] is None else str(item["empresa_id"])
            )
            tabs.append(
                {
                    "id": empresa_id,
                    "nombre": item["empresa__nombre"] or "Sin empresa",
                    "total": item["total"],
                    "activa": self.empresa_seleccionada == empresa_id,
                    "url": build_url(empresa_id),
                }
            )
        return tabs

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

        self.company_tab_summary = self.get_company_tab_summary(queryset)
        self.empresa_seleccionada = self.get_selected_company(self.company_tab_summary)
        if self.empresa_seleccionada == "sin_empresa":
            queryset = queryset.filter(empresa__isnull=True)
        elif self.empresa_seleccionada:
            queryset = queryset.filter(empresa_id=self.empresa_seleccionada)

        orden = self.request.GET.get("orden", "nombre_asc").strip()
        campos_orden = self.ORDENES.get(orden, self.ORDENES["nombre_asc"])

        return queryset.order_by(*campos_orden)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        # El identificador visual es una columna fija, fuera del selector.
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 1
        context["busqueda"] = self.request.GET.get("q", "").strip()
        context["estado_seleccionado"] = self.request.GET.get("estado", "").strip()
        context["empresa_seleccionada"] = self.empresa_seleccionada
        context["tabs_empresa"] = self.build_company_tabs(self.company_tab_summary)
        context["area_seleccionada"] = self.request.GET.get("area", "").strip()
        context["ubicacion_seleccionada"] = self.request.GET.get("ubicacion", "").strip()
        context["activos_seleccionado"] = self.request.GET.get("activos", "").strip()
        orden_solicitado = self.request.GET.get("orden", "nombre_asc").strip()
        context["orden_seleccionado"] = (
            orden_solicitado if orden_solicitado in self.ORDENES else "nombre_asc"
        )
        context["ordenes_disponibles"] = self.ORDENES_CHOICES
        context["estados_colaborador"] = Colaborador.EstadoColaborador.choices
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
        messages.success(
            self.request,
            f"El colaborador {self.object.nombres} {self.object.apellidos} fue registrado correctamente.",
        )
        return HttpResponseRedirect(self.get_success_url())


class ColaboradorCatalogoRapidoCreateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        catalogo = request.POST.get("catalogo", "").strip()
        form_class = get_catalogo_rapido_form(catalogo)
        if form_class is None:
            return JsonResponse(
                {"ok": False, "errors": {"catalogo": ["Catálogo no permitido."]}},
                status=400,
            )

        form = form_class(request.POST)
        if not form.is_valid():
            return JsonResponse(
                {
                    "ok": False,
                    "errors": {
                        field: [str(error) for error in errors]
                        for field, errors in form.errors.items()
                    },
                },
                status=400,
            )

        instance = form.save()
        return JsonResponse(
            {
                "ok": True,
                "catalogo": catalogo,
                "catalogo_label": get_catalogo_rapido_label(catalogo),
                "id": instance.pk,
                "label": str(instance),
            },
            status=201,
        )


class ColaboradorUpdateView(LoginRequiredMixin, UpdateView):
    model = Colaborador
    form_class = ColaboradorForm
    template_name = "colaboradores/formulario.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Los datos de {self.object.nombres} {self.object.apellidos} fueron actualizados correctamente.",
        )
        return response

    def get_success_url(self):
        return reverse("colaboradores:detalle", args=[self.object.pk])


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
        context["editar_url"] = reverse(
            "colaboradores:editar",
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
