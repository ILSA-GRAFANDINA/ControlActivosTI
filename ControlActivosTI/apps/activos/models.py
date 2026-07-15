import posixpath
import re
import unicodedata
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Max
from django.utils import timezone
from PIL import Image, ImageOps

from apps.catalogos.models import Empresa, EstadoActivo, TipoActivo, TipoEventoActivo


TIPOS_ACTIVO_CON_ESPECIFICACIONES = (
    "laptop",
    "pc",
    "desktop",
    "escritorio",
    "computador",
    "computadora",
)

TIPOS_ACTIVO_CON_CODIGO_SAP = (
    "laptop",
    "pc",
)

PREFIJOS_TIPOS_ACTIVO = {
    "laptop": "LAP",
    "mouse": "MOU",
    "mousepad": "MOUP",
    "teclado": "TEC",
    "base para laptop": "BLP",
    "pc": "PC",
}

FOTO_VARIANTS = {
    "thumb": 360,
    "medium": 960,
    "large": 1600,
}


def normalizar_nombre_tipo(nombre):
    nombre = unicodedata.normalize("NFKD", nombre or "")
    nombre = "".join(caracter for caracter in nombre if not unicodedata.combining(caracter))
    nombre = re.sub(r"[^a-zA-Z0-9]+", " ", nombre).strip().lower()
    return re.sub(r"\s+", " ", nombre)


def obtener_base_prefijo(nombre):
    nombre_normalizado = normalizar_nombre_tipo(nombre)
    return re.sub(r"[^A-Z0-9]+", "", nombre_normalizado.upper()) or "GEN"


def tipo_activo_requiere_codigo_sap(nombre_tipo):
    nombre_normalizado = normalizar_nombre_tipo(nombre_tipo)
    return nombre_normalizado in TIPOS_ACTIVO_CON_CODIGO_SAP


def ruta_foto_activo(instance, filename):
    codigo = instance.activo.codigo if instance.activo and instance.activo.codigo else "sin-codigo"
    return f"activos/{codigo}/{filename}"


