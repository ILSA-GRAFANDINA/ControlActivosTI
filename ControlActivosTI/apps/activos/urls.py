from django.urls import path

from .views import (
    ActivoCreateView,
    ActivoDetailView,
    ActivoExportView,
    ActivoListView,
    ActivoVigenciaView,
    FacturasProveedorJsonView,
    TipoActivoAtributosJsonView,
)

app_name = "activos"

urlpatterns = [
    path("", ActivoListView.as_view(), name="lista"),
    path("exportar/", ActivoExportView.as_view(), name="exportar"),
    path("nuevo/", ActivoCreateView.as_view(), name="nuevo"),
    path(
        "atributos/tipo/<int:tipo_id>/",
        TipoActivoAtributosJsonView.as_view(),
        name="atributos-tipo-json",
    ),
    path(
        "facturas/proveedor/",
        FacturasProveedorJsonView.as_view(),
        name="facturas-proveedor-json",
    ),
    path(
        "<int:pk>/<str:accion>/",
        ActivoVigenciaView.as_view(),
        name="vigencia",
    ),
    path("<int:pk>/", ActivoDetailView.as_view(), name="detalle"),
]
