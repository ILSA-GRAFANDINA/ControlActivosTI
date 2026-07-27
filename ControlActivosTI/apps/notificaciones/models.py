from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def is_safe_internal_path(path):
    parsed = urlsplit(path or "")
    return bool(
        path
        and path.startswith("/")
        and not path.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
    )


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        ACTIVO_CREADO = "ACTIVO_CREADO", "Activo creado"
        ACTIVO_CAMBIADO = "ACTIVO_CAMBIADO", "Activo modificado"
        ACTIVO_BAJA = "ACTIVO_BAJA", "Activo dado de baja"
        ASIGNACION_CREADA = "ASIGNACION_CREADA", "Asignación creada"
        ASIGNACION_CAMBIADA = "ASIGNACION_CAMBIADA", "Asignación modificada"
        ASIGNACION_FINALIZADA = "ASIGNACION_FINALIZADA", "Asignación finalizada"
        PROVEEDOR_CREADO = "PROVEEDOR_CREADO", "Proveedor creado"
        PROVEEDOR_CAMBIADO = "PROVEEDOR_CAMBIADO", "Proveedor modificado"
        FACTURA_CREADA = "FACTURA_CREADA", "Factura creada"
        FACTURA_CAMBIADA = "FACTURA_CAMBIADA", "Factura modificada"

    class Entidad(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        ASIGNACION = "ASIGNACION", "Asignación"
        PROVEEDOR = "PROVEEDOR", "Proveedor"
        FACTURA = "FACTURA", "Factura"
        NINGUNA = "NINGUNA", "Sin entidad"

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notificaciones",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="notificaciones_generadas",
        null=True,
        blank=True,
    )
    tipo = models.CharField(max_length=28, choices=Tipo.choices)
    titulo = models.CharField(max_length=100)
    mensaje = models.CharField(max_length=280)
    entidad_tipo = models.CharField(
        max_length=16,
        choices=Entidad.choices,
        default=Entidad.NINGUNA,
    )
    entidad_id = models.PositiveBigIntegerField(null=True, blank=True)
    ruta = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    fingerprint = models.CharField(max_length=64)

    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["destinatario", "read_at", "-created_at"],
                name="notif_dest_read_created_idx",
            ),
            models.Index(
                fields=["destinatario", "-created_at"],
                name="notif_dest_created_idx",
            ),
            models.Index(fields=["tipo"], name="notif_tipo_idx"),
            models.Index(fields=["-created_at"], name="notif_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["destinatario", "fingerprint"],
                name="unique_notif_dest_fingerprint",
            )
        ]
        permissions = [
            ("view_all_notificacion", "Puede consultar el historial administrativo de notificaciones"),
        ]

    def __str__(self):
        return f"{self.destinatario}: {self.titulo}"

    @property
    def leida(self):
        return self.read_at is not None

    @property
    def actor_nombre(self):
        if not self.actor_id:
            return "Usuario no disponible"
        return self.actor.get_full_name().strip() or self.actor.get_username()

    def clean(self):
        super().clean()
        if bool(self.entidad_id) != (self.entidad_tipo != self.Entidad.NINGUNA):
            raise ValidationError("La entidad relacionada está incompleta.")
        if self.ruta:
            if not is_safe_internal_path(self.ruta):
                raise ValidationError({"ruta": "Solo se permiten rutas internas seguras."})
