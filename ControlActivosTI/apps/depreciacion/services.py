import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import NotificationService

from .models import ConfiguracionAlertasDepreciacion, EventoNotificacionDepreciacion

logger = logging.getLogger("controlactivos")
VIDA_UTIL_MESES = 36
VALOR_RESIDUAL = Decimal("0.00")


@dataclass(frozen=True)
class ResultadoDepreciacion:
    estado: str
    costo_adquisicion: Decimal | None
    valor_residual: Decimal
    base_depreciable: Decimal
    proporcion: Decimal
    porcentaje_depreciado: Decimal
    depreciacion_acumulada: Decimal
    valor_contable_estimado: Decimal
    fecha_inicio: date | None
    fecha_fin: date | None
    dias_transcurridos: int
    dias_totales: int
    dias_restantes: int
    proxima_alerta: date | None
    configurado: bool


ESTADOS_TERMINALES = ("dado de baja", "retir", "vend", "perdid", "rob")


def activo_fuera_de_servicio(activo):
    if not activo.activo:
        return True
    nombre = getattr(activo.estado_activo, "nombre_normalizado", "")
    return any(fragmento in nombre for fragmento in ESTADOS_TERMINALES)


class DepreciationService:
    @staticmethod
    def configuracion():
        return ConfiguracionAlertasDepreciacion.obtener()

    @classmethod
    def calcular(cls, activo, fecha_consulta=None):
        fecha = fecha_consulta or timezone.localdate()
        configuracion = cls.configuracion()
        costo = activo.valor
        inicio = activo.fecha_compra
        if (
            getattr(activo, "modalidad_tenencia", None) == "ARRENDADO"
            or not activo.incluir_en_depreciacion
        ):
            return ResultadoDepreciacion(
                estado="No depreciable",
                costo_adquisicion=costo,
                valor_residual=VALOR_RESIDUAL,
                base_depreciable=Decimal("0"),
                proporcion=Decimal("0"),
                porcentaje_depreciado=Decimal("0"),
                depreciacion_acumulada=Decimal("0"),
                valor_contable_estimado=costo or Decimal("0"),
                fecha_inicio=inicio,
                fecha_fin=None,
                dias_transcurridos=0,
                dias_totales=0,
                dias_restantes=0,
                proxima_alerta=None,
                configurado=False,
            )
        if costo is None or inicio is None:
            return ResultadoDepreciacion(
                estado="Pendiente de configuración",
                costo_adquisicion=costo,
                valor_residual=VALOR_RESIDUAL,
                base_depreciable=Decimal("0"),
                proporcion=Decimal("0"),
                porcentaje_depreciado=Decimal("0"),
                depreciacion_acumulada=Decimal("0"),
                valor_contable_estimado=costo or Decimal("0"),
                fecha_inicio=inicio,
                fecha_fin=None,
                dias_transcurridos=0,
                dias_totales=0,
                dias_restantes=0,
                proxima_alerta=None,
                configurado=False,
            )

        fin = inicio + relativedelta(months=VIDA_UTIL_MESES)
        dias_totales = max((fin - inicio).days, 1)
        transcurridos_brutos = (fecha - inicio).days
        proporcion = Decimal(transcurridos_brutos) / Decimal(dias_totales)
        proporcion = min(max(proporcion, Decimal("0")), Decimal("1"))
        base = max(costo - VALOR_RESIDUAL, Decimal("0"))
        acumulada = min(base * proporcion, base)
        valor = max(costo - acumulada, VALOR_RESIDUAL)

        if activo_fuera_de_servicio(activo):
            estado = "Retirado o dado de baja"
        elif fecha < inicio:
            estado = "No iniciada"
        elif fecha >= fin:
            estado = "Vida útil cumplida"
        elif fecha >= fin - relativedelta(months=configuracion.alerta_previa_meses):
            estado = "Próximo a cumplir vida útil"
        else:
            estado = "En depreciación"

        return ResultadoDepreciacion(
            estado=estado,
            costo_adquisicion=costo,
            valor_residual=VALOR_RESIDUAL,
            base_depreciable=base,
            proporcion=proporcion,
            porcentaje_depreciado=proporcion * Decimal("100"),
            depreciacion_acumulada=acumulada,
            valor_contable_estimado=valor,
            fecha_inicio=inicio,
            fecha_fin=fin,
            dias_transcurridos=max(transcurridos_brutos, 0),
            dias_totales=dias_totales,
            dias_restantes=max((fin - fecha).days, 0),
            proxima_alerta=cls.calcular_proxima_alerta(activo, fecha),
            configurado=True,
        )

    @classmethod
    def calcular_proxima_alerta(cls, activo, fecha=None):
        if (
            getattr(activo, "modalidad_tenencia", None) == "ARRENDADO"
            or not activo.incluir_en_depreciacion
            or activo.valor is None
            or activo.fecha_compra is None
        ):
            return None
        fecha = fecha or timezone.localdate()
        configuracion = cls.configuracion()
        fin = activo.fecha_compra + relativedelta(months=VIDA_UTIL_MESES)
        alerta = fin - relativedelta(months=configuracion.alerta_previa_meses)
        if fecha <= alerta:
            return alerta
        if fecha <= fin:
            return fin
        frecuencia = configuracion.frecuencia_recordatorio_meses
        meses = (fecha.year - fin.year) * 12 + fecha.month - fin.month
        multiplo = max(1, (meses + frecuencia - 1) // frecuencia)
        candidata = fin + relativedelta(months=multiplo * frecuencia)
        if candidata < fecha:
            candidata = fin + relativedelta(months=(multiplo + 1) * frecuencia)
        return candidata

    @classmethod
    def eventos_vencidos(cls, activo, fecha):
        if (
            getattr(activo, "modalidad_tenencia", None) == "ARRENDADO"
            or not activo.incluir_en_depreciacion
            or activo.valor is None
            or activo.fecha_compra is None
        ):
            return []
        configuracion = cls.configuracion()
        fin = activo.fecha_compra + relativedelta(months=VIDA_UTIL_MESES)
        eventos = []
        alerta = fin - relativedelta(months=configuracion.alerta_previa_meses)
        if alerta <= fecha:
            eventos.append((EventoNotificacionDepreciacion.Tipo.ALERTA, alerta))
        if fin <= fecha:
            eventos.append((EventoNotificacionDepreciacion.Tipo.CUMPLIMIENTO, fin))
            frecuencia = configuracion.frecuencia_recordatorio_meses
            meses = (fecha.year - fin.year) * 12 + fecha.month - fin.month
            for numero in range(frecuencia, meses + 1, frecuencia):
                programada = fin + relativedelta(months=numero)
                if programada <= fecha:
                    eventos.append(
                        (EventoNotificacionDepreciacion.Tipo.RECORDATORIO, programada)
                    )
        return eventos


class DepreciationNotificationService:
    @classmethod
    def destinatarios(cls, activo):
        User = get_user_model()
        administradores = (
            Q(is_superuser=True)
            | Q(
                user_permissions__content_type__app_label="depreciacion",
                user_permissions__codename="configure_alertas_depreciacion",
            )
            | Q(
                groups__permissions__content_type__app_label="depreciacion",
                groups__permissions__codename="configure_alertas_depreciacion",
            )
            | Q(
                user_permissions__content_type__app_label="activos",
                user_permissions__codename="change_activo",
            )
            | Q(
                groups__permissions__content_type__app_label="activos",
                groups__permissions__codename="change_activo",
            )
            | Q(groups__name__iexact="TIC")
        )
        ids = set(
            User.objects.filter(is_active=True)
            .filter(administradores)
            .values_list("pk", flat=True)
            .distinct()
        )
        detalle = (
            activo.detalles_asignacion.filter(activa=True)
            .select_related("asignacion__colaborador")
            .first()
        )
        if detalle:
            correo = detalle.asignacion.colaborador.correo_corporativo
            for usuario in User.objects.filter(is_active=True, email__iexact=correo):
                if usuario.has_perm("activos.view_activo"):
                    ids.add(usuario.pk)
        return sorted(ids)

    @staticmethod
    def contenido(activo, tipo):
        fin = activo.fecha_compra + relativedelta(months=VIDA_UTIL_MESES)
        fecha_texto = fin.strftime("%d/%m/%Y")
        if tipo == EventoNotificacionDepreciacion.Tipo.ALERTA:
            return (
                f"Activo {activo.codigo}: vida útil próxima",
                f"El activo {activo.codigo} está próximo a cumplir su vida útil interna. "
                f"La fecha estimada de finalización es el {fecha_texto}.",
            )
        if tipo == EventoNotificacionDepreciacion.Tipo.CUMPLIMIENTO:
            return (
                f"Activo {activo.codigo}: vida útil cumplida",
                f"El activo {activo.codigo} cumplió su vida útil interna estimada. "
                "Esto no implica que el equipo haya dejado de funcionar.",
            )
        return (
            f"Activo {activo.codigo}: recordatorio de depreciación",
            f"El activo {activo.codigo} se encuentra completamente depreciado y continúa "
            "registrado como operativo.",
        )

    @classmethod
    def procesar(cls, activo, tipo, fecha_programada, dry_run=False):
        if dry_run:
            existe = EventoNotificacionDepreciacion.objects.filter(
                activo=activo, tipo=tipo, fecha_programada=fecha_programada
            ).exists()
            return not existe, 0
        try:
            with transaction.atomic():
                evento, creado = EventoNotificacionDepreciacion.objects.get_or_create(
                    activo=activo, tipo=tipo, fecha_programada=fecha_programada
                )
                if not creado:
                    return False, evento.destinatarios
                titulo, mensaje = cls.contenido(activo, tipo)
                entregadas = 0
                for destinatario_id in cls.destinatarios(activo):
                    notificacion = NotificationService.crear_notificacion(
                        destinatario_id=destinatario_id,
                        actor=None,
                        tipo=tipo,
                        titulo=titulo,
                        mensaje=mensaje,
                        entidad_tipo=Notificacion.Entidad.ACTIVO,
                        entidad_id=activo.pk,
                        ruta=reverse("activos:detalle", args=[activo.pk]),
                        event_key=(
                            f"depreciacion:{activo.pk}:{tipo}:{fecha_programada.isoformat()}"
                        ),
                    )
                    entregadas += int(notificacion is not None)
                evento.destinatarios = entregadas
                evento.save(update_fields=["destinatarios"])
                return True, entregadas
        except IntegrityError:
            return False, 0


def calcular_depreciacion(activo, fecha_consulta=None):
    return DepreciationService.calcular(activo, fecha_consulta)


def obtener_estado_depreciacion(activo, fecha_consulta=None):
    return DepreciationService.calcular(activo, fecha_consulta).estado


def calcular_proxima_alerta(activo, fecha=None):
    return DepreciationService.calcular_proxima_alerta(activo, fecha)
