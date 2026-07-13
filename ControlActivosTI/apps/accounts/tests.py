from datetime import date
from pathlib import Path
import shutil
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.utils import override_settings

from apps.activos.models import Activo
from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.accounts.models import PerfilUsuario
from apps.catalogos.models import Area, Cargo, CentroCosto, EstadoActivo, TipoActivo, Ubicacion
from apps.colaboradores.models import Colaborador


def make_test_media_root():
    media_root = Path.cwd() / "test-media" / uuid.uuid4().hex
    media_root.mkdir(parents=True, exist_ok=True)
    return media_root


class Admin2ViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staffuser",
            password="secret123",
            is_staff=True,
        )
        self.area = Area.objects.create(nombre="TI")
        self.cargo = Cargo.objects.create(nombre="Analista")
        self.ubicacion = Ubicacion.objects.create(nombre="Matriz")
        self.ceco = CentroCosto.objects.create(
            codigo="TI001",
            nombre="Tecnologia",
            acepta_asignaciones=True,
            activo=True,
        )
        self.tipo_activo = TipoActivo.objects.create(nombre="Laptop")
        self.tipo_teclado = TipoActivo.objects.create(nombre="Teclado")
        self.estado_disponible = EstadoActivo.objects.create(
            nombre="Disponible",
            permite_asignacion=True,
        )
        self.estado_asignado = EstadoActivo.objects.create(
            nombre="Asignado",
            permite_asignacion=False,
        )
        self.colaborador = Colaborador.objects.create(
            nombres="Ana",
            apellidos="Perez",
            cedula="0123456789",
            correo_corporativo="ana.perez@example.com",
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            centro_costo=self.ceco,
            fecha_ingreso=date(2024, 1, 10),
        )
        self.activo = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="Dell",
            modelo="Latitude 5440",
            serie="ABC123",
            codigo_sap="SAP-ACC-001",
            estado_activo=self.estado_disponible,
        )
        self.activo_teclado = Activo.objects.create(
            tipo_activo=self.tipo_teclado,
            marca="Logitech",
            modelo="K120",
            serie="KEY123",
            estado_activo=self.estado_disponible,
        )
        self.asignacion = Asignacion.objects.create(
            colaborador=self.colaborador,
            fecha_asignacion=date(2026, 4, 20),
            usuario_responsable=self.user,
        )
        AsignacionDetalle.objects.create(
            asignacion=self.asignacion,
            activo=self.activo,
            orden=1,
        )

    def test_admin2_requires_staff_access(self):
        response = self.client.get(reverse("admin2-inicio"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_admin2_home_renders_real_operational_data(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lanzador administrativo")
        self.assertContains(response, "Usuarios")
        self.assertContains(response, "Activos")
        self.assertContains(response, "Asignaciones")
        self.assertContains(response, "Activos registrados")

    def test_dashboard_shows_assets_by_type_availability_summary(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard-inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disponibilidad por tipo de activo")

        resumen_por_tipo = {
            item["tipo_activo__nombre"]: item for item in response.context["activos_tipo_resumen"]
        }

        self.assertEqual(resumen_por_tipo["Laptop"]["disponibles"], 0)
        self.assertEqual(resumen_por_tipo["Laptop"]["asignados"], 1)
        self.assertEqual(resumen_por_tipo["Laptop"]["total"], 1)
        self.assertEqual(resumen_por_tipo["Teclado"]["disponibles"], 1)
        self.assertEqual(resumen_por_tipo["Teclado"]["asignados"], 0)
        self.assertEqual(resumen_por_tipo["Teclado"]["total"], 1)

    def test_admin2_home_uses_practical_section_names(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activos")
        self.assertContains(response, "Colaboradores")
        self.assertContains(response, "Tablas maestras")
        self.assertContains(response, "Administrador")
        self.assertNotContains(response, "Guía rápida")
        self.assertNotContains(response, 'href="#admin2-guia"')

    def test_admin2_inventory_module_shows_asset_rows(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-inventario"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ultimos activos incorporados")
        self.assertContains(response, self.activo.codigo)
        self.assertContains(response, "Disponibles")

    def test_admin2_dashboard_uses_current_ceco_name_after_rename(self):
        self.ceco.nombre = "Tecnologia Renovada"
        self.ceco.codigo = "2001"
        self.ceco.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard-inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2001 - Tecnologia Renovada")
        self.assertNotContains(response, "TI001 - Tecnologia")

    def test_admin2_catalog_can_create_records(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("admin2-catalogo-crear", args=["areas"]),
            {
                "nombre": "Finanzas",
                "descripcion": "Area administrativa",
                "activo": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Area.objects.filter(nombre="Finanzas", activo=True).exists())

    def test_admin2_topbar_uses_profile_photo_when_available(self):
        media_root = make_test_media_root()
        try:
            with override_settings(MEDIA_ROOT=media_root):
                profile = PerfilUsuario.objects.create(
                    user=self.user,
                    foto=SimpleUploadedFile("staff-avatar.jpg", b"filecontent", content_type="image/jpeg"),
                )
                self.client.force_login(self.user)

                response = self.client.get(reverse("admin2-inicio"))
                profile.refresh_from_db()

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, profile.foto.url)
        finally:
            shutil.rmtree(media_root, ignore_errors=True)

    def test_admin2_has_scroll_to_top_floating_button(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-admin2-scroll-top')
        self.assertContains(response, 'aria-label="Volver arriba"')

    def test_admin2_home_marks_scroll_sections_for_dynamic_navigation(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-admin2-anchor-link')
        self.assertContains(response, 'data-admin2-section')


class PerfilUsuarioViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="maria",
            password="secret123",
            first_name="Maria",
            last_name="Lopez",
            email="maria@example.com",
        )

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:perfil"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_profile_view_creates_profile_if_missing(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:perfil"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(PerfilUsuario.objects.filter(user=self.user).exists())
        self.assertContains(response, "Actualiza tu información básica")

    def test_profile_view_updates_basic_data(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:perfil"),
            {
                "first_name": "Maria Jose",
                "last_name": "Lopez Vera",
                "email": "mjose@example.com",
                "telefono": "0999999999",
                "cargo_visible": "Analista TI",
                "bio": "Encargada de soporte interno.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        profile = PerfilUsuario.objects.get(user=self.user)
        self.assertEqual(self.user.first_name, "Maria Jose")
        self.assertEqual(self.user.last_name, "Lopez Vera")
        self.assertEqual(self.user.email, "mjose@example.com")
        self.assertEqual(profile.telefono, "0999999999")
        self.assertEqual(profile.cargo_visible, "Analista TI")
        self.assertEqual(profile.bio, "Encargada de soporte interno.")


class LoginViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="loginuser",
            password="secret123",
        )

    def test_login_with_remember_me_uses_persistent_session(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "loginuser",
                "password": "secret123",
                "remember_me": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard-inicio"))

        session = self.client.session
        self.assertEqual(session.get_expire_at_browser_close(), False)
        self.assertEqual(session.get_expiry_age(), 60 * 60 * 24 * 14)

    def test_login_without_remember_me_expires_at_browser_close(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "loginuser",
                "password": "secret123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard-inicio"))

        session = self.client.session
        self.assertEqual(session.get_expire_at_browser_close(), True)

    def test_profile_photo_is_available_in_shared_layouts(self):
        media_root = make_test_media_root()
        try:
            with override_settings(MEDIA_ROOT=media_root):
                profile = PerfilUsuario.objects.create(
                    user=self.user,
                    foto=SimpleUploadedFile("avatar.jpg", b"filecontent", content_type="image/jpeg"),
                )
                self.client.force_login(self.user)

                dashboard_response = self.client.get(reverse("dashboard-inicio"))
                profile.refresh_from_db()

                self.assertEqual(dashboard_response.status_code, 200)
                self.assertContains(dashboard_response, profile.foto.url)
        finally:
            shutil.rmtree(media_root, ignore_errors=True)
