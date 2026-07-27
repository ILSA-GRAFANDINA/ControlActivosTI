from .models import Notificacion
from .services import prepare_notifications


def notifications_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"recent_notifications": [], "unread_notifications_count": 0}

    queryset = Notificacion.objects.filter(destinatario=user).select_related("actor")
    recent = prepare_notifications(queryset[:12], user)
    return {
        "recent_notifications": recent,
        "unread_notifications_count": queryset.filter(read_at__isnull=True).count(),
    }

