from datetime import date
from pathlib import Path
import shutil
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher, identify_hasher
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.utils import override_settings

from apps.activos.models import Activo
from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.accounts.models import PerfilUsuario
from apps.catalogos.models import (
    AtributoActivo,
    Area,
    Cargo,
    CentroCosto,
    EstadoActivo,
    TipoActivo,
    TipoActivoAtributo,
    Ubicacion,
)
from apps.auditoria.models import RegistroAuditoria
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
        self.assertContains(
            response,
            f'href="{reverse("dashboard-inicio")}" aria-label="Ir al dashboard"',
        )
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

    def test_dashboard_metric_cards_link_to_corresponding_filtered_lists(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard-inicio"))

        self.assertEqual(response.status_code, 200)
        expected_urls = [
            reverse("activos:lista"),
            f"{reverse('activos:lista')}?disponibilidad=disponibles",
            f"{reverse('activos:lista')}?disponibilidad=asignados",
            f"{reverse('asignaciones:lista')}?estado=ABIERTAS",
            reverse("colaboradores:lista"),
            f"{reverse('colaboradores:lista')}?estado=ACTIVO",
        ]
        for url in expected_urls:
            with self.subTest(url=url):
                self.assertContains(response, f'href="{url}"')

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

    def grant_attribute_schema_permission(self):
        permission = Permission.objects.get(
            codename="manage_asset_attribute_schema",
            content_type__app_label="catalogos",
        )
        self.user.user_permissions.add(permission)

    def test_admin2_attribute_schema_requires_specific_permission(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-atributos-lista"))

        self.assertEqual(response.status_code, 403)

    def test_admin2_catalog_module_links_to_native_attribute_views(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-catalogos"))

        self.assertContains(response, reverse("admin2-atributos-lista"))
        self.assertContains(response, reverse("admin2-configuraciones-atributos-lista"))

    def test_admin2_can_create_attribute_and_records_audit(self):
        self.grant_attribute_schema_permission()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("admin2-atributo-crear"),
            {
                "nombre": "Memoria de video de prueba",
                "clave": "Memoria Video Prueba",
                "descripcion": "Capacidad instalada",
                "tipo_dato": AtributoActivo.TipoDato.ENTERO,
                "unidad": "GB",
                "activo": "on",
                "opciones-TOTAL_FORMS": "2",
                "opciones-INITIAL_FORMS": "0",
                "opciones-MIN_NUM_FORMS": "0",
                "opciones-MAX_NUM_FORMS": "1000",
                "opciones-0-activo": "on",
                "opciones-1-activo": "on",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
            (response.context["form"].errors, response.context["formset"].errors)
            if response.status_code == 200 else None,
        )
        self.assertEqual(response.url, reverse("admin2-atributos-lista"))
        atributo = AtributoActivo.objects.get(clave="memoria_video_prueba")
        self.assertEqual(atributo.created_by, self.user)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                entidad="AtributoActivo", objeto_id=str(atributo.pk),
                accion=RegistroAuditoria.Accion.CREAR, usuario=self.user,
            ).exists()
        )

    def test_admin2_configuration_assigns_next_order_automatically(self):
        self.grant_attribute_schema_permission()
        primero = AtributoActivo.objects.create(
            nombre="Chip de prueba admin2", clave="chip_prueba_admin2", tipo_dato=AtributoActivo.TipoDato.TEXTO_CORTO
        )
        segundo = AtributoActivo.objects.create(
            nombre="Capacidad de prueba admin2", clave="capacidad_prueba_admin2", tipo_dato=AtributoActivo.TipoDato.ENTERO
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo_activo, atributo=primero, orden=1
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("admin2-configuracion-atributo-crear"),
            {
                "tipo_activo": self.tipo_activo.pk,
                "atributo": segundo.pk,
                "texto_ayuda": "Ingrese solo el numero",
                "unidad": "GB",
                "mostrar_detalle": "on",
                "activo": "on",
                "validaciones": "{}",
            },
        )

        self.assertRedirects(response, reverse("admin2-configuraciones-atributos-lista"))
        configuracion = TipoActivoAtributo.objects.get(tipo_activo=self.tipo_activo, atributo=segundo)
        self.assertEqual(configuracion.orden, 2)
        self.assertEqual(configuracion.created_by, self.user)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                entidad="TipoActivoAtributo", objeto_id=str(configuracion.pk),
                accion=RegistroAuditoria.Accion.ASOCIAR,
            ).exists()
        )

    def test_admin2_can_create_list_attribute_with_options(self):
        self.grant_attribute_schema_permission()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("admin2-atributo-crear"),
            {
                "nombre": "Panel de prueba admin2",
                "clave": "panel_prueba_admin2",
                "tipo_dato": AtributoActivo.TipoDato.LISTA,
                "activo": "on",
                "opciones-TOTAL_FORMS": "2",
                "opciones-INITIAL_FORMS": "0",
                "opciones-MIN_NUM_FORMS": "0",
                "opciones-MAX_NUM_FORMS": "1000",
                "opciones-0-clave": "ips",
                "opciones-0-nombre": "IPS",
                "opciones-0-orden": "1",
                "opciones-0-activo": "on",
                "opciones-1-activo": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        atributo = AtributoActivo.objects.get(clave="panel_prueba_admin2")
        opcion = atributo.opciones.get()
        self.assertEqual(opcion.clave, "ips")
        self.assertEqual(opcion.nombre, "IPS")
        self.assertTrue(opcion.activo)

    def test_admin2_remove_attribute_from_type_preserves_configuration(self):
        self.grant_attribute_schema_permission()
        atributo = AtributoActivo.objects.create(
            nombre="Resolucion", clave="resolucion", tipo_dato=AtributoActivo.TipoDato.TEXTO_CORTO
        )
        configuracion = TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo_activo, atributo=atributo, orden=1
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("admin2-configuracion-atributo-desactivar", args=[configuracion.pk])
        )

        self.assertRedirects(response, reverse("admin2-configuraciones-atributos-lista"))
        configuracion.refresh_from_db()
        self.assertFalse(configuracion.activo)
        self.assertEqual(configuracion.updated_by, self.user)
        self.assertTrue(TipoActivoAtributo.objects.filter(pk=configuracion.pk).exists())
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                entidad="TipoActivoAtributo", objeto_id=str(configuracion.pk),
                accion=RegistroAuditoria.Accion.DESACTIVAR,
            ).exists()
        )

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

    def test_admin2_home_exposes_dynamic_module_search(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("admin2-inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-admin2-search')
        self.assertContains(response, 'data-admin2-search-input')
        self.assertContains(response, 'data-admin2-search-results')
        self.assertContains(response, 'data-admin2-search-source')
        self.assertContains(response, "Buscar módulo o función...")
        self.assertContains(response, "admin2-search--quick")
        self.assertNotContains(response, "¿Qué necesitas administrar?")
        self.assertContains(response, "admin2/js/admin2-search.js")


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
        self.assertContains(response, 'class="profile-banner')

    def test_authenticated_topbar_uses_user_dropdown(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:perfil"))

        self.assertContains(response, "data-user-menu")
        self.assertContains(response, self.user.username)
        self.assertContains(response, self.user.email)
        self.assertContains(response, reverse("accounts:perfil"))
        self.assertContains(response, reverse("accounts:logout"))
        self.assertContains(response, "Cerrar sesión", count=1)

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

    def test_profile_success_message_is_rendered_as_floating_toast(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:perfil"),
            {
                "first_name": "Maria",
                "last_name": "Lopez",
                "email": "maria@example.com",
                "telefono": "",
                "cargo_visible": "",
                "bio": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="toast-region"')
        self.assertContains(response, "app-toast--success")
        self.assertContains(response, "Operación exitosa")
        self.assertContains(response, "Tu perfil fue actualizado correctamente.")
        self.assertContains(response, 'data-toast-close')
        self.assertContains(response, "css/toasts.css")
        self.assertContains(response, "js/toasts.js")

    def test_invalid_profile_form_shows_auto_dismiss_error_toast(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:perfil"),
            {
                "first_name": "Maria",
                "last_name": "Lopez",
                "email": "correo-invalido",
                "telefono": "",
                "cargo_visible": "",
                "bio": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app-toast--error")
        self.assertContains(response, "Revisa la información")
        self.assertContains(response, 'data-toast-timeout="2500"')
        self.assertContains(
            response,
            "No se pudo guardar. Corrige los campos marcados e inténtalo nuevamente.",
        )


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

    def test_successful_login_upgrades_a_legacy_password_hash(self):
        legacy_hasher = PBKDF2PasswordHasher()
        legacy_hasher.iterations = 1_000
        self.user.password = legacy_hasher.encode("secret123", legacy_hasher.salt())
        self.user.save(update_fields=["password"])

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "loginuser", "password": "secret123"},
        )

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(identify_hasher(self.user.password).algorithm, "scrypt")

    def test_sql_injection_payloads_cannot_authenticate_or_modify_users(self):
        payloads = [
            "' OR '1'='1' --",
            'loginuser" OR 1=1 --',
            "'; DELETE FROM auth_user; --",
        ]
        initial_user_count = get_user_model().objects.count()

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse("accounts:login"),
                    {"username": payload, "password": payload},
                )

                self.assertEqual(response.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertEqual(get_user_model().objects.count(), initial_user_count)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("secret123"))

    def test_login_rejects_usernames_longer_than_the_database_field(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "a" * 151, "password": "secret123"},
        )

        self.assertEqual(response.status_code, 200)
        username_error = response.context["form"].errors.as_data()["username"][0]
        self.assertEqual(username_error.code, "max_length")
        self.assertNotIn("_auth_user_id", self.client.session)

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
