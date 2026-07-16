import logging

from django.shortcuts import render

logger = logging.getLogger("controlactivos")


def _render(request, status, message, exception=None):
    if status >= 500:
        logger.error("Error HTTP %s en %s", status, request.path, exc_info=exception is not None)
    return render(request, f"errors/{status}.html", {"status_code": status, "error_message": message}, status=status)


def error_400(request, exception):
    return _render(request, 400, "La solicitud no pudo ser procesada.")


def error_403(request, exception):
    return _render(request, 403, "No tiene permisos para acceder a este recurso.")


def error_404(request, exception):
    return _render(request, 404, "No encontramos la pagina solicitada.")


def error_500(request):
    return _render(request, 500, "Ocurrio un error interno. El equipo tecnico ha sido notificado.")
