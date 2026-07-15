from django.urls import path

from .views import (ProveedorCreateView, ProveedorDeleteView, ProveedorDetailView,
                    ProveedorEstadoView, ProveedorListView, ProveedorUpdateView)

app_name = "proveedores"

urlpatterns = [
    path("", ProveedorListView.as_view(), name="lista"),
    path("nuevo/", ProveedorCreateView.as_view(), name="nuevo"),
    path("<int:pk>/", ProveedorDetailView.as_view(), name="detalle"),
    path("<int:pk>/editar/", ProveedorUpdateView.as_view(), name="editar"),
    path("<int:pk>/estado/", ProveedorEstadoView.as_view(), name="estado"),
    path("<int:pk>/eliminar/", ProveedorDeleteView.as_view(), name="eliminar"),
]
