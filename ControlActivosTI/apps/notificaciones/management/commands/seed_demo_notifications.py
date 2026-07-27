from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.activos.models import Activo
from apps.notificaciones.models import Notificacion


class Command(BaseCommand):
    help = "Crea dos notificaciones de demostración para un usuario concreto."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=options["username"], is_active=True)
        except User.DoesNotExist as exc:
            raise CommandError("No existe un usuario activo con ese nombre.") from exc

        activos = list(
            Activo.objects.filter(activo=True)
            .only("pk", "codigo", "marca", "modelo")
            .order_by("-created_at", "-pk")[:2]
        )
        examples = [
            {
                "tipo": Notificacion.Tipo.ACTIVO_CREADO,
                "titulo": "Módulo de notificaciones listo",
                "mensaje": "Ya puedes consultar la actividad reciente desde la nueva campana.",
            },
            {
                "tipo": Notificacion.Tipo.ACTIVO_CAMBIADO,
                "titulo": "Vista compacta habilitada",
                "mensaje": "El panel mantiene un tamaño fijo y se adapta a pantallas pequeñas.",
            },
        ]

        for index, example in enumerate(examples):
            activo = activos[index] if index < len(activos) else None
            if activo:
                example.update(
                    {
                        "titulo": f"Actividad del activo {activo.codigo}",
                        "mensaje": f"Revisa la ficha reciente de {activo.marca} {activo.modelo}.",
                        "entidad_tipo": Notificacion.Entidad.ACTIVO,
                        "entidad_id": activo.pk,
                        "ruta": reverse("activos:detalle", args=[activo.pk]),
                    }
                )
            Notificacion.objects.update_or_create(
                destinatario=user,
                fingerprint=f"demo-notification-v2-{index + 1}",
                defaults={
                    "actor": user,
                    "tipo": example["tipo"],
                    "titulo": example["titulo"],
                    "mensaje": example["mensaje"],
                    "entidad_tipo": example.get(
                        "entidad_tipo", Notificacion.Entidad.NINGUNA
                    ),
                    "entidad_id": example.get("entidad_id"),
                    "ruta": example.get("ruta", ""),
                    "read_at": None,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(f"Se prepararon 2 notificaciones para {user.username}.")
        )
