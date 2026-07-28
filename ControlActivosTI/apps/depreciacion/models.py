from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class ConfiguracionAlertasDepreciacion(models.Model):
    alerta_previa_meses = models.PositiveIntegerField(
        default=3,
        help_text="Meses calendario antes de cumplir los 36 meses de vida útil.",
    )
    frecuencia_recordatorio_meses = models.PositiveIntegerField(
        default=6,
        validators=[MinValueValidator(1)],
        help_text="Frecuencia de recordatorios después de cumplir la vida útil.",
    )
    mostrar_valor_residual = models.BooleanField(
        default=False,
        verbose_name="Mostrar valor residual",
        help_text=(
            "Muestra el valor residual en el bloque de depreciación del detalle "
            "de cada activo."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de depreciación"
        verbose_name_plural = "Configuración de depreciación"
        permissions = [
            ("configure_alertas_depreciacion", "Puede configurar alertas de depreciación"),
        ]

    def __str__(self):
        return "Configuración de depreciación"

    def clean(self):
        super().clean()
        if self.frecuencia_recordatorio_meses <= 0:
            raise ValidationError(
                {"frecuencia_recordatorio_meses": "La frecuencia debe ser mayor que cero."}
            )
        if not self.pk and type(self).objects.exists():
            raise ValidationError("Solo puede existir una configuración global.")

    def save(self, *args, **kwargs):
        self.pk = 1
        self.full_clean()
        return super().save(*args, **kwargs)

    @classmethod
    def obtener(cls):
        configuracion = cls.objects.filter(pk=1).first()
        if configuracion:
            return configuracion
        return cls(pk=1, alerta_previa_meses=3, frecuencia_recordatorio_meses=6)


class EventoNotificacionDepreciacion(models.Model):
    class Tipo(models.TextChoices):
        ALERTA = "ASSET_DEPRECIATION_WARNING", "Alerta previa"
        CUMPLIMIENTO = "ASSET_USEFUL_LIFE_COMPLETED", "Vida útil cumplida"
        RECORDATORIO = "ASSET_DEPRECIATED_REMINDER", "Recordatorio posterior"

    activo = models.ForeignKey(
        "activos.Activo",
        on_delete=models.CASCADE,
        related_name="eventos_notificacion_depreciacion",
    )
    tipo = models.CharField(max_length=40, choices=Tipo.choices)
    fecha_programada = models.DateField(db_index=True)
    destinatarios = models.PositiveIntegerField(default=0)
    omitido = models.BooleanField(
        default=False,
        help_text="Evento histórico omitido para evitar envíos masivos atrasados.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha_programada", "-id"]
        verbose_name = "Evento de notificación de depreciación"
        verbose_name_plural = "Eventos de notificación de depreciación"
        constraints = [
            models.UniqueConstraint(
                fields=["activo", "tipo", "fecha_programada"],
                name="unique_evento_depreciacion_programado",
            )
        ]
        indexes = [
            models.Index(fields=["fecha_programada", "tipo"]),
        ]
