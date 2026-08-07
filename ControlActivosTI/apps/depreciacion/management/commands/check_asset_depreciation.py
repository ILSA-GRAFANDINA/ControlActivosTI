import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.activos.models import Activo
from apps.depreciacion.models import EventoNotificacionDepreciacion
from apps.depreciacion.services import (
    DepreciationNotificationService,
    DepreciationService,
    activo_fuera_de_servicio,
)

logger = logging.getLogger("controlactivos")


class Command(BaseCommand):
    help = "Revisa alertas automáticas de depreciación de forma idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--date", dest="evaluation_date")
        parser.add_argument("--batch-size", type=int, default=200)

    def handle(self, *args, **options):
        if options["batch_size"] <= 0:
            raise CommandError("--batch-size debe ser mayor que cero.")
        if options["evaluation_date"]:
            try:
                fecha = datetime.strptime(options["evaluation_date"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--date debe usar el formato YYYY-MM-DD.") from exc
        else:
            fecha = timezone.localdate()

        revisados = creadas = omitidos = errores = eventos_omitidos = 0
        queryset = Activo.objects.select_related(
            "estado_activo", "tipo_activo"
        ).order_by("pk")
        for activo in queryset.iterator(chunk_size=options["batch_size"]):
            revisados += 1
            try:
                if (
                    not activo.activo
                    or not activo.incluir_en_depreciacion
                    or activo_fuera_de_servicio(activo)
                    or activo.valor is None
                    or activo.fecha_compra is None
                ):
                    omitidos += 1
                    continue
                vencidos = DepreciationService.eventos_vencidos(activo, fecha)
                pendientes = [
                    evento
                    for evento in vencidos
                    if not EventoNotificacionDepreciacion.objects.filter(
                        activo=activo,
                        tipo=evento[0],
                        fecha_programada=evento[1],
                    ).exists()
                ]
                if not pendientes:
                    continue
                tipo, fecha_programada = max(pendientes, key=lambda item: item[1])
                eventos_omitidos += max(len(pendientes) - 1, 0)
                creada, _ = DepreciationNotificationService.procesar(
                    activo, tipo, fecha_programada, dry_run=options["dry_run"]
                )
                creadas += int(creada)
                if creada and not options["dry_run"]:
                    EventoNotificacionDepreciacion.objects.bulk_create(
                        [
                            EventoNotificacionDepreciacion(
                                activo=activo,
                                tipo=tipo_omitido,
                                fecha_programada=fecha_omitida,
                                omitido=True,
                            )
                            for tipo_omitido, fecha_omitida in pendientes
                            if (tipo_omitido, fecha_omitida)
                            != (tipo, fecha_programada)
                        ],
                        ignore_conflicts=True,
                    )
            except Exception:
                errores += 1
                logger.exception("Error revisando depreciación activo_id=%s", activo.pk)

        logger.info(
            "Depreciación revisados=%s creadas=%s omitidos=%s "
            "eventos_historicos_omitidos=%s errores=%s dry_run=%s fecha=%s",
            revisados,
            creadas,
            omitidos,
            eventos_omitidos,
            errores,
            options["dry_run"],
            fecha,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Activos revisados: {revisados}; notificaciones creadas: {creadas}; "
                f"omitidos: {omitidos}; eventos históricos omitidos: {eventos_omitidos}; "
                f"errores: {errores}; dry-run: {'sí' if options['dry_run'] else 'no'}."
            )
        )
