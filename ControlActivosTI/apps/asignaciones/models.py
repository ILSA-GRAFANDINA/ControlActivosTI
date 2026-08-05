from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.activos.models import Activo
from apps.catalogos.models import CentroCosto, EstadoActivo
from apps.colaboradores.models import Colaborador


class Asignacion(models.Model):
    class EstadoAsignacion(models.TextChoices):
        ACTIVA = "ACTIVA", "Activa"
        PARCIAL = "PARCIAL", "Parcial"
        CERRADA = "CERRADA", "Cerrada"

    codigo_asignacion = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        db_index=True,
        null=True,
        blank=True,
    )
    colaborador = models.ForeignKey(
        Colaborador,
        on_delete=models.PROTECT,
        related_name="asignaciones",
    )
    centro_costo = models.ForeignKey(
        CentroCosto,
        on_delete=models.PROTECT,
        related_name="asignaciones",
        null=True,
        blank=True,
        editable=False,
        help_text="CECO historico copiado desde el colaborador al crear la asignacion.",
    )
    centro_costo_codigo = models.CharField(max_length=30, blank=True, editable=False, db_index=True)
    centro_costo_nombre = models.CharField(max_length=150, blank=True, editable=False)
    centro_costo_empresa = models.CharField(max_length=100, blank=True, editable=False)
    fecha_asignacion = models.DateField(default=timezone.now)
    observaciones_entrega = models.TextField(blank=True)
    usuario_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="asignaciones_registradas",
    )
    estado_asignacion = models.CharField(
        max_length=10,
        choices=EstadoAsignacion.choices,
        default=EstadoAsignacion.ACTIVA,
    )
    fecha_devolucion = models.DateField(null=True, blank=True)
    observaciones_devolucion = models.TextField(blank=True)
    usuario_recepcion = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="devoluciones_registradas",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Asignación"
        verbose_name_plural = "Asignaciones"
        ordering = ["-fecha_asignacion", "-id"]

    def __str__(self):
        codigo = self.codigo_asignacion or "SIN-CODIGO"
        return f"{codigo} - {self.colaborador}"

    def clean(self):
        super().clean()

        esta_abierta = self.estado_asignacion in {
            self.EstadoAsignacion.ACTIVA,
            self.EstadoAsignacion.PARCIAL,
        }
        esta_activa = self.estado_asignacion == self.EstadoAsignacion.ACTIVA

        if (
            esta_activa
            and self.colaborador_id
            and self.colaborador.estado != Colaborador.EstadoColaborador.ACTIVO
        ):
            raise ValidationError({"colaborador": "Solo se puede asignar a colaboradores activos."})

        ceco = self.centro_costo if self.centro_costo_id else None
        if esta_activa and self.colaborador_id:
            ceco = ceco or getattr(self.colaborador, "centro_costo", None)
            if not ceco:
                raise ValidationError(
                    {"colaborador": "El colaborador debe tener un CECO vigente antes de asignar activos."}
                )

        if esta_activa and ceco and (not ceco.activo or not ceco.acepta_asignaciones):
            raise ValidationError({"centro_costo": "El CECO del colaborador no esta habilitado para asignaciones."})

        if esta_abierta:
            if self.fecha_devolucion:
                raise ValidationError(
                    {"fecha_devolucion": "Una asignación activa no puede tener fecha de devolución."}
                )
            if self.usuario_recepcion_id:
                raise ValidationError(
                    {"usuario_recepcion": "Una asignación activa no debe tener usuario de recepción."}
                )
        elif self.estado_asignacion == self.EstadoAsignacion.CERRADA:
            if not self.fecha_devolucion:
                raise ValidationError({"fecha_devolucion": "Debes indicar la fecha de devolución."})
            if not self.usuario_recepcion_id:
                raise ValidationError(
                    {"usuario_recepcion": "Debes indicar el usuario que recibe los activos."}
                )

    def save(self, *args, **kwargs):
        if self.colaborador_id and not self.centro_costo_id:
            self._copiar_ceco_desde_colaborador()
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            if not self.codigo_asignacion:
                anio = self.fecha_asignacion.year if self.fecha_asignacion else timezone.localdate().year
                codigo = f"ASG-{anio}-{self.pk:05d}"
                Asignacion.objects.filter(pk=self.pk).update(codigo_asignacion=codigo)
                self.codigo_asignacion = codigo

    def _copiar_ceco_desde_colaborador(self):
        ceco = getattr(self.colaborador, "centro_costo", None)
        if not ceco:
            return
        self.centro_costo = ceco
        self.centro_costo_codigo = ceco.codigo
        self.centro_costo_nombre = ceco.nombre
        self.centro_costo_empresa = ceco.empresa.nombre if ceco.empresa_id else ""

    @property
    def centro_costo_snapshot(self):
        if not self.centro_costo_codigo:
            return "-"
        return f"{self.centro_costo_codigo} - {self.centro_costo_nombre}"

    @property
    def nombre_colaborador_completo(self):
        return f"{self.colaborador.nombres} {self.colaborador.apellidos}".strip()

    @property
    def total_activos(self):
        return self.detalles.count()

    @property
    def resumen_activos(self):
        codigos = [detalle.activo.codigo for detalle in self.detalles.select_related("activo")]
        return ", ".join(codigos) if codigos else "-"

    def _acta_por_tipo(self, tipo):
        actas_prefetch = getattr(self, "_prefetched_objects_cache", {}).get("actas")
        if actas_prefetch is not None:
            return next((acta for acta in actas_prefetch if acta.tipo == tipo), None)
        return self.actas.filter(tipo=tipo).first()

    @property
    def acta_entrega(self):
        return self._acta_por_tipo("ENTREGA")

    @property
    def acta_recepcion(self):
        return self._acta_por_tipo("RECEPCION")

    @property
    def total_activos_pendientes(self):
        return self.detalles.filter(activa=True).count()

    @property
    def total_activos_devueltos(self):
        return self.detalles.filter(activa=False).count()

    def recalcular_estado_devolucion(self, guardar=True):
        total = self.detalles.count()
        pendientes = self.detalles.filter(activa=True).count()

        if total and pendientes == 0:
            self.estado_asignacion = self.EstadoAsignacion.CERRADA
            ultima_devolucion = self.devoluciones.order_by("-fecha_devolucion", "-id").first()
            if ultima_devolucion:
                self.fecha_devolucion = ultima_devolucion.fecha_devolucion
                self.usuario_recepcion = ultima_devolucion.usuario_recepcion
                self.observaciones_devolucion = ultima_devolucion.observaciones or ""
        elif total and pendientes < total:
            self.estado_asignacion = self.EstadoAsignacion.PARCIAL
            self.fecha_devolucion = None
            self.usuario_recepcion = None
            self.observaciones_devolucion = ""
        else:
            self.estado_asignacion = self.EstadoAsignacion.ACTIVA
            self.fecha_devolucion = None
            self.usuario_recepcion = None
            self.observaciones_devolucion = ""

        if guardar:
            self.save()
        return self.estado_asignacion


