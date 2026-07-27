from django.urls import path

from .views import (
    ActivoCreateView,
    ActivoDetailView,
    ActivoExportView,
    ActivoListView,
    ActivoVigenciaView,
)

app_name = "activos"

urlpatterns = [
    path("", ActivoListView.as_view(), name="lista"),
    path("exportar/", ActivoExportView.as_view(), name="exportar"),
    path("nuevo/", ActivoCreateView.as_view(), name="nuevo"),
    path(
        "<int:pk>/<str:accion>/",
        ActivoVigenciaView.as_view(),
        name="vigencia",
    ),
    path("<int:pk>/", ActivoDetailView.as_view(), name="detalle"),
]
