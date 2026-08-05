from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    class Accion(models.TextChoices):
        CREAR = "crear", "Crear"
        MODIFICAR = "modificar", "Modificar"
        ACTIVAR = "activar", "Activar"
        DESACTIVAR = "desactivar", "Desactivar"
        ASOCIAR = "asociar", "Asociar"
        CAMBIAR_TIPO = "cambiar_tipo", "Cambiar tipo"
        MIGRAR = "migrar", "Migrar"
        CONSULTAR_SENSIBLE = "consultar_sensible", "Consultar informacion sensible"

    entidad = models.CharField(max_length=80, db_index=True)
    objeto_id = models.CharField(max_length=64, blank=True, db_index=True)
    accion = models.CharField(max_length=24, choices=Accion.choices, db_index=True)
    resumen = models.CharField(max_length=255)
    detalle = models.JSONField(default=dict, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Registro de auditoria"
        verbose_name_plural = "Registros de auditoria"
        ordering = ["-created_at", "-id"]
        permissions = [
            ("view_attribute_configuration_audit", "Puede ver auditoria de atributos configurables"),
        ]

    def __str__(self):
        return f"{self.get_accion_display()} - {self.entidad} {self.objeto_id}".strip()