class Activo(models.Model):
    codigo = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
    )
    tipo_activo = models.ForeignKey(
        TipoActivo,
        on_delete=models.PROTECT,
        related_name="activos",
    )
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,
        related_name="activos",
        null=True,
        blank=True,
    )
    proveedor = models.ForeignKey(
        "proveedores.Proveedor",
        on_delete=models.PROTECT,
        related_name="activos",
        null=True,
        blank=True,
        help_text="Proveedor de adquisicion del activo.",
    )
    marca = models.CharField(max_length=80)
    modelo = models.CharField(max_length=80)
    serie = models.CharField(
    max_length=120,
    db_index=True,
    blank=True,
    default="S/N",
    )
    codigo_sap = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        help_text="Codigo SAP unico para laptops y PCs.",
    )
    cpu = models.CharField(max_length=150, blank=True)
    ram = models.CharField(max_length=50, blank=True)
    disco = models.CharField(max_length=80, blank=True)
    sistema_operativo = models.CharField(max_length=50, blank=True, default="")
    fecha_compra = models.DateField(null=True, blank=True)
    valor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Valor de Compra",
        help_text="Ingresa el valor con coma de miles, por ejemplo 10,482.00.",
    )
    estado_activo = models.ForeignKey(
        EstadoActivo,
        on_delete=models.PROTECT,
        related_name="activos",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Desactiva este registro para conservarlo sin incluirlo en los totales vigentes.",
    )
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Activo"
        verbose_name_plural = "Activos"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.marca} {self.modelo}"

    def requiere_codigo_sap(self):
        nombre_tipo = self.tipo_activo.nombre if self.tipo_activo_id else ""
        return tipo_activo_requiere_codigo_sap(nombre_tipo)

    def _obtener_prefijo_tipo(self):
        nombre_tipo = self.tipo_activo.nombre if self.tipo_activo_id else ""
        nombre_normalizado = normalizar_nombre_tipo(nombre_tipo)
        if nombre_normalizado in PREFIJOS_TIPOS_ACTIVO:
            return PREFIJOS_TIPOS_ACTIVO[nombre_normalizado]

        base_prefijo = obtener_base_prefijo(nombre_tipo)
        longitud_inicial = min(3, len(base_prefijo))
        prefijos_reservados = {
            prefijo
            for tipo, prefijo in PREFIJOS_TIPOS_ACTIVO.items()
            if tipo != nombre_normalizado
        }
        prefijos_reservados.add("ACT")

        for longitud in range(longitud_inicial, len(base_prefijo) + 1):
            prefijo = base_prefijo[:longitud]
            if prefijo in prefijos_reservados:
                continue
            existe_en_otro_tipo = Activo.objects.filter(
                codigo__startswith=f"{prefijo}-",
            ).exclude(tipo_activo_id=self.tipo_activo_id).exists()
            if not existe_en_otro_tipo:
                return prefijo

        contador = 2
        prefijo_base = base_prefijo[:13]
        while True:
            prefijo = f"{prefijo_base}{contador}"
            existe_en_otro_tipo = Activo.objects.filter(
                codigo__startswith=f"{prefijo}-",
            ).exclude(tipo_activo_id=self.tipo_activo_id).exists()
            if prefijo not in prefijos_reservados and not existe_en_otro_tipo:
                return prefijo
            contador += 1

    def requiere_especificaciones_tecnicas(self):
        nombre_tipo = (self.tipo_activo.nombre if self.tipo_activo_id else "").strip().lower()
        return any(clave in nombre_tipo for clave in TIPOS_ACTIVO_CON_ESPECIFICACIONES)

    def limpiar_especificaciones_no_aplicables(self):
        if self.requiere_especificaciones_tecnicas():
            return

        self.cpu = ""
        self.ram = ""
        self.disco = ""
        self.sistema_operativo = ""

    def limpiar_codigo_sap_no_aplicable(self):
        if self.requiere_codigo_sap():
            if self.codigo_sap:
                self.codigo_sap = self.codigo_sap.strip().upper()
            return

        self.codigo_sap = None

    def clean(self):
        super().clean()

        if self.codigo_sap:
            self.codigo_sap = self.codigo_sap.strip().upper()
        else:
            self.codigo_sap = None

    def _generar_codigo(self):
        prefijo = self._obtener_prefijo_tipo()
        ultimo = (
            Activo.objects.filter(codigo__startswith=f"{prefijo}-")
            .order_by("-codigo")
            .first()
        )

        if ultimo and ultimo.codigo:
            try:
                ultimo_numero = int(ultimo.codigo.split("-")[-1])
            except (ValueError, IndexError):
                ultimo_numero = 0
        else:
            ultimo_numero = 0

        siguiente_numero = ultimo_numero + 1
        return f"{prefijo}-{siguiente_numero:04d}"

    def save(self, *args, **kwargs):
        if not self.serie or not self.serie.strip():
            self.serie = "S/N"
        self.limpiar_especificaciones_no_aplicables()
        self.limpiar_codigo_sap_no_aplicable()
        if not self.codigo:
            self.codigo = self._generar_codigo()
        self.full_clean()
        super().save(*args, **kwargs)


