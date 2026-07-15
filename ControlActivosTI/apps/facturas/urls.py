from django.urls import path

from . import views

app_name = "facturas"

urlpatterns = [
    path("", views.FacturaListView.as_view(), name="lista"),
    path("nueva/", views.FacturaCreateView.as_view(), name="nueva"),
    path("<int:pk>/", views.FacturaDetailView.as_view(), name="detalle"),
    path("<int:pk>/editar/", views.FacturaUpdateView.as_view(), name="editar"),
    path("<int:pk>/activos/", views.FacturaAsociarActivosView.as_view(), name="asociar_activos"),
    path("<int:pk>/documento/", views.FacturaDocumentoView.as_view(), name="documento"),
    path("<int:pk>/descargar/", views.FacturaDocumentoView.as_view(), {"descargar": True}, name="descargar"),
    path("<int:pk>/reemplazar/", views.FacturaReemplazarView.as_view(), name="reemplazar"),
    path("<int:pk>/estado/", views.FacturaEstadoView.as_view(), name="estado"),
    path("<int:pk>/eliminar/", views.FacturaDeleteView.as_view(), name="eliminar"),
]