class AsignacionDetalle(models.Model):
    asignacion = models.ForeignKey(
        Asignacion,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    activo = models.ForeignKey(
        Activo,
        on_delete=models.PROTECT,
        related_name="detalles_asignacion",
    )
    orden = models.PositiveIntegerField(default=1)
    observaciones_linea = models.TextField(blank=True)
    activa = models.BooleanField(default=True, db_index=True)
    estado_activo_devolucion = models.ForeignKey(
        EstadoActivo,
        on_delete=models.PROTECT,
        related_name="detalles_asignacion_cerrados",
        null=True,
        blank=True,
    )
    observaciones_devolucion = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Detalle de asignación"
        verbose_name_plural = "Detalles de asignación"
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["activo"],
                condition=Q(activa=True),
                name="unique_detalle_asignacion_activa_por_activo",
            ),
            models.UniqueConstraint(
                fields=["asignacion", "activo"],
                name="unique_activo_por_asignacion",
            ),
        ]

    def __str__(self):
        codigo = self.asignacion.codigo_asignacion or "SIN-CODIGO"
        return f"{codigo} - {self.activo.codigo}"

    def _obtener_estado_asignado(self):
        estado = EstadoActivo.objects.filter(nombre__iexact="Asignado").first()
        if not estado:
            raise ValidationError("Debe existir un estado de activo llamado 'Asignado'.")
        return estado

    def clean(self):
        super().clean()

        if self.activa:
            if self.activo_id and not self.activo.activo:
                raise ValidationError({"activo": "El activo seleccionado está deshabilitado."})

            if self.activo_id and not self.activo.estado_activo.es_asignable_para_nueva_asignacion:
                raise ValidationError({"activo": "El activo seleccionado no está disponible para asignación."})

            existe_otra_activa = AsignacionDetalle.objects.filter(activo_id=self.activo_id, activa=True)
            if self.pk:
                existe_otra_activa = existe_otra_activa.exclude(pk=self.pk)
            if existe_otra_activa.exists():
                raise ValidationError({"activo": "Este activo ya tiene una asignación activa."})

            if self.estado_activo_devolucion_id:
                raise ValidationError(
                    {"estado_activo_devolucion": "Un detalle activo no puede tener estado de devolución."}
                )
        else:
            if not self.estado_activo_devolucion_id:
                raise ValidationError(
                    {"estado_activo_devolucion": "Debes indicar el estado final del activo."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)

            if self.activa:
                estado_asignado = self._obtener_estado_asignado()
                if self.activo.estado_activo_id != estado_asignado.id:
                    Activo.objects.filter(pk=self.activo_id).update(estado_activo=estado_asignado)
                    self.activo.estado_activo = estado_asignado
            elif self.estado_activo_devolucion_id:
                if self.activo.estado_activo_id != self.estado_activo_devolucion_id:
                    Activo.objects.filter(pk=self.activo_id).update(
                        estado_activo=self.estado_activo_devolucion
                    )
                    self.activo.estado_activo = self.estado_activo_devolucion

    @property
    def articulo_acta(self):
        if self.activo_id and self.activo.tipo_activo_id:
            return self.activo.tipo_activo.nombre
        return self.activo.codigo

    @property
    def caracteristicas_acta(self):
        partes = []
        if self.activo.modelo:
            partes.append(f"Modelo: {self.activo.modelo}")
        if self.activo.serie:
            partes.append(f"Serie: {self.activo.serie}")
        from apps.activos.attribute_services import caracteristicas_para_acta
        dinamicas = caracteristicas_para_acta(self.activo)
        if dinamicas:
            partes.extend(dinamicas)
        elif self.activo.cpu:
            partes.append(f"CPU: {self.activo.cpu}")
        if not dinamicas and self.activo.ram:
            partes.append(f"RAM: {self.activo.ram}")
        if not dinamicas and self.activo.disco:
            partes.append(f"Disco: {self.activo.disco}")
        if not dinamicas and self.activo.sistema_operativo:
            partes.append(f"SO: {self.activo.sistema_operativo}")
        return " | ".join(partes) if partes else "-"

    @property
    def observaciones_acta(self):
        partes = []
        if self.activo.observaciones:
            partes.append(self.activo.observaciones.strip())
        if self.observaciones_linea:
            partes.append(self.observaciones_linea.strip())
        if self.asignacion.observaciones_entrega:
            partes.append(self.asignacion.observaciones_entrega.strip())
        return " | ".join([p for p in partes if p]) or "-"

    @property
    def foto_principal(self):
        fotos = list(self.activo.fotos.all())
        return fotos[0] if fotos else None


class Devolucion(models.Model):
    codigo_devolucion = models.CharField(
        max_length=40,
        unique=True,
        editable=False,
        db_index=True,
        null=True,
        blank=True,
    )
    asignacion = models.ForeignKey(
        Asignacion,
        on_delete=models.CASCADE,
        related_name="devoluciones",
    )
    fecha_devolucion = models.DateField(default=timezone.now)
    observaciones = models.TextField(blank=True)
    usuario_recepcion = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="eventos_devolucion_registrados",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Devolucion"
        verbose_name_plural = "Devoluciones"
        ordering = ["-fecha_devolucion", "-id"]

    def __str__(self):
        codigo = self.codigo_devolucion or "SIN-CODIGO"
        return f"{codigo} - {self.asignacion}"

    def clean(self):
        super().clean()
        if self.asignacion_id and self.fecha_devolucion < self.asignacion.fecha_asignacion:
            raise ValidationError(
                {"fecha_devolucion": "La fecha de devolucion no puede ser anterior a la fecha de asignacion."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            if not self.codigo_devolucion:
                codigo = f"DEV-{self.pk:05d}"
                Devolucion.objects.filter(pk=self.pk).update(codigo_devolucion=codigo)
                self.codigo_devolucion = codigo


class DevolucionDetalle(models.Model):
    devolucion = models.ForeignKey(
        Devolucion,
        on_delete=models.CASCADE,
        related_name="detalles",
    )
    detalle_asignacion = models.ForeignKey(
        AsignacionDetalle,
        on_delete=models.PROTECT,
        related_name="devoluciones",
    )
    estado_activo_devolucion = models.ForeignKey(
        EstadoActivo,
        on_delete=models.PROTECT,
        related_name="detalles_devolucion",
    )
    observaciones = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Detalle de devolucion"
        verbose_name_plural = "Detalles de devolucion"
        ordering = ["detalle_asignacion__orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["detalle_asignacion"],
                name="unique_devolucion_por_detalle_asignacion",
            ),
            models.UniqueConstraint(
                fields=["devolucion", "detalle_asignacion"],
                name="unique_detalle_por_devolucion",
            ),
        ]

    def __str__(self):
        return f"{self.devolucion} - {self.detalle_asignacion.activo.codigo}"

    @property
    def activo(self):
        return self.detalle_asignacion.activo

    def clean(self):
        super().clean()

        if self.detalle_asignacion_id and self.devolucion_id:
            if self.detalle_asignacion.asignacion_id != self.devolucion.asignacion_id:
                raise ValidationError(
                    {"detalle_asignacion": "El activo no pertenece a la asignacion de esta devolucion."}
                )

        if self.detalle_asignacion_id and not self.pk and not self.detalle_asignacion.activa:
            raise ValidationError({"detalle_asignacion": "Este activo ya fue devuelto."})

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            detalle = self.detalle_asignacion
            detalle.activa = False
            detalle.estado_activo_devolucion = self.estado_activo_devolucion
            detalle.observaciones_devolucion = self.observaciones
            detalle.save()
            self.devolucion.asignacion.recalcular_estado_devolucion()
