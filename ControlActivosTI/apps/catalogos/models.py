from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from decimal import Decimal
from datetime import date
import re
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
    NOMBRE_DADO_DE_BAJA = "dado de baja"

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

    def save(self, *args, **kwargs):
        if self.nombre_normalizado == self.NOMBRE_DADO_DE_BAJA:
            self.permite_asignacion = False
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"permite_asignacion"}
        super().save(*args, **kwargs)

    @property
    def nombre_normalizado(self):
        nombre = unicodedata.normalize("NFKD", self.nombre or "")
        nombre = "".join(caracter for caracter in nombre if not unicodedata.combining(caracter))
        return nombre.lower().strip()

    @property
    def es_dado_de_baja(self):
        return self.nombre_normalizado == self.NOMBRE_DADO_DE_BAJA

    @property
    def es_asignable_para_nueva_asignacion(self):
        if not self.permite_asignacion:
            return False
        nombre = self.nombre_normalizado
        return "cuarentena" not in nombre and "repar" not in nombre


class AtributoActivo(models.Model):
    class TipoDato(models.TextChoices):
        TEXTO_CORTO = "texto_corto", "Texto corto"
        TEXTO_LARGO = "texto_largo", "Texto largo"
        TEXTO_PROTEGIDO = "texto_protegido", "Texto protegido"
        ENTERO = "entero", "Numero entero"
        DECIMAL = "decimal", "Numero decimal"
        FECHA = "fecha", "Fecha"
        BOOLEANO = "booleano", "Si / No"
        LISTA = "lista", "Lista de opciones"

    nombre = models.CharField(max_length=100)
    clave = models.SlugField(
        max_length=80,
        unique=True,
        help_text="Clave estable en minusculas, sin espacios. No cambia al editar el nombre.",
    )
    descripcion = models.TextField(blank=True)
    tipo_dato = models.CharField(max_length=20, choices=TipoDato.choices)
    unidad = models.CharField(max_length=30, blank=True)
    activo = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="atributos_activo_creados", null=True, blank=True, editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="atributos_activo_modificados", null=True, blank=True, editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Atributo de activo"
        verbose_name_plural = "Atributos de activos"
        ordering = ["nombre", "clave"]
        permissions = [
            ("manage_asset_attribute_schema", "Puede administrar atributos configurables"),
        ]
        constraints = [
            models.UniqueConstraint(Lower("nombre"), name="unique_nombre_atributo_ci"),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_dato_display()})"

    @property
    def esta_usado(self):
        return self.valores.exists()

    def clean(self):
        super().clean()
        self.clave = self.normalizar_clave(self.clave)
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.clave):
            raise ValidationError(
                {"clave": "Usa letras minusculas, numeros y guion bajo; debe iniciar con una letra."}
            )
        if self.pk:
            anterior = type(self).objects.filter(pk=self.pk).values("clave", "tipo_dato").first()
            if anterior:
                if anterior["clave"] != self.clave:
                    raise ValidationError({"clave": "La clave interna no puede cambiar despues de crear el atributo."})
                if anterior["tipo_dato"] != self.tipo_dato and self.valores.exists():
                    raise ValidationError(
                        {"tipo_dato": "No se puede cambiar el tipo de dato porque el atributo ya contiene valores."}
                    )
        texto_sensible = f"{self.nombre} {self.clave}".lower()
        prohibidas = ("password", "contrasena", "contraseña", "token", "clave_privada", "api_key", "secreto")
        if self.tipo_dato != self.TipoDato.TEXTO_PROTEGIDO and any(palabra in texto_sensible for palabra in prohibidas):
            raise ValidationError(
                {"nombre": "Los atributos normales no pueden almacenar contrasenas, tokens ni secretos."}
            )

    @staticmethod
    def normalizar_clave(valor):
        valor = unicodedata.normalize("NFKD", valor or "")
        valor = "".join(caracter for caracter in valor if not unicodedata.combining(caracter))
        return re.sub(r"[^a-zA-Z0-9]+", "_", valor).strip("_").lower()

    def save(self, *args, **kwargs):
        self.clave = self.normalizar_clave(self.clave)
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.valores.exists():
            raise ValidationError("El atributo contiene valores historicos; desactivalo en lugar de eliminarlo.")
        return super().delete(*args, **kwargs)


class OpcionAtributoActivo(models.Model):
    atributo = models.ForeignKey(
        AtributoActivo, on_delete=models.PROTECT, related_name="opciones",
    )
    clave = models.SlugField(max_length=80)
    nombre = models.CharField(max_length=100)
    orden = models.PositiveSmallIntegerField(default=1)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Opcion de atributo"
        verbose_name_plural = "Opciones de atributos"
        ordering = ["atributo", "orden", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["atributo", "clave"], name="unique_clave_opcion_por_atributo"),
        ]

    def __str__(self):
        return self.nombre

    def clean(self):
        super().clean()
        self.clave = (self.clave or "").strip().lower().replace("-", "_")
        if self.atributo_id and self.atributo.tipo_dato != AtributoActivo.TipoDato.LISTA:
            raise ValidationError({"atributo": "Solo los atributos de tipo lista pueden tener opciones."})

    def save(self, *args, **kwargs):
        self.clave = AtributoActivo.normalizar_clave(self.clave)
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.valores.exists():
            raise ValidationError("La opcion contiene valores historicos; desactivala en lugar de eliminarla.")
        return super().delete(*args, **kwargs)


