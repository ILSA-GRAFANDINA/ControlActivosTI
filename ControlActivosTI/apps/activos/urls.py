from django.urls import path

from .views import ActivoCreateView, ActivoDetailView, ActivoListView

app_name = "activos"

urlpatterns = [
    path("", ActivoListView.as_view(), name="lista"),
    path("nuevo/", ActivoCreateView.as_view(), name="nuevo"),
    path("<int:pk>/", ActivoDetailView.as_view(), name="detalle"),
]
