from django.urls import path

from .views import ActivoCreateView, ActivoDetailView, ActivoExportView, ActivoListView

app_name = "activos"

urlpatterns = [
    path("", ActivoListView.as_view(), name="lista"),
    path("exportar/", ActivoExportView.as_view(), name="exportar"),
    path("nuevo/", ActivoCreateView.as_view(), name="nuevo"),
    path("<int:pk>/", ActivoDetailView.as_view(), name="detalle"),
]
