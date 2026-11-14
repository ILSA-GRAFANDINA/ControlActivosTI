from django.core.validators import RegexValidator
from django.db import models

from apps.catalogos.models import Area, Cargo, CentroCosto, Empresa, Ubicacion

cedula_validator = RegexValidator(
    regex=r"^\d{10}$",
    message="La cédula debe tener exactamente 10 dígitos.",
)


class Colaborador(models.Model):
    class EstadoColaborador(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        INACTIVO = "INACTIVO", "Inactivo"
        DESVINCULADO = "DESVINCULADO", "Desvinculado"

    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    cedula = models.CharField(
        max_length=10,
        unique=True,
        validators=[cedula_validator],
        db_index=True,
    )
    correo_corporativo = models.EmailField(unique=True)
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="colaboradores",
        null=True,
        blank=True,
    )
    cargo = models.ForeignKey(
        Cargo,
        on_delete=models.PROTECT,
        related_name="colaboradores",
    )
    area = models.ForeignKey(
        Area,
        on_delete=models.PROTECT,
        related_name="colaboradores",
    )
    ubicacion = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name="colaboradores",
        null=True,
        blank=True,
    )
    centro_costo = models.ForeignKey(
        CentroCosto,
        on_delete=models.PROTECT,
        related_name="colaboradores",
        null=True,
        blank=True,
        help_text="CECO contable vigente del colaborador. Se copia a cada asignación al crearla.",
    )
    estado = models.CharField(
        max_length=15,
        choices=EstadoColaborador.choices,
        default=EstadoColaborador.ACTIVO,
    )
    fecha_ingreso = models.DateField()
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Colaborador"
        verbose_name_plural = "Colaboradores"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.apellidos}, {self.nombres}"
