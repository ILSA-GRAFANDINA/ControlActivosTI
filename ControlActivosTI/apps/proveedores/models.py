import re
import unicodedata

from django.core.exceptions import ValidationError
from django.db import models


def normalizar_identificacion(valor):
    """Conserva solo letras y numeros para comparar identificaciones de forma estable."""
    return re.sub(r"[^A-Za-z0-9]", "", valor or "").upper()


def es_ecuador(pais):
    valor = unicodedata.normalize("NFKD", pais or "")
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return valor.strip().casefold() in {"ecuador", "ec", "ecu"}


class Proveedor(models.Model):
    class TipoProveedor(models.TextChoices):
        PERSONA = "persona", "Persona"
        EMPRESA = "empresa", "Empresa"

    class TipoIdentificacion(models.TextChoices):
        CEDULA = "cedula", "Cedula"
        RUC = "ruc", "RUC"
        EXTRANJERA = "extranjera", "Identificacion extranjera"

    tipo_proveedor = models.CharField(max_length=10, choices=TipoProveedor.choices)
    tipo_identificacion = models.CharField(max_length=12, choices=TipoIdentificacion.choices)
    identificacion = models.CharField(max_length=40, unique=True, db_index=True)
    razon_social = models.CharField(max_length=180)
    nombre_comercial = models.CharField(max_length=180, blank=True)
    nombre_contacto = models.CharField(max_length=180, blank=True)
    correo_electronico = models.EmailField(blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    direccion = models.CharField(max_length=250, blank=True)
    ciudad = models.CharField(max_length=120, blank=True)
    pais = models.CharField(max_length=100, default="Ecuador")
    activo = models.BooleanField(default=True, db_index=True)
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["razon_social", "identificacion"]
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        permissions = [
            ("change_proveedor_status", "Puede activar o desactivar proveedores"),
        ]

    @property
    def nombre_visible(self):
        return self.nombre_comercial.strip() or self.razon_social

    def __str__(self):
        return self.nombre_visible

    def clean(self):
        super().clean()
        self.identificacion = normalizar_identificacion(self.identificacion)
        self.razon_social = (self.razon_social or "").strip()
        self.nombre_comercial = (self.nombre_comercial or "").strip()
        self.pais = (self.pais or "").strip()

        errores = {}
        if not self.identificacion:
            errores["identificacion"] = "La identificacion es obligatoria."
        if not self.razon_social:
            errores["razon_social"] = "La razon social es obligatoria."

        if es_ecuador(self.pais):
            if self.tipo_identificacion == self.TipoIdentificacion.RUC and not re.fullmatch(r"\d{13}", self.identificacion):
                errores["identificacion"] = "El RUC ecuatoriano debe contener exactamente 13 digitos."
            elif self.tipo_identificacion == self.TipoIdentificacion.CEDULA and not re.fullmatch(r"\d{10}", self.identificacion):
                errores["identificacion"] = "La cedula ecuatoriana debe contener exactamente 10 digitos."

        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        self.identificacion = normalizar_identificacion(self.identificacion)
        self.full_clean()
        return super().save(*args, **kwargs)
