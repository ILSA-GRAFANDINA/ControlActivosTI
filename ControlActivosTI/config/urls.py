from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from .admin2_views import (
    Admin2AuditoriaView,
    Admin2CatalogCreateView,
    Admin2CatalogListView,
    Admin2CatalogUpdateView,
    Admin2CatalogosView,
    Admin2HomeView,
    Admin2InventarioView,
    Admin2ReportesView,
    Admin2SeguridadView,
    Admin2UsuariosView,
)
from .views import HealthView, InicioView, ProtectedImageView

admin.site.site_header = "ControlActivosTI"
admin.site.site_title = "ControlActivosTI Admin"
admin.site.index_title = "Administración interna"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("admin/", admin.site.urls),
    path("admin2/", Admin2HomeView.as_view(), name="admin2-inicio"),
    path("admin2/usuarios/", Admin2UsuariosView.as_view(), name="admin2-usuarios"),
    path("admin2/catalogos/", Admin2CatalogosView.as_view(), name="admin2-catalogos"),
    path("admin2/catalogos/<slug:catalog_slug>/", Admin2CatalogListView.as_view(), name="admin2-catalogo-lista"),
    path("admin2/catalogos/<slug:catalog_slug>/nuevo/", Admin2CatalogCreateView.as_view(), name="admin2-catalogo-crear"),
    path("admin2/catalogos/<slug:catalog_slug>/<int:pk>/editar/", Admin2CatalogUpdateView.as_view(), name="admin2-catalogo-editar"),
    path("admin2/seguridad/", Admin2SeguridadView.as_view(), name="admin2-seguridad"),
    path("admin2/reportes/", Admin2ReportesView.as_view(), name="admin2-reportes"),
    path("admin2/inventario/", Admin2InventarioView.as_view(), name="admin2-inventario"),
    path("admin2/auditoria/", Admin2AuditoriaView.as_view(), name="admin2-auditoria"),
    path("", InicioView.as_view(), name="inicio-raiz"),
    path("dashboard/", InicioView.as_view(), name="dashboard-inicio"),
    path("cuentas/", include("apps.accounts.urls")),
    path("activos/", include("apps.activos.urls")),
    path("colaboradores/", include("apps.colaboradores.urls")),
    path("proveedores/", include("apps.proveedores.urls")),
    path("facturas/", include("apps.facturas.urls")),
    path("asignaciones/", include("apps.asignaciones.urls")),
    path("notificaciones/", include("apps.notificaciones.urls")),
    path("actas/", include("apps.actas.urls")),
    path("media/<path:path>", ProtectedImageView.as_view(), name="protected-image"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = "config.error_views.error_400"
handler403 = "config.error_views.error_403"
handler404 = "config.error_views.error_404"
handler500 = "config.error_views.error_500"
