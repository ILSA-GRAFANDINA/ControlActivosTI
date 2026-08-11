from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q
from django.urls import reverse
from django.http import HttpResponseRedirect, JsonResponse, QueryDict
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.activos.models import FotoActivo
from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.catalogos.models import Area, Cargo, Empresa, Ubicacion

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

    FILTER_SESSION_KEY = "colaboradores_filtros_guardados"
    FILTER_FIELDS = ("q", "fecha_desde", "fecha_hasta", "orden")
    FILTER_MULTI_FIELDS = (
        "estado",
        "empresa",
        "area",
        "cargo",
        "ubicacion",
        "activos",
        "cols",
    )
    ACTIVOS_FILTRO = (
        ("con", "Con activos"),
        ("sin", "Sin activos"),
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
        for field in ("q", "fecha_desde", "fecha_hasta"):
            filtros[field] = (filtros.get(field, "") or "").strip()
        filtros["orden"] = (
            filtros["orden"] if filtros.get("orden") in self.ORDENES else "nombre_asc"
        )

        estados_validos = {choice[0] for choice in Colaborador.EstadoColaborador.choices}
        activos_validos = {value for value, _ in self.ACTIVOS_FILTRO}
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        validadores = {
            "estado": lambda value: value in estados_validos,
            "empresa": lambda value: value == "sin_empresa" or value.isdigit(),
            "area": str.isdigit,
            "cargo": str.isdigit,
            "ubicacion": str.isdigit,
            "activos": lambda value: value in activos_validos,
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

    def get_selected_columns(self):
        seleccionadas = self.get_active_filters()["cols"]
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

    def get_selected_companies(self, summary):
        return self.get_active_filters()["empresa"]

    def build_company_tabs(self, summary):
        base_params = self.build_filter_querydict(exclude={"empresa"})
        base_url = reverse("colaboradores:lista")

        def build_url(empresa_id=""):
            params = base_params.copy()
            if empresa_id:
                params.setlist("empresa", [empresa_id])
            query_string = params.urlencode()
            return f"{base_url}?{query_string}" if query_string else base_url

        tabs = [
            {
                "id": "",
                "nombre": "Todos",
                "total": sum(item["total"] for item in summary),
                "activa": not self.empresas_seleccionadas,
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
                    "activa": self.empresas_seleccionadas == [empresa_id],
                    "url": build_url(empresa_id),
                }
            )
        return tabs

    def build_filter_querydict(self, filtros=None, exclude=None):
        filtros = filtros or self.get_active_filters()
        exclude = exclude or set()
        params = QueryDict("", mutable=True)
        if "q" not in exclude and filtros["q"]:
            params["q"] = filtros["q"]
        for field in self.FILTER_MULTI_FIELDS:
            if field in exclude:
                continue
            values = filtros[field]
            if field == "cols" and (not values or values == self.COLUMNAS_POR_DEFECTO):
                continue
            params.setlist(field, values)
        for field in ("fecha_desde", "fecha_hasta"):
            if field not in exclude and filtros[field]:
                params[field] = filtros[field]
        if "orden" not in exclude and filtros["orden"] != "nombre_asc":
            params["orden"] = filtros["orden"]
        return params

    def get_queryset(self):
        filtros = self.get_active_filters()
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

        busqueda = filtros["q"]
        if busqueda:
            queryset = queryset.filter(
                Q(nombres__icontains=busqueda)
                | Q(apellidos__icontains=busqueda)
                | Q(cedula__icontains=busqueda)
                | Q(correo_corporativo__icontains=busqueda)
            )

        if filtros["estado"]:
            queryset = queryset.filter(estado__in=filtros["estado"])

        if filtros["area"]:
            queryset = queryset.filter(area_id__in=filtros["area"])

        if filtros["cargo"]:
            queryset = queryset.filter(cargo_id__in=filtros["cargo"])

        if filtros["ubicacion"]:
            queryset = queryset.filter(ubicacion_id__in=filtros["ubicacion"])

        activos = filtros["activos"]
        if activos and set(activos) != {"con", "sin"}:
            if "con" in activos:
                queryset = queryset.filter(activos_asignados_count__gt=0)
            elif "sin" in activos:
                queryset = queryset.filter(activos_asignados_count=0)

        fecha_desde = parse_date(filtros["fecha_desde"])
        if fecha_desde:
            queryset = queryset.filter(fecha_ingreso__gte=fecha_desde)

        fecha_hasta = parse_date(filtros["fecha_hasta"])
        if fecha_hasta:
            queryset = queryset.filter(fecha_ingreso__lte=fecha_hasta)

        self.company_tab_summary = self.get_company_tab_summary(queryset)
        self.empresas_seleccionadas = self.get_selected_companies(self.company_tab_summary)
        empresas_normales = [
            empresa for empresa in self.empresas_seleccionadas if empresa != "sin_empresa"
        ]
        incluye_sin_empresa = "sin_empresa" in self.empresas_seleccionadas
        if empresas_normales and incluye_sin_empresa:
            queryset = queryset.filter(
                Q(empresa_id__in=empresas_normales) | Q(empresa__isnull=True)
            )
        elif incluye_sin_empresa:
            queryset = queryset.filter(empresa__isnull=True)
        elif empresas_normales:
            queryset = queryset.filter(empresa_id__in=empresas_normales)

        orden = filtros["orden"]
        campos_orden = self.ORDENES.get(orden, self.ORDENES["nombre_asc"])

        return queryset.order_by(*campos_orden)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.get_active_filters()
        columnas_seleccionadas = self.get_selected_columns()
        context["columnas_disponibles"] = self.COLUMNAS_DISPONIBLES
        context["columnas_seleccionadas"] = columnas_seleccionadas
        # El identificador visual es una columna fija, fuera del selector.
        context["total_columnas_tabla"] = len(columnas_seleccionadas) + 1
        context["busqueda"] = filtros["q"]
        context["estado_seleccionado"] = filtros["estado"][0] if filtros["estado"] else ""
        context["estados_seleccionados"] = filtros["estado"]
        context["empresa_seleccionada"] = (
            self.empresas_seleccionadas[0] if self.empresas_seleccionadas else ""
        )
        context["empresas_seleccionadas"] = self.empresas_seleccionadas
        context["tabs_empresa"] = self.build_company_tabs(self.company_tab_summary)
        context["area_seleccionada"] = filtros["area"][0] if filtros["area"] else ""
        context["areas_seleccionadas"] = filtros["area"]
        context["cargo_seleccionado"] = filtros["cargo"][0] if filtros["cargo"] else ""
        context["cargos_seleccionados"] = filtros["cargo"]
        context["ubicacion_seleccionada"] = filtros["ubicacion"][0] if filtros["ubicacion"] else ""
        context["ubicaciones_seleccionadas"] = filtros["ubicacion"]
        context["activos_seleccionado"] = filtros["activos"][0] if filtros["activos"] else ""
        context["activos_seleccionados"] = filtros["activos"]
        context["fecha_desde"] = filtros["fecha_desde"]
        context["fecha_hasta"] = filtros["fecha_hasta"]
        context["orden_seleccionado"] = filtros["orden"]
        context["ordenes_disponibles"] = self.ORDENES_CHOICES
        context["estados_colaborador"] = Colaborador.EstadoColaborador.choices
        context["activos_filtro"] = self.ACTIVOS_FILTRO
        context["empresas"] = Empresa.objects.filter(activo=True).order_by("nombre")
        context["areas"] = Area.objects.filter(activo=True).order_by("nombre")
        context["cargos"] = Cargo.objects.filter(activo=True).order_by("nombre")
        context["ubicaciones"] = Ubicacion.objects.filter(activo=True).order_by("nombre")
        context["cantidad_filtros_activos"] = (
            bool(filtros["q"])
            + len(filtros["estado"])
            + len(self.empresas_seleccionadas)
            + len(filtros["area"])
            + len(filtros["cargo"])
            + len(filtros["ubicacion"])
            + len(filtros["activos"])
            + bool(filtros["fecha_desde"])
            + bool(filtros["fecha_hasta"])
            + (filtros["orden"] != "nombre_asc")
        )
        context["query_string"] = self.build_filter_querydict(filtros).urlencode()
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
