from datetime import datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.http import QueryDict
from django.shortcuts import redirect
from django.utils import timezone
from django.views.generic import FormView, ListView

from apps.activos.models import Activo

from .forms import ConfiguracionAlertasForm
from .models import ConfiguracionAlertasDepreciacion
from .services import DepreciationService


class ConfiguracionAlertasView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = "depreciacion/configurar_alertas.html"
    form_class = ConfiguracionAlertasForm

    def test_func(self):
        user = self.request.user
        return (
            user.is_superuser
            or user.has_perm("depreciacion.configure_alertas_depreciacion")
            or user.has_perm("activos.change_activo")
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = ConfiguracionAlertasDepreciacion.obtener()
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "La configuración de alertas fue actualizada.")
        return redirect("depreciacion:configurar-alertas")


class DepreciacionReporteView(LoginRequiredMixin, ListView):
    model = Activo
    template_name = "depreciacion/reporte.html"
    context_object_name = "activos"
    paginate_by = 30
    TAB_PARAM = "tab_tipo"
    FILTER_SESSION_KEY = "depreciacion_filtros_guardados"
    FILTER_FIELDS = ("q", "fecha", "solo_vigentes", "orden", TAB_PARAM)
    FILTER_MULTI_FIELDS = ("estado", "cols")

    COLUMNAS_DISPONIBLES = [
        ("categoria", "Categoría"),
        ("estado", "Estado"),
        ("compra", "Fecha de compra"),
        ("fin_vida_util", "Fin de vida útil"),
        ("avance", "Avance"),
        ("valor_estimado", "Valor estimado"),
        ("proxima_alerta", "Próxima alerta"),
    ]
    COLUMNAS_POR_DEFECTO = [
        "compra",
        "avance",
        "valor_estimado",
        "fin_vida_util",
        "estado",
    ]
    ESTADOS_DEPRECIACION = (
        "Pendiente de configuración",
        "No iniciada",
        "En depreciación",
        "Próximo a cumplir vida útil",
        "Vida útil cumplida",
        "Retirado o dado de baja",
    )
    ORDENES = {
        "codigo": ("codigo",),
        "compra_reciente": ("-fecha_compra", "-id"),
        "compra_antigua": ("fecha_compra", "id"),
        "valor_mayor": ("-valor", "codigo"),
        "valor_menor": ("valor", "codigo"),
    }
    ORDENES_CHOICES = (
        ("codigo", "Código"),
        ("compra_reciente", "Compra m?s reciente"),
        ("compra_antigua", "Compra m?s antigua"),
        ("valor_mayor", "Mayor valor"),
        ("valor_menor", "Menor valor"),
    )

    def _default_filters(self):
        return {
            "q": "",
            "fecha": timezone.localdate().isoformat(),
            "solo_vigentes": "1",
            "orden": "codigo",
            self.TAB_PARAM: "",
            **{field: [] for field in self.FILTER_MULTI_FIELDS},
        }

    def _sanitize_filters(self, filtros):
        filtros = {**self._default_filters(), **(filtros or {})}
        filtros["q"] = (filtros.get("q", "") or "").strip()
        filtros["fecha"] = (filtros.get("fecha", "") or "").strip()
        filtros["solo_vigentes"] = (
            "0" if str(filtros.get("solo_vigentes", "1")).strip() == "0" else "1"
        )
        filtros["orden"] = (
            filtros["orden"] if filtros.get("orden") in self.ORDENES else "codigo"
        )
        filtros[self.TAB_PARAM] = (filtros.get(self.TAB_PARAM, "") or "").strip()

        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        estados_validos = set(self.ESTADOS_DEPRECIACION)
        validadores = {
            "estado": lambda value: value in estados_validos,
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
        filtros["fecha"] = filtros["fecha"] or timezone.localdate().isoformat()
        filtros["solo_vigentes"] = filtros["solo_vigentes"] or "1"
        filtros["orden"] = filtros["orden"] or "codigo"
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

    def build_filter_querydict(self, filtros=None, exclude=None):
        filtros = filtros or self.get_active_filters()
        exclude = exclude or set()
        params = QueryDict("", mutable=True)
        if "q" not in exclude and filtros["q"]:
            params["q"] = filtros["q"]
        if "estado" not in exclude:
            params.setlist("estado", filtros["estado"])
        if "fecha" not in exclude and filtros["fecha"] != timezone.localdate().isoformat():
            params["fecha"] = filtros["fecha"]
        if "solo_vigentes" not in exclude and filtros["solo_vigentes"] == "0":
            params["solo_vigentes"] = "0"
        if "orden" not in exclude and filtros["orden"] != "codigo":
            params["orden"] = filtros["orden"]
        if self.TAB_PARAM not in exclude and filtros[self.TAB_PARAM]:
            params[self.TAB_PARAM] = filtros[self.TAB_PARAM]
        if "cols" not in exclude and filtros["cols"] and filtros["cols"] != self.COLUMNAS_POR_DEFECTO:
            params.setlist("cols", filtros["cols"])
        return params

    def get_selected_columns(self):
        seleccionadas = self.get_active_filters()["cols"]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def fecha_consulta(self):
        filtros = self.get_active_filters()
        try:
            return datetime.strptime(filtros["fecha"], "%Y-%m-%d").date()
        except ValueError:
            return timezone.localdate()

    @staticmethod
    def _ultimo_inicio_que_cumple(fecha_objetivo, meses_alerta=0):
        candidato = fecha_objetivo - relativedelta(months=36 - meses_alerta)

        def fecha_evento(fecha_inicio):
            fecha_fin = fecha_inicio + relativedelta(months=36)
            return fecha_fin - relativedelta(months=meses_alerta)

        while fecha_evento(candidato) > fecha_objetivo:
            candidato -= timedelta(days=1)
        while fecha_evento(candidato + timedelta(days=1)) <= fecha_objetivo:
            candidato += timedelta(days=1)
        return candidato

    def filtrar_por_estado(self, queryset, estado):
        if not estado:
            return queryset
        if estado not in self.ESTADOS_DEPRECIACION:
            return queryset.none()

        fecha = self.fecha_consulta()
        configuracion = DepreciationService.configuracion()
        configurado = Q(valor__isnull=False, fecha_compra__isnull=False)
        fuera_de_servicio = (
            Q(activo=False)
            | Q(estado_activo__nombre__icontains="dado de baja")
            | Q(estado_activo__nombre__icontains="retir")
            | Q(estado_activo__nombre__icontains="vend")
            | Q(estado_activo__nombre__icontains="perdid")
            | Q(estado_activo__nombre__icontains="p?rdid")
            | Q(estado_activo__nombre__icontains="rob")
        )

        if estado == "Pendiente de configuración":
            return queryset.filter(
                Q(valor__isnull=True) | Q(fecha_compra__isnull=True)
            )

        queryset = queryset.filter(configurado)
        if estado == "Retirado o dado de baja":
            return queryset.filter(fuera_de_servicio)

        queryset = queryset.exclude(fuera_de_servicio)
        if estado == "No iniciada":
            return queryset.filter(fecha_compra__gt=fecha)

        limite_fin = self._ultimo_inicio_que_cumple(fecha)
        if estado == "Vida útil cumplida":
            return queryset.filter(fecha_compra__lte=limite_fin)

        limite_alerta = self._ultimo_inicio_que_cumple(
            fecha,
            configuracion.alerta_previa_meses,
        )
        queryset = queryset.filter(
            fecha_compra__lte=fecha,
            fecha_compra__gt=limite_fin,
        )
        if estado == "Próximo a cumplir vida útil":
            return queryset.filter(fecha_compra__lte=limite_alerta)
        return queryset.filter(fecha_compra__gt=limite_alerta)

    def filtrar_por_estados(self, queryset, estados):
        if not estados:
            return queryset
        resultado = queryset.none()
        for estado in estados:
            resultado = resultado | self.filtrar_por_estado(queryset, estado)
        return resultado.distinct()

    def get_queryset(self):
        filtros = self.get_active_filters()
        qs = Activo.objects.select_related("tipo_activo", "estado_activo").filter(
            incluir_en_depreciacion=True,
            modalidad_tenencia=Activo.ModalidadTenencia.PROPIO,
        )
        q = filtros["q"]
        if q:
            qs = qs.filter(
                Q(codigo__icontains=q)
                | Q(marca__icontains=q)
                | Q(modelo__icontains=q)
                | Q(serie__icontains=q)
                | Q(tipo_activo__nombre__icontains=q)
            )
        if filtros["solo_vigentes"] == "1":
            qs = qs.filter(activo=True)
        qs = self.filtrar_por_estados(qs, filtros["estado"])

        self.resumen_tipos = list(
            qs.values("tipo_activo_id", "tipo_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("tipo_activo__nombre")
        )
        tipos_disponibles = {
            str(item["tipo_activo_id"]) for item in self.resumen_tipos
        }
        tab_tipo = filtros[self.TAB_PARAM]
        self.tab_tipo_activa = tab_tipo if tab_tipo in tipos_disponibles else ""
        if self.tab_tipo_activa:
            qs = qs.filter(tipo_activo_id=self.tab_tipo_activa)
        return qs.order_by(*self.ORDENES[filtros["orden"]])

    def construir_tabs_tipo(self):
        parametros_base = self.build_filter_querydict(exclude={self.TAB_PARAM})

        def url_tab(tipo_id=""):
            parametros = parametros_base.copy()
            if tipo_id:
                parametros[self.TAB_PARAM] = str(tipo_id)
            query_string = parametros.urlencode()
            return f"{self.request.path}?{query_string}" if query_string else self.request.path

        return [
            {
                "nombre": "Todos",
                "total": sum(item["total"] for item in self.resumen_tipos),
                "activa": not self.tab_tipo_activa,
                "url": url_tab(),
            },
            *[
                {
                    "nombre": item["tipo_activo__nombre"],
                    "total": item["total"],
                    "activa": self.tab_tipo_activa == str(item["tipo_activo_id"]),
                    "url": url_tab(item["tipo_activo_id"]),
                }
                for item in self.resumen_tipos
            ],
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.get_active_filters()
        fecha = self.fecha_consulta()
        columnas_seleccionadas = self.get_selected_columns()
        filas = []
        for activo in context["activos"]:
            calculo = DepreciationService.calcular(activo, fecha)
            filas.append((activo, calculo))

        costo = acumulada = valor = Decimal("0")
        for activo in self.get_queryset().iterator(chunk_size=500):
            calculo = DepreciationService.calcular(activo, fecha)
            if calculo.configurado:
                costo += calculo.costo_adquisicion
                acumulada += calculo.depreciacion_acumulada
                valor += calculo.valor_contable_estimado

        context.update(
            {
                "filas_depreciacion": filas,
                "fecha_consulta": fecha,
                "busqueda": filtros["q"],
                "estado_seleccionado": filtros["estado"][0] if filtros["estado"] else "",
                "estados_seleccionados": filtros["estado"],
                "solo_vigentes": filtros["solo_vigentes"],
                "orden_seleccionado": filtros["orden"],
                "tab_tipo_activa": self.tab_tipo_activa,
                "tabs_tipo": self.construir_tabs_tipo(),
                "columnas_disponibles": self.COLUMNAS_DISPONIBLES,
                "columnas_seleccionadas": columnas_seleccionadas,
                "total_columnas_tabla": len(columnas_seleccionadas) + 1,
                "estados_depreciacion": self.ESTADOS_DEPRECIACION,
                "ordenes_disponibles": self.ORDENES_CHOICES,
                "cantidad_filtros_activos": (
                    bool(filtros["q"])
                    + len(filtros["estado"])
                    + (filtros["fecha"] != timezone.localdate().isoformat())
                    + (filtros["solo_vigentes"] == "0")
                    + (filtros["orden"] != "codigo")
                ),
                "configuracion_alertas": DepreciationService.configuracion(),
                "totales_reporte": {
                    "costo": costo,
                    "acumulada": acumulada,
                    "valor": valor,
                },
            }
        )
        if context.get("page_obj"):
            context["query_string"] = self.build_filter_querydict(filtros).urlencode()
            context["page_numbers"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number,
                on_each_side=2,
                on_ends=1,
            )
        return context