class FotoActivo(models.Model):
    activo = models.ForeignKey(
        Activo,
        on_delete=models.CASCADE,
        related_name="fotos",
    )
    imagen = models.ImageField(upload_to=ruta_foto_activo)
    descripcion = models.CharField(max_length=255, blank=True)
    orden = models.PositiveSmallIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Foto de activo"
        verbose_name_plural = "Fotos de activos"
        ordering = ["activo", "orden"]
        constraints = [
            models.UniqueConstraint(
                fields=["activo", "orden"],
                name="unique_orden_foto_por_activo",
            )
        ]

    def __str__(self):
        codigo = self.activo.codigo if self.activo_id else "sin-activo"
        return f"Foto {self.orden or '-'} - {codigo}"

    def _source_filename(self):
        if not self.imagen:
            return ""
        return Path(self.imagen.name).name

    def _variant_name(self, variant):
        source_name = self._source_filename()
        if not source_name:
            return ""
        base_name = Path(source_name).stem
        base_dir = posixpath.dirname(self.imagen.name)
        variant_filename = f"{base_name}_{variant}.webp"
        return posixpath.join(base_dir, variant_filename) if base_dir else variant_filename

    def _normalize_image_file(self, max_dimension=1600, quality=88):
        if not self.imagen:
            return None

        self.imagen.file.seek(0)
        with Image.open(self.imagen.file) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode == "P":
                image = image.convert("RGBA")
            elif image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            buffer = BytesIO()
            image.save(buffer, format="WEBP", quality=quality, method=6)
            buffer.seek(0)

        normalized_name = f"{Path(self._source_filename()).stem}.webp"
        return ContentFile(buffer.read(), name=normalized_name)

    def _save_variant_file(self, variant, max_dimension):
        variant_name = self._variant_name(variant)
        if not variant_name or not default_storage.exists(self.imagen.name):
            return ""
        if default_storage.exists(variant_name):
            return variant_name

        with default_storage.open(self.imagen.name, "rb") as source_file:
            with Image.open(source_file) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode == "P":
                    image = image.convert("RGBA")
                elif image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

                buffer = BytesIO()
                image.save(buffer, format="WEBP", quality=82, method=6)
                buffer.seek(0)

        default_storage.save(variant_name, ContentFile(buffer.read()))
        return variant_name

    def _ensure_variant_files(self):
        if not self.imagen:
            return

        for variant, max_dimension in FOTO_VARIANTS.items():
            self._save_variant_file(variant, max_dimension)

    def _delete_related_files(self, source_name):
        if not source_name:
            return

        default_storage.delete(source_name)
        base_name = Path(source_name).stem
        base_dir = posixpath.dirname(source_name)
        for variant in FOTO_VARIANTS:
            variant_filename = f"{base_name}_{variant}.webp"
            variant_name = posixpath.join(base_dir, variant_filename) if base_dir else variant_filename
            default_storage.delete(variant_name)

    def _best_available_image_name(self):
        if not self.imagen or not self.imagen.name:
            return ""

        candidate_names = [
            self.imagen.name,
            self._variant_name("large"),
            self._variant_name("medium"),
            self._variant_name("thumb"),
        ]
        for candidate in candidate_names:
            if candidate and default_storage.exists(candidate):
                return candidate
        return ""

    @property
    def imagen_original_url(self):
        nombre_imagen = self._best_available_image_name()
        return default_storage.url(nombre_imagen) if nombre_imagen else ""

    @property
    def imagen_large_url(self):
        if not self.imagen:
            return ""
        variant_name = self._save_variant_file("large", FOTO_VARIANTS["large"])
        if variant_name:
            return default_storage.url(variant_name)
        nombre_imagen = self._best_available_image_name()
        return default_storage.url(nombre_imagen) if nombre_imagen else ""

    @property
    def imagen_medium_url(self):
        if not self.imagen:
            return ""
        variant_name = self._save_variant_file("medium", FOTO_VARIANTS["medium"])
        if variant_name:
            return default_storage.url(variant_name)
        nombre_imagen = self._best_available_image_name()
        return default_storage.url(nombre_imagen) if nombre_imagen else ""

    @property
    def imagen_thumb_url(self):
        if not self.imagen:
            return ""
        variant_name = self._save_variant_file("thumb", FOTO_VARIANTS["thumb"])
        if variant_name:
            return default_storage.url(variant_name)
        nombre_imagen = self._best_available_image_name()
        return default_storage.url(nombre_imagen) if nombre_imagen else ""

    @property
    def imagen_srcset(self):
        if not self.imagen:
            return ""
        return ", ".join(
            [
                f"{self.imagen_thumb_url} 360w",
                f"{self.imagen_medium_url} 960w",
                f"{self.imagen_large_url} 1600w",
            ]
        )

    @property
    def preview_url(self):
        return self.imagen_thumb_url

    def clean(self):
        super().clean()

        if not self.activo_id:
            return

        fotos_existentes = FotoActivo.objects.filter(activo_id=self.activo_id)
        if self.pk:
            fotos_existentes = fotos_existentes.exclude(pk=self.pk)

        if fotos_existentes.count() >= 5:
            raise ValidationError("Un activo no puede tener más de 5 fotos.")

        if self.orden is not None:
            if fotos_existentes.filter(orden=self.orden).exists():
                raise ValidationError({"orden": "Ya existe una foto con ese orden para este activo."})

    def save(self, *args, **kwargs):
        old_imagen_name = None
        if self.pk:
            old_imagen_name = FotoActivo.objects.filter(pk=self.pk).values_list("imagen", flat=True).first()

        if self.imagen and not getattr(self.imagen, "_committed", True):
            self.imagen = self._normalize_image_file()

        if self.activo_id and not self.orden:
            ultimo_orden = (
                FotoActivo.objects
                .filter(activo_id=self.activo_id)
                .exclude(pk=self.pk)
                .aggregate(max_orden=Max("orden"))
                .get("max_orden") or 0
            )
            self.orden = ultimo_orden + 1

        self.full_clean()
        super().save(*args, **kwargs)
        self._ensure_variant_files()

        if old_imagen_name and old_imagen_name != self.imagen.name:
            self._delete_related_files(old_imagen_name)

    def delete(self, *args, **kwargs):
        source_name = self.imagen.name if self.imagen else ""
        super().delete(*args, **kwargs)
        self._delete_related_files(source_name)