class TipoActivoAtributo(models.Model):
    tipo_activo = models.ForeignKey(
        TipoActivo, on_delete=models.PROTECT, related_name="configuraciones_atributos",
    )
    atributo = models.ForeignKey(
        AtributoActivo, on_delete=models.PROTECT, related_name="configuraciones_tipo",
    )
    obligatorio = models.BooleanField(default=False)
    orden = models.PositiveSmallIntegerField(default=1)
    valor_predeterminado = models.JSONField(null=True, blank=True)
    texto_ayuda = models.CharField(max_length=255, blank=True)
    unidad = models.CharField(max_length=30, blank=True)
    mostrar_detalle = models.BooleanField(default=True)
    mostrar_actas = models.BooleanField(default=False)
    mostrar_reportes = models.BooleanField(default=False)
    filtrable = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    longitud_maxima = models.PositiveIntegerField(null=True, blank=True)
    valor_minimo = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    valor_maximo = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    validaciones = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="configuraciones_atributos_creadas", null=True, blank=True, editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name="configuraciones_atributos_modificadas", null=True, blank=True, editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuracion de atributo por tipo"
        verbose_name_plural = "Configuraciones de atributos por tipo"
        ordering = ["tipo_activo", "orden", "atributo__nombre"]
        constraints = [
            models.UniqueConstraint(fields=["tipo_activo", "atributo"], name="unique_atributo_por_tipo_activo"),
            models.UniqueConstraint(
                fields=["tipo_activo", "orden"], condition=Q(activo=True),
                name="unique_orden_activo_por_tipo",
            ),
        ]

    def __str__(self):
        return f"{self.tipo_activo} - {self.atributo}"

    @property
    def unidad_efectiva(self):
        return self.unidad or self.atributo.unidad

    def clean(self):
        super().clean()
        errores = {}
        if self.activo and self.tipo_activo_id:
            limite = int(getattr(settings, "MAX_ATRIBUTOS_ACTIVOS_POR_TIPO", 10))
            existentes = type(self).objects.filter(tipo_activo_id=self.tipo_activo_id, activo=True)
            if self.pk:
                existentes = existentes.exclude(pk=self.pk)
            if existentes.count() >= limite:
                errores["activo"] = f"El tipo ya alcanzo el limite de {limite} atributos activos."
            if self.orden and existentes.filter(orden=self.orden).exists():
                errores["orden"] = (
                    f"El orden {self.orden} ya esta ocupado por otro atributo activo "
                    f"de {self.tipo_activo}."
                )
        if self.valor_minimo is not None and self.valor_maximo is not None:
            if Decimal(self.valor_minimo) > Decimal(self.valor_maximo):
                errores["valor_maximo"] = "El valor maximo no puede ser menor al valor minimo."
        if self.longitud_maxima and self.atributo_id and self.atributo.tipo_dato not in {
            AtributoActivo.TipoDato.TEXTO_CORTO,
            AtributoActivo.TipoDato.TEXTO_LARGO,
            AtributoActivo.TipoDato.TEXTO_PROTEGIDO,
        }:
            errores["longitud_maxima"] = "La longitud maxima solo aplica a atributos de texto."
        if not isinstance(self.validaciones, dict):
            errores["validaciones"] = "Las validaciones adicionales deben ser un objeto JSON."
        predeterminado = self.valor_predeterminado
        if predeterminado is not None and self.atributo_id:
            tipo = self.atributo.tipo_dato
            try:
                if tipo == AtributoActivo.TipoDato.TEXTO_PROTEGIDO:
                    raise ValueError
                if tipo == AtributoActivo.TipoDato.ENTERO:
                    int(predeterminado)
                elif tipo == AtributoActivo.TipoDato.DECIMAL:
                    Decimal(str(predeterminado))
                elif tipo == AtributoActivo.TipoDato.FECHA:
                    date.fromisoformat(str(predeterminado))
                elif tipo == AtributoActivo.TipoDato.BOOLEANO and not isinstance(predeterminado, bool):
                    raise ValueError
                elif tipo == AtributoActivo.TipoDato.LISTA:
                    if not self.atributo.opciones.filter(pk=predeterminado, activo=True).exists():
                        raise ValueError
            except (TypeError, ValueError, ArithmeticError):
                if tipo == AtributoActivo.TipoDato.TEXTO_PROTEGIDO:
                    errores["valor_predeterminado"] = (
                        "Los atributos protegidos no pueden tener valor predeterminado."
                    )
                else:
                    errores["valor_predeterminado"] = "El valor predeterminado no corresponde al tipo de dato."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.tipo_activo_id:
                TipoActivo.objects.select_for_update().get(pk=self.tipo_activo_id)
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.atributo.valores.filter(tipo_activo_origen=self.tipo_activo).exists():
            raise ValidationError(
                "La configuracion tiene valores historicos; desactívala en lugar de eliminarla."
            )
        return super().delete(*args, **kwargs)


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
