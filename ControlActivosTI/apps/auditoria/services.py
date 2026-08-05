from .models import RegistroAuditoria


def registrar_evento(*, entidad, objeto_id, accion, resumen, usuario=None, detalle=None):
    return RegistroAuditoria.objects.create(
        entidad=entidad,
        objeto_id=str(objeto_id or ""),
        accion=accion,
        resumen=resumen[:255],
        usuario=usuario if getattr(usuario, "is_authenticated", False) else None,
        detalle=detalle or {},
    )
