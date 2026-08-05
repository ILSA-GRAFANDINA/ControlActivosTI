from datetime import datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
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
    ESTADOS_DEPRECIACION = {
        "Pendiente de configuración",
        "No iniciada",
        "En depreciación",
        "Próximo a cumplir vida útil",
        "Vida útil cumplida",
        "Retirado o dado de baja",
    }

    def get_selected_columns(self):
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        seleccionadas = [
            columna
            for columna in self.request.GET.getlist("cols")
            if columna in columnas_validas
        ]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def fecha_consulta(self):
        try:
            return datetime.strptime(
                self.request.GET.get("fecha", ""), "%Y-%m-%d"
            ).date()
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
            | Q(estado_activo__nombre__icontains="pérdid")
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

    def get_queryset(self):
        qs = Activo.objects.select_related("tipo_activo", "estado_activo").order_by(
            "codigo"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(codigo__icontains=q)
                | Q(marca__icontains=q)
                | Q(modelo__icontains=q)
                | Q(serie__icontains=q)
                | Q(tipo_activo__nombre__icontains=q)
            )
        if self.request.GET.get("solo_vigentes", "1") == "1":
            qs = qs.filter(activo=True)
        qs = self.filtrar_por_estado(
            qs,
            self.request.GET.get("estado", ""),
        )

        self.resumen_tipos = list(
            qs.values("tipo_activo_id", "tipo_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("tipo_activo__nombre")
        )
        tipos_disponibles = {
            str(item["tipo_activo_id"]) for item in self.resumen_tipos
        }
        tab_tipo = (self.request.GET.get(self.TAB_PARAM, "") or "").strip()
        self.tab_tipo_activa = tab_tipo if tab_tipo in tipos_disponibles else ""
        if self.tab_tipo_activa:
            qs = qs.filter(tipo_activo_id=self.tab_tipo_activa)
        return qs

    def construir_tabs_tipo(self):
        parametros_base = self.request.GET.copy()
        parametros_base.pop("page", None)
        parametros_base.pop(self.TAB_PARAM, None)

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
        fecha = self.fecha_consulta()
        estado_filtro = self.request.GET.get("estado", "")
        busqueda = self.request.GET.get("q", "").strip()
        solo_vigentes = self.request.GET.get("solo_vigentes", "1")
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
                "busqueda": busqueda,
                "estado_seleccionado": estado_filtro,
                "solo_vigentes": solo_vigentes,
                "tab_tipo_activa": self.tab_tipo_activa,
                "tabs_tipo": self.construir_tabs_tipo(),
                "columnas_disponibles": self.COLUMNAS_DISPONIBLES,
                "columnas_seleccionadas": columnas_seleccionadas,
                "total_columnas_tabla": len(columnas_seleccionadas) + 1,
                "configuracion_alertas": DepreciationService.configuracion(),
                "totales_reporte": {
                    "costo": costo,
                    "acumulada": acumulada,
                    "valor": valor,
                },
            }
        )
        if context.get("page_obj"):
            query_params = self.request.GET.copy()
            query_params.pop("page", None)
            context["query_string"] = query_params.urlencode()
            context["page_numbers"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number,
                on_each_side=2,
                on_ends=1,
            )
        return context
