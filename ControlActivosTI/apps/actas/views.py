import logging

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import FileResponse, Http404
from django.views import View

from .models import ActaEntrega

logger = logging.getLogger("controlactivos")


class DescargarActaPorAsignacionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "actas.view_actaentrega"
    raise_exception = True
    def get(self, request, asignacion_id, tipo, *args, **kwargs):
        tipo = tipo.upper()
        if tipo not in ActaEntrega.TipoActa.values:
            raise Http404("Tipo de acta no valido.")

        acta = (
            ActaEntrega.objects.select_related("asignacion")
            .filter(asignacion_id=asignacion_id, tipo=tipo)
            .first()
        )
        if not acta or not acta.archivo:
            raise Http404("No existe un acta generada para esta asignacion.")

        archivo = acta.archivo.open("rb")
        nombre = acta.nombre_archivo or f"acta_{acta.asignacion.codigo_asignacion}.docx"
        logger.info("Acta descargada acta_id=%s usuario_id=%s ip=%s", acta.pk, request.user.pk, request.META.get("REMOTE_ADDR", ""))
        return FileResponse(archivo, as_attachment=True, filename=nombre)


class DescargarActaPorDevolucionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "actas.view_actaentrega"
    raise_exception = True
    def get(self, request, devolucion_id, *args, **kwargs):
        acta = (
            ActaEntrega.objects.select_related("asignacion", "devolucion")
            .filter(devolucion_id=devolucion_id, tipo=ActaEntrega.TipoActa.RECEPCION)
            .first()
        )
        if not acta or not acta.archivo:
            raise Http404("No existe un acta de recepcion generada para esta devolucion.")

        archivo = acta.archivo.open("rb")
        nombre = acta.nombre_archivo or f"acta_{acta.devolucion.codigo_devolucion}.docx"
        logger.info("Acta devolucion descargada acta_id=%s usuario_id=%s ip=%s", acta.pk, request.user.pk, request.META.get("REMOTE_ADDR", ""))
        return FileResponse(archivo, as_attachment=True, filename=nombre)