class EventoActivo(models.Model):
    class CampoAfectado(models.TextChoices):
        NINGUNO = "ninguno", "Ninguno"
        CPU = "cpu", "Procesador"
        RAM = "ram", "RAM"
        DISCO = "disco", "Disco"
        SISTEMA_OPERATIVO = "sistema_operativo", "Sistema operativo"

    activo = models.ForeignKey(
        Activo,
        on_delete=models.CASCADE,
        related_name="eventos",
    )
    tipo_evento = models.ForeignKey(
        TipoEventoActivo,
        on_delete=models.PROTECT,
        related_name="eventos",
    )
    fecha_evento = models.DateTimeField(default=timezone.now)
    detalle = models.TextField()
    campo_afectado = models.CharField(
        max_length=30,
        choices=CampoAfectado.choices,
        default=CampoAfectado.NINGUNO,
    )
    valor_anterior = models.CharField(max_length=150, blank=True, editable=False)
    valor_nuevo = models.CharField(
        max_length=150,
        blank=True,
        help_text="Nuevo valor tecnico que se aplicara al activo, por ejemplo 16 GB.",
    )
    costo_adicional = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Costo de repuesto o mejora. No aplica para mantenimiento simple.",
    )
    sumar_costo_al_valor = models.BooleanField(
        default=False,
        help_text="Suma el costo adicional al valor actual del activo.",
    )
    nuevo_estado_activo = models.ForeignKey(
        EstadoActivo,
        on_delete=models.PROTECT,
        related_name="eventos_actualizacion",
        null=True,
        blank=True,
        help_text="Estado que tomara el activo despues del evento, si aplica.",
    )
    usuario_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="eventos_activo_registrados",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento de activo"
        verbose_name_plural = "Eventos de activos"
        ordering = ["-fecha_evento", "-id"]

    def __str__(self):
        return f"{self.activo.codigo} - {self.tipo_evento.nombre}"

    def clean(self):
        super().clean()

        errores = {}
        afecta_campo = self.campo_afectado != self.CampoAfectado.NINGUNO

        if afecta_campo and not (self.valor_nuevo or "").strip():
            errores["valor_nuevo"] = "Ingresa el nuevo valor tecnico que se aplicara al activo."

        if afecta_campo and self.activo_id and not self.activo.requiere_especificaciones_tecnicas():
            errores["campo_afectado"] = "Este tipo de activo no maneja especificaciones tecnicas editables."

        if self.sumar_costo_al_valor and self.costo_adicional in (None, ""):
            errores["costo_adicional"] = "Ingresa el costo adicional que se sumara al valor del activo."

        if self.costo_adicional is not None and self.costo_adicional < 0:
            errores["costo_adicional"] = "El costo adicional no puede ser negativo."

        if errores:
            raise ValidationError(errores)

    def _obtener_valor_actual(self):
        if self.campo_afectado == self.CampoAfectado.NINGUNO or not self.activo_id:
            return ""

        return getattr(self.activo, self.campo_afectado, "") or ""

    def _actualizar_activo(self):
        if not self.activo_id:
            return

        campos_actualizados = []
        if self.campo_afectado != self.CampoAfectado.NINGUNO:
            setattr(self.activo, self.campo_afectado, self.valor_nuevo.strip())
            campos_actualizados.append(self.campo_afectado)

        if self.sumar_costo_al_valor and self.costo_adicional is not None:
            valor_actual = self.activo.valor or 0
            self.activo.valor = valor_actual + self.costo_adicional
            campos_actualizados.append("valor")

        if self.nuevo_estado_activo_id:
            self.activo.estado_activo = self.nuevo_estado_activo
            campos_actualizados.append("estado_activo")

        if campos_actualizados:
            self.activo.save(update_fields=[*campos_actualizados, "updated_at"])

    def save(self, *args, **kwargs):
        es_nuevo = self._state.adding

        if es_nuevo and self.campo_afectado != self.CampoAfectado.NINGUNO and not self.valor_anterior:
            self.valor_anterior = self._obtener_valor_actual()

        self.full_clean()
        super().save(*args, **kwargs)

        if es_nuevo:
            self._actualizar_activo()
