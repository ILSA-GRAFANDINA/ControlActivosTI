from django.urls import path

from .views import (
    ColaboradorCreateView,
    ColaboradorDetailView,
    ColaboradorListView,
    ColaboradorUpdateView,
)

app_name = "colaboradores"

urlpatterns = [
    path("", ColaboradorListView.as_view(), name="lista"),
    path("nuevo/", ColaboradorCreateView.as_view(), name="nuevo"),
    path("<int:pk>/editar/", ColaboradorUpdateView.as_view(), name="editar"),
    path("<int:pk>/", ColaboradorDetailView.as_view(), name="detalle"),
]
