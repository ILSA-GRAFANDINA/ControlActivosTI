from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.views.generic import TemplateView

from apps.activos.models import Activo
from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.colaboradores.models import Colaborador

ASIGNACIONES_ABIERTAS = [
    Asignacion.EstadoAsignacion.ACTIVA,
    Asignacion.EstadoAsignacion.PARCIAL,
]

ACTIVO_VIGENTE_Q = Q(activo=True)
ESTADO_ASIGNABLE_Q = (
    ACTIVO_VIGENTE_Q
    & Q(estado_activo__permite_asignacion=True)
    & ~Q(estado_activo__nombre__icontains="repar")
    & ~Q(estado_activo__nombre__icontains="cuarentena")
)

ESTADO_ASIGNADO_Q = ACTIVO_VIGENTE_Q & Q(estado_activo__nombre__iexact="Asignado")


class InicioView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/inicio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        activos_vigentes = Activo.objects.filter(activo=True)
        total_activos = activos_vigentes.count()
        total_colaboradores = Colaborador.objects.count()
        total_colaboradores_activos = Colaborador.objects.filter(
            estado=Colaborador.EstadoColaborador.ACTIVO
        ).count()
        asignaciones_activas = Asignacion.objects.filter(
            estado_asignacion__in=ASIGNACIONES_ABIERTAS
        ).count()
        activos_disponibles = activos_vigentes.filter(ESTADO_ASIGNABLE_Q).count()
        activos_asignados = activos_vigentes.filter(ESTADO_ASIGNADO_Q).count()
        valor_total_activos = activos_vigentes.aggregate(total=Sum("valor")).get("total") or 0

        activos_por_estado = list(
            activos_vigentes.values("estado_activo_id", "estado_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "estado_activo__nombre")
        )
        activos_por_tipo = list(
            activos_vigentes.values("tipo_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "tipo_activo__nombre")[:8]
        )
        activos_por_tipo_resumen = list(
            activos_vigentes.values("tipo_activo__nombre")
            .annotate(
                total=Count("id"),
                disponibles=Count("id", filter=ESTADO_ASIGNABLE_Q),
                asignados=Count("id", filter=ESTADO_ASIGNADO_Q),
            )
            .order_by("tipo_activo__nombre")
        )
        activos_por_ceco = list(
            AsignacionDetalle.objects.filter(
                activa=True,
                asignacion__estado_asignacion__in=ASIGNACIONES_ABIERTAS,
                activo__activo=True,
            )
            .values(
                "asignacion__centro_costo__codigo",
                "asignacion__centro_costo__nombre",
            )
            .annotate(total=Count("id"))
            .order_by("-total", "asignacion__centro_costo__codigo")[:10]
        )
        activos_por_empresa = list(
            activos_vigentes.values("empresa__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "empresa__nombre")[:8]
        )

        ultimas_asignaciones = (
            Asignacion.objects.select_related(
                "colaborador",
                "usuario_responsable",
            )
            .prefetch_related("detalles__activo")
            .order_by("-fecha_asignacion", "-id")[:5]
        )

        alertas = [
            {
                "titulo": "Activos listos para asignación",
                "valor": activos_disponibles,
                "tono": "emerald",
                "detalle": "Equipos que pueden entregarse de inmediato.",
            },
            {
                "titulo": "Activos actualmente asignados",
                "valor": activos_asignados,
                "tono": "cyan",
                "detalle": "Inventario que ya está en manos de colaboradores.",
            },
            {
                "titulo": "Colaboradores no activos",
                "valor": total_colaboradores - total_colaboradores_activos,
                "tono": "amber",
                "detalle": "Registros para revisar antes de nuevas asignaciones.",
            },
            {
                "titulo": "Asignaciones activas",
                "valor": asignaciones_activas,
                "tono": "rose",
                "detalle": "Procesos abiertos pendientes de devolución o seguimiento.",
            },
        ]

        context.update(
            {
                "total_activos": total_activos,
                "total_colaboradores": total_colaboradores,
                "total_colaboradores_activos": total_colaboradores_activos,
                "asignaciones_activas": asignaciones_activas,
                "activos_disponibles": activos_disponibles,
                "activos_asignados": activos_asignados,
                "valor_total_activos": valor_total_activos,
                "ultimas_asignaciones": ultimas_asignaciones,
                "alertas": alertas,
                "activos_estado_labels": [
                    item["estado_activo__nombre"] or "Sin estado"
                    for item in activos_por_estado
                ],
                "activos_estado_data": [item["total"] for item in activos_por_estado],
                "activos_estado_ids": [item["estado_activo_id"] for item in activos_por_estado],
                "activos_tipo_labels": [
                    item["tipo_activo__nombre"] for item in activos_por_tipo
                ],
                "activos_tipo_data": [item["total"] for item in activos_por_tipo],
                "activos_tipo_resumen": activos_por_tipo_resumen,
                "cecos_labels": [
                    self._formatear_ceco_label(item) for item in activos_por_ceco
                ],
                "cecos_data": [item["total"] for item in activos_por_ceco],
                "activos_empresa_labels": [
                    item["empresa__nombre"] or "Sin empresa"
                    for item in activos_por_empresa
                ],
                "activos_empresa_data": [
                    item["total"] for item in activos_por_empresa
                ],
            }
        )
        return context

    def _formatear_ceco_label(self, item):
        codigo = item["asignacion__centro_costo__codigo"] or "Sin CECO"
        nombre = item["asignacion__centro_costo__nombre"]
        return f"{codigo} - {nombre}" if nombre else codigo
