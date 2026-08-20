import hashlib
import logging
from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.urls import reverse

from .models import Notificacion, is_safe_internal_path

logger = logging.getLogger("controlactivos")


ENTITY_CONFIG = {
    Notificacion.Entidad.ACTIVO: ("activos.Activo", None),
    Notificacion.Entidad.ASIGNACION: ("asignaciones.Asignacion", None),
    Notificacion.Entidad.PROVEEDOR: ("proveedores.Proveedor", "proveedores.view_proveedor"),
    Notificacion.Entidad.FACTURA: ("facturas.FacturaCompra", "facturas.view_facturacompra"),
}


def _actor_name(actor):
    if not actor:
        return "El sistema"
    return actor.get_full_name().strip() or actor.get_username()


def _format_change_value(value):
    if value in (None, ""):
        return "sin valor"
    if hasattr(value, "pk"):
        return str(value)
    return str(value)


class NotificationService:
    @classmethod
    def _recipient_ids(cls, actor, permission=None):
        User = get_user_model()
        query = Q(is_superuser=True)
        if actor and (not permission or actor.has_perm(permission)):
            query |= Q(pk=actor.pk)
        if permission:
            app_label, codename = permission.split(".", 1)
            query |= Q(
                user_permissions__content_type__app_label=app_label,
                user_permissions__codename=codename,
            )
            query |= Q(
                groups__permissions__content_type__app_label=app_label,
                groups__permissions__codename=codename,
            )
        else:
            query |= Q(is_staff=True)
        return list(
            User.objects.filter(is_active=True).filter(query).values_list("pk", flat=True).distinct()
        )

    @classmethod
    def crear_notificacion(
        cls,
        *,
        destinatario_id,
        actor,
        tipo,
        titulo,
        mensaje,
        entidad_tipo=Notificacion.Entidad.NINGUNA,
        entidad_id=None,
        ruta="",
        event_key="",
    ):
        if not destinatario_id:
            return None
        raw_key = "|".join(
            str(value)
            for value in (
                destinatario_id,
                tipo,
                entidad_tipo,
                entidad_id or "",
                event_key or f"{titulo}|{mensaje}",
            )
        )
        fingerprint = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        try:
            notification, _ = Notificacion.objects.get_or_create(
                destinatario_id=destinatario_id,
                fingerprint=fingerprint,
                defaults={
                    "actor": actor if getattr(actor, "is_authenticated", False) else None,
                    "tipo": tipo,
                    "titulo": titulo[:100],
                    "mensaje": mensaje[:280],
                    "entidad_tipo": entidad_tipo,
                    "entidad_id": entidad_id,
                    "ruta": ruta[:240],
                },
            )
            return notification
        except Exception:
            logger.exception(
                "No se pudo crear la notificación secundaria tipo=%s entidad=%s:%s",
                tipo,
                entidad_tipo,
                entidad_id,
            )
            return None

    @classmethod
    def notificar_actividad(
        cls,
        *,
        actor,
        tipo,
        titulo,
        mensaje,
        entidad_tipo,
        entidad_id,
        ruta,
        permission=None,
        event_key="",
    ):
        recipient_ids = cls._recipient_ids(actor, permission)

        def create_after_commit():
            for recipient_id in recipient_ids:
                cls.crear_notificacion(
                    destinatario_id=recipient_id,
                    actor=actor,
                    tipo=tipo,
                    titulo=titulo,
                    mensaje=mensaje,
                    entidad_tipo=entidad_tipo,
                    entidad_id=entidad_id,
                    ruta=ruta,
                    event_key=event_key,
                )

        transaction.on_commit(create_after_commit)

    @classmethod
    def activo_creado(cls, activo, actor):
        nombre = _actor_name(actor)
        cls.notificar_actividad(
            actor=actor,
            tipo=Notificacion.Tipo.ACTIVO_CREADO,
            titulo=f"Activo {activo.codigo} registrado",
            mensaje=f"{nombre} registró el activo {activo.codigo} ({activo.marca} {activo.modelo}).",
            entidad_tipo=Notificacion.Entidad.ACTIVO,
            entidad_id=activo.pk,
            ruta=reverse("activos:detalle", args=[activo.pk]),
            permission=None,
            event_key=f"activo:create:{activo.pk}",
        )

    @classmethod
    def activo_cambiado(cls, activo, actor, cambios):
        if not cambios:
            return
        nombre = _actor_name(actor)
        etiquetas = {
            "marca": "marca",
            "modelo": "nombre/modelo",
            "tipo_activo": "categoría",
            "estado_activo": "estado",
            "empresa": "empresa",
            "ubicacion_fisica": "ubicación física",
            "activo": "estado del registro",
            "proveedor": "proveedor",
            "factura_compra": "factura",
        }
        partes = [etiquetas[campo] for campo in cambios if campo in etiquetas]
        if not partes:
            return
        if len(partes) == 1:
            campo = next(iter(cambios))
            valores = cambios[campo]
            if isinstance(valores, (list, tuple)) and len(valores) == 2:
                anterior, nuevo = valores
                if campo == "activo":
                    anterior = "Visible" if anterior else "Eliminado"
                    nuevo = "Visible" if nuevo else "Eliminado"
                else:
                    anterior = _format_change_value(anterior)
                    nuevo = _format_change_value(nuevo)
                resumen = f"{etiquetas[campo]} de “{anterior}” a “{nuevo}”"
            else:
                resumen = etiquetas[campo]
        else:
            resumen = ", ".join(partes)
        tipo = (
            Notificacion.Tipo.ACTIVO_ELIMINADO
            if "activo" in cambios and not activo.activo
            else Notificacion.Tipo.ACTIVO_CAMBIADO
        )
        cls.notificar_actividad(
            actor=actor,
            tipo=tipo,
            titulo=f"Activo {activo.codigo} actualizado",
            mensaje=f"{nombre} cambió {resumen} del activo {activo.codigo}.",
            entidad_tipo=Notificacion.Entidad.ACTIVO,
            entidad_id=activo.pk,
            ruta=reverse("activos:detalle", args=[activo.pk]),
            permission=None,
            event_key=f"activo:update:{activo.pk}:{activo.updated_at.isoformat()}:{','.join(sorted(cambios))}",
        )

    @classmethod
    def asignacion_creada(cls, asignacion, actor):
        nombre = _actor_name(actor)
        colaborador = asignacion.nombre_colaborador_completo
        codigos = asignacion.resumen_activos
        cls.notificar_actividad(
            actor=actor,
            tipo=Notificacion.Tipo.ASIGNACION_CREADA,
            titulo=f"Asignación {asignacion.codigo_asignacion}",
            mensaje=f"{nombre} asignó {codigos} a {colaborador}.",
            entidad_tipo=Notificacion.Entidad.ASIGNACION,
            entidad_id=asignacion.pk,
            ruta=reverse("asignaciones:detalle", args=[asignacion.pk]),
            permission=None,
            event_key=f"asignacion:create:{asignacion.pk}",
        )

    @classmethod
    def asignacion_devuelta(cls, asignacion, devolucion, actor, codigos):
        nombre = _actor_name(actor)
        finalizada = asignacion.estado_asignacion == asignacion.EstadoAsignacion.CERRADA
        cls.notificar_actividad(
            actor=actor,
            tipo=(
                Notificacion.Tipo.ASIGNACION_FINALIZADA
                if finalizada
                else Notificacion.Tipo.ASIGNACION_CAMBIADA
            ),
            titulo=(
                f"Asignación {asignacion.codigo_asignacion} finalizada"
                if finalizada
                else f"Devolución en {asignacion.codigo_asignacion}"
            ),
            mensaje=f"{nombre} recibió {', '.join(codigos)} de {asignacion.nombre_colaborador_completo}.",
            entidad_tipo=Notificacion.Entidad.ASIGNACION,
            entidad_id=asignacion.pk,
            ruta=reverse("asignaciones:detalle", args=[asignacion.pk]),
            permission=None,
            event_key=f"devolucion:create:{devolucion.pk}",
        )

    @classmethod
    def proveedor_guardado(cls, proveedor, actor, creado=False, cambios=None):
        cambios = set(cambios or [])
        if not creado and not cambios:
            return
        nombre = _actor_name(actor)
        accion = "registró" if creado else "actualizó"
        cls.notificar_actividad(
            actor=actor,
            tipo=(
                Notificacion.Tipo.PROVEEDOR_CREADO
                if creado
                else Notificacion.Tipo.PROVEEDOR_CAMBIADO
            ),
            titulo=f"Proveedor {proveedor.razon_social}",
            mensaje=f"{nombre} {accion} al proveedor {proveedor.razon_social}.",
            entidad_tipo=Notificacion.Entidad.PROVEEDOR,
            entidad_id=proveedor.pk,
            ruta=reverse("proveedores:detalle", args=[proveedor.pk]),
            permission="proveedores.view_proveedor",
            event_key=(
                f"proveedor:create:{proveedor.pk}"
                if creado
                else f"proveedor:update:{proveedor.pk}:{proveedor.updated_at.isoformat()}:{','.join(sorted(cambios))}"
            ),
        )

    @classmethod
    def factura_guardada(cls, factura, actor, creada=False, cambios=None):
        cambios = set(cambios or [])
        if not creada and not cambios:
            return
        nombre = _actor_name(actor)
        accion = "registró" if creada else "actualizó"
        cls.notificar_actividad(
            actor=actor,
            tipo=(
                Notificacion.Tipo.FACTURA_CREADA
                if creada
                else Notificacion.Tipo.FACTURA_CAMBIADA
            ),
            titulo=f"Factura {factura.numero_factura}",
            mensaje=f"{nombre} {accion} la factura {factura.numero_factura}.",
            entidad_tipo=Notificacion.Entidad.FACTURA,
            entidad_id=factura.pk,
            ruta=reverse("facturas:detalle", args=[factura.pk]),
            permission="facturas.view_facturacompra",
            event_key=(
                f"factura:create:{factura.pk}"
                if creada
                else f"factura:update:{factura.pk}:{factura.updated_at.isoformat()}:{','.join(sorted(cambios))}"
            ),
        )


def prepare_notifications(notifications, user):
    grouped = defaultdict(set)
    items = list(notifications)
    for notification in items:
        if notification.entidad_id:
            grouped[notification.entidad_tipo].add(notification.entidad_id)

    existing = {}
    permissions = {}
    from django.apps import apps

    for entity_type, ids in grouped.items():
        config = ENTITY_CONFIG.get(entity_type)
        if not config:
            continue
        model_label, permission = config
        permissions[entity_type] = not permission or user.has_perm(permission)
        if permissions[entity_type]:
            model = apps.get_model(model_label)
            existing[entity_type] = set(model.objects.filter(pk__in=ids).values_list("pk", flat=True))

    for notification in items:
        notification.related_missing = bool(
            notification.entidad_id
            and notification.entidad_id not in existing.get(notification.entidad_tipo, set())
        )
        notification.display_url = (
            notification.ruta
            if is_safe_internal_path(notification.ruta)
            and permissions.get(notification.entidad_tipo, False)
            and not notification.related_missing
            else ""
        )
    return items
