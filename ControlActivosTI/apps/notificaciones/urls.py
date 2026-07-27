from django.urls import path

from .views import AbrirNotificacionView, HistorialNotificacionesView, MarcarTodasLeidasView

app_name = "notificaciones"

urlpatterns = [
    path("", HistorialNotificacionesView.as_view(), name="historial"),
    path("leer-todas/", MarcarTodasLeidasView.as_view(), name="leer_todas"),
    path("<int:pk>/abrir/", AbrirNotificacionView.as_view(), name="abrir"),
]

