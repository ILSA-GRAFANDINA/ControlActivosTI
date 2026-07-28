from django.urls import path

from .views import ConfiguracionAlertasView, DepreciacionReporteView

app_name = "depreciacion"

urlpatterns = [
    path("", DepreciacionReporteView.as_view(), name="reporte"),
    path(
        "configuracion-alertas/",
        ConfiguracionAlertasView.as_view(),
        name="configurar-alertas",
    ),
]

