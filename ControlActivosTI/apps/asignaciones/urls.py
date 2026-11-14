from django.urls import path

from .views import (
    AsignacionCreateView,
    AsignacionDetailView,
    AsignacionDevolucionView,
    AsignacionListView,
    DevolucionDetailView,
)

app_name = "asignaciones"

urlpatterns = [
    path("", AsignacionListView.as_view(), name="lista"),
    path("<int:pk>/", AsignacionDetailView.as_view(), name="detalle"),
    path("devoluciones/<int:pk>/", DevolucionDetailView.as_view(), name="devolucion_detalle"),
    path("devolver/<int:pk>/", AsignacionDevolucionView.as_view(), name="devolver"),
    path("nueva/", AsignacionCreateView.as_view(), name="nueva"),
]
