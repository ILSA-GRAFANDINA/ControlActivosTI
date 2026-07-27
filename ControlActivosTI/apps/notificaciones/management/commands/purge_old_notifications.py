import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.notificaciones.models import Notificacion

logger = logging.getLogger("controlactivos")


class Command(BaseCommand):
    help = "Elimina por lotes notificaciones leídas y pendientes que superaron su retención."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        read_days = settings.NOTIFICATIONS_READ_RETENTION_DAYS
        unread_days = settings.NOTIFICATIONS_UNREAD_RETENTION_DAYS
        now = timezone.now()
        expired = Notificacion.objects.filter(
            Q(read_at__isnull=False, created_at__lt=now - timedelta(days=read_days))
            | Q(read_at__isnull=True, created_at__lt=now - timedelta(days=unread_days))
        )
        total = expired.count()
        if options["dry_run"]:
            self.stdout.write(f"Modo simulación: se eliminarían {total} notificaciones.")
            return

        batch_size = max(1, min(options["batch_size"], 10000))
        deleted = 0
        while True:
            ids = list(expired.order_by("pk").values_list("pk", flat=True)[:batch_size])
            if not ids:
                break
            count, _ = Notificacion.objects.filter(pk__in=ids).delete()
            deleted += count
        message = f"Depuración completada: {deleted} notificaciones eliminadas."
        logger.info(message)
        self.stdout.write(self.style.SUCCESS(message))
