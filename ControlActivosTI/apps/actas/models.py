from django.conf import settings
from django.db import models


def ruta_acta_entrega(instance, filename):
    codigo = instance.asignacion.codigo_asignacion if instance.asignacion_id else "sin-asignacion"
    tipo = (instance.tipo or "ENTREGA").lower()
    if instance.devolucion_id:
        return f"actas/{codigo}/{tipo}/{instance.devolucion.codigo_devolucion}/{filename}"
    return f"actas/{codigo}/{tipo}/{filename}"


class ActaEntrega(models.Model):
    class TipoActa(models.TextChoices):
        ENTREGA = "ENTREGA", "Entrega"
        RECEPCION = "RECEPCION", "Recepcion"

    asignacion = models.ForeignKey(
        "asignaciones.Asignacion",
        on_delete=models.CASCADE,
        related_name="actas",
    )
    devolucion = models.ForeignKey(
        "asignaciones.Devolucion",
        on_delete=models.CASCADE,
        related_name="actas",
        null=True,
        blank=True,
    )
    tipo = models.CharField(
        max_length=10,
        choices=TipoActa.choices,
        default=TipoActa.ENTREGA,
        db_index=True,
    )
    archivo = models.FileField(upload_to=ruta_acta_entrega, blank=True, null=True)
    nombre_archivo = models.CharField(max_length=255, blank=True)
    version_plantilla = models.CharField(max_length=20, default="2.0")
    instantanea_datos = models.JSONField(default=dict, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    emitida = models.BooleanField(default=False, db_index=True)
    usuario_generador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="actas_generadas",
    )
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Acta de entrega"
        verbose_name_plural = "Actas de entrega"
        ordering = ["-fecha_generacion", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["asignacion", "tipo"],
                condition=models.Q(tipo="ENTREGA", devolucion__isnull=True),
                name="unique_acta_entrega_por_asignacion",
            ),
            models.UniqueConstraint(
                fields=["devolucion", "tipo"],
                condition=models.Q(tipo="RECEPCION", devolucion__isnull=False),
                name="unique_acta_recepcion_por_devolucion",
            ),
        ]

    def __str__(self):
        if self.devolucion_id:
            codigo = self.devolucion.codigo_devolucion
        else:
            codigo = self.asignacion.codigo_asignacion if self.asignacion_id else "SIN-CODIGO"
        return f"Acta {self.get_tipo_display()} - {codigo}"
