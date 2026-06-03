from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
import unicodedata


ceco_codigo_validator = RegexValidator(
    regex=r"^[A-Z0-9][A-Z0-9._-]{1,29}$",
    message="El codigo CECO debe usar mayusculas, numeros, punto, guion o guion bajo.",
)


class Area(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Área"
        verbose_name_plural = "Áreas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Cargo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cargo"
        verbose_name_plural = "Cargos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Empresa(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas de Activos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Ubicacion(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ubicación"
        verbose_name_plural = "Ubicaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class DepartamentoEmpresa(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="departamentos",
    )
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Departamento de empresa"
        verbose_name_plural = "Departamentos de empresa"
        ordering = ["empresa__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nombre"],
                name="unique_departamento_por_empresa",
            )
        ]

    def __str__(self):
        return f"{self.empresa} - {self.nombre}"


class CentroCosto(models.Model):
    class TipoCentroCosto(models.TextChoices):
        OPERATIVO = "OPERATIVO", "Operativo"
        ADMINISTRATIVO = "ADMINISTRATIVO", "Administrativo"
        PROYECTO = "PROYECTO", "Proyecto"
        SERVICIO = "SERVICIO", "Servicio compartido"

    codigo = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        validators=[ceco_codigo_validator],
        help_text="Codigo oficial del centro de costo segun ERP/Finanzas.",
    )
    nombre = models.CharField(max_length=150)
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="centros_costo",
        null=True,
        blank=True,
    )
    padre = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="subcentros",
        null=True,
        blank=True,
        help_text="Permite modelar jerarquia tipo SAP: sociedad, division, area o subcentro.",
    )
    tipo = models.CharField(
        max_length=20,
        choices=TipoCentroCosto.choices,
        default=TipoCentroCosto.OPERATIVO,
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="centros_costo_responsable",
        null=True,
        blank=True,
    )
    departamentos = models.ManyToManyField(
        DepartamentoEmpresa,
        related_name="centros_costo",
        blank=True,
        help_text="Departamentos de la empresa que engloba este CECO.",
    )
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    acepta_asignaciones = models.BooleanField(
        default=True,
        help_text="Si esta desmarcado, no se permite copiar este CECO en nuevas asignaciones.",
    )
    activo = models.BooleanField(default=True)
    descripcion = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Centro de costo"
        verbose_name_plural = "Centros de costo"
        ordering = ["codigo"]
        indexes = [
            models.Index(fields=["codigo", "activo"]),
            models.Index(fields=["empresa", "activo"]),
        ]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

    def clean(self):
        super().clean()

        if self.codigo:
            self.codigo = self.codigo.strip().upper()

        if self.padre_id and self.pk and self.padre_id == self.pk:
            raise ValidationError({"padre": "Un CECO no puede ser padre de si mismo."})

        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({"fecha_fin": "La fecha fin no puede ser anterior a la fecha inicio."})

        if self.padre_id and self.padre and not self.padre.activo:
            raise ValidationError({"padre": "El CECO padre debe estar activo."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def ruta_jerarquia(self):
        nodos = [self.codigo]
        padre = self.padre
        while padre:
            nodos.append(padre.codigo)
            padre = padre.padre
        return " > ".join(reversed(nodos))

    @property
    def departamentos_resumen(self):
        nombres = [departamento.nombre for departamento in self.departamentos.order_by("nombre")]
        return ", ".join(nombres) if nombres else "-"


class TipoActivo(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tipo de activo"
        verbose_name_plural = "Tipos de activo"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class EstadoActivo(models.Model):
    nombre = models.CharField(max_length=50, unique=True)
    descripcion = models.TextField(blank=True)
    permite_asignacion = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Estado de activo"
        verbose_name_plural = "Estados de activo"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def nombre_normalizado(self):
        nombre = unicodedata.normalize("NFKD", self.nombre or "")
        nombre = "".join(caracter for caracter in nombre if not unicodedata.combining(caracter))
        return nombre.lower().strip()

    @property
    def es_asignable_para_nueva_asignacion(self):
        if not self.permite_asignacion:
            return False
        nombre = self.nombre_normalizado
        return "cuarentena" not in nombre and "repar" not in nombre


class TipoEventoActivo(models.Model):
    nombre = models.CharField(max_length=80, unique=True)
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tipo de evento de activo"
        verbose_name_plural = "Tipos de evento de activo"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
