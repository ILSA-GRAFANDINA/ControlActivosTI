from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.activos.models import Activo
from apps.asignaciones.models import Asignacion
from apps.catalogos.models import (
    Area,
    Cargo,
    CentroCosto,
    Empresa,
    EstadoActivo,
    TipoActivo,
    Ubicacion,
)
from apps.colaboradores.models import Colaborador
from apps.proveedores.models import Proveedor

from apps.notificaciones.context_processors import notifications_context
from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import NotificationService, prepare_notifications

User = get_user_model()


class NotificationBaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="kevin", password="secret123")
        self.other = User.objects.create_user(username="maria", password="secret123")

    def create_notification(self, user=None, **kwargs):
        user = user or self.user
        defaults = {
            "destinatario": user,
            "actor": self.user,
            "tipo": Notificacion.Tipo.ACTIVO_CREADO,
            "titulo": "Activo registrado",
            "mensaje": "Kevin registró un activo.",
            "entidad_tipo": Notificacion.Entidad.NINGUNA,
            "fingerprint": f"fingerprint-{user.pk}-{Notificacion.objects.count()}",
        }
        defaults.update(kwargs)
        return Notificacion.objects.create(**defaults)


class NotificationViewsTests(NotificationBaseTests):
    def test_unread_counter_is_personal(self):
        self.create_notification()
        self.create_notification()
        self.create_notification(user=self.other)
        request = type("Request", (), {"user": self.user})()
        context = notifications_context(request)
        self.assertEqual(context["unread_notifications_count"], 2)
        self.assertEqual(len(context["recent_notifications"]), 2)

    def test_mark_individual_as_read_and_redirects_to_related_object(self):
        proveedor = Proveedor.objects.create(
            tipo_proveedor=Proveedor.TipoProveedor.EMPRESA,
            tipo_identificacion=Proveedor.TipoIdentificacion.RUC,
            identificacion="1790012345001",
            razon_social="Proveedor Uno",
        )
        notification = self.create_notification(
            entidad_tipo=Notificacion.Entidad.PROVEEDOR,
            entidad_id=proveedor.pk,
            ruta=reverse("proveedores:detalle", args=[proveedor.pk]),
        )
        self.user.user_permissions.add(
            *User._meta.apps.get_model("auth", "Permission").objects.filter(
                codename="view_proveedor", content_type__app_label="proveedores"
            )
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("notificaciones:abrir", args=[notification.pk]))
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.assertRedirects(
            response,
            reverse("proveedores:detalle", args=[proveedor.pk]),
            fetch_redirect_response=False,
        )

    def test_mark_all_as_read_returns_async_counter(self):
        self.create_notification()
        self.create_notification()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notificaciones:leer_todas"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.json(), {"updated": 2, "unread_count": 0})
        self.assertFalse(
            Notificacion.objects.filter(destinatario=self.user, read_at__isnull=True).exists()
        )

    def test_user_cannot_read_another_users_notification(self):
        notification = self.create_notification(user=self.other)
        self.client.force_login(self.user)
        response = self.client.post(reverse("notificaciones:abrir", args=[notification.pk]))
        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_missing_related_object_has_no_link(self):
        proveedor = Proveedor.objects.create(
            tipo_proveedor=Proveedor.TipoProveedor.EMPRESA,
            tipo_identificacion=Proveedor.TipoIdentificacion.RUC,
            identificacion="1790012345002",
            razon_social="Proveedor Borrable",
        )
        notification = self.create_notification(
            entidad_tipo=Notificacion.Entidad.PROVEEDOR,
            entidad_id=proveedor.pk,
            ruta=reverse("proveedores:detalle", args=[proveedor.pk]),
        )
        proveedor.delete()
        prepared = prepare_notifications([notification], self.user)[0]
        self.assertTrue(prepared.related_missing)
        self.assertEqual(prepared.display_url, "")

    def test_external_related_path_is_never_exposed(self):
        notification = self.create_notification(ruta="//malicioso.example/robo")
        prepared = prepare_notifications([notification], self.user)[0]
        self.assertEqual(prepared.display_url, "")

    def test_history_is_paginated(self):
        for index in range(25):
            self.create_notification(titulo=f"Notificación {index}")
        self.client.force_login(self.user)
        response = self.client.get(reverse("notificaciones:historial"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["notificaciones"]), 20)
        self.assertTrue(response.context["is_paginated"])

    def test_bell_contains_badge_and_async_endpoint(self):
        self.create_notification()
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard-inicio"))
        self.assertContains(response, "data-notification-badge")
        self.assertContains(response, reverse("notificaciones:leer_todas"))

    def test_preparation_avoids_n_plus_one(self):
        empresa = Empresa.objects.create(nombre="Empresa")
        tipo = TipoActivo.objects.create(nombre="Monitor")
        estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        activos = [
            Activo.objects.create(
                tipo_activo=tipo,
                empresa=empresa,
                marca="Dell",
                modelo=f"P{index}",
                serie=f"SER-{index}",
                estado_activo=estado,
            )
            for index in range(10)
        ]
        notifications = [
            self.create_notification(
                entidad_tipo=Notificacion.Entidad.ACTIVO,
                entidad_id=activo.pk,
                ruta=reverse("activos:detalle", args=[activo.pk]),
            )
            for activo in activos
        ]
        with self.assertNumQueries(1):
            prepared = prepare_notifications(notifications, self.user)
        self.assertTrue(all(item.display_url for item in prepared))


class NotificationServiceTests(NotificationBaseTests):
    def test_duplicate_notifications_are_not_created(self):
        for _ in range(2):
            NotificationService.crear_notificacion(
                destinatario_id=self.user.pk,
                actor=self.user,
                tipo=Notificacion.Tipo.ACTIVO_CREADO,
                titulo="Activo LAP-001",
                mensaje="Kevin registró LAP-001.",
                entidad_tipo=Notificacion.Entidad.ACTIVO,
                entidad_id=1,
                ruta="/activos/1/",
                event_key="activo:create:1",
            )
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_secondary_failure_does_not_break_main_operation(self):
        with patch(
            "apps.notificaciones.services.Notificacion.objects.get_or_create",
            side_effect=RuntimeError("fallo secundario"),
        ):
            result = NotificationService.crear_notificacion(
                destinatario_id=self.user.pk,
                actor=self.user,
                tipo=Notificacion.Tipo.ACTIVO_CREADO,
                titulo="Prueba",
                mensaje="Prueba",
                event_key="failure",
            )
        self.assertIsNone(result)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())


class RelevantFlowTests(NotificationBaseTests):
    def setUp(self):
        super().setUp()
        self.empresa = Empresa.objects.create(nombre="Acme")
        self.tipo = TipoActivo.objects.create(nombre="Laptop")
        self.disponible = EstadoActivo.objects.create(
            nombre="Disponible", permite_asignacion=True
        )
        self.asignado = EstadoActivo.objects.create(
            nombre="Asignado", permite_asignacion=False
        )

    def asset_data(self, activo=None):
        data = {
            "tipo_activo": self.tipo.pk,
            "empresa": self.empresa.pk,
            "marca": activo.marca if activo else "Dell",
            "modelo": activo.modelo if activo else "Latitude 5420",
            "serie": activo.serie if activo else "SER-001",
            "codigo_sap": activo.codigo_sap if activo else "SAP-NOT-001",
            "cpu": "Intel Core i5",
            "ram": "16 GB",
            "disco": "512 GB",
            "sistema_operativo": "Windows 11",
            "fecha_compra": "2026-01-10",
            "valor": "1000.00",
            "estado_activo": self.disponible.pk,
            "activo": "on",
            "observaciones": "",
            "fotos-TOTAL_FORMS": "2",
            "fotos-INITIAL_FORMS": "0",
            "fotos-MIN_NUM_FORMS": "0",
            "fotos-MAX_NUM_FORMS": "5",
        }
        if activo:
            data["activo_id"] = str(activo.pk)
        return data

    def test_asset_create_and_real_name_change_notify_but_noop_does_not(self):
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("activos:nuevo"), self.asset_data())
        self.assertEqual(response.status_code, 302)
        activo = Activo.objects.get(serie="SER-001")
        self.assertEqual(
            Notificacion.objects.filter(tipo=Notificacion.Tipo.ACTIVO_CREADO).count(), 1
        )

        unchanged = self.asset_data(activo)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{reverse('activos:nuevo')}?editar={activo.pk}", unchanged
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notificacion.objects.count(), 1)

        changed = self.asset_data(activo)
        changed["modelo"] = "Latitude 5420 renovada"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"{reverse('activos:nuevo')}?editar={activo.pk}", changed
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Notificacion.objects.filter(tipo=Notificacion.Tipo.ACTIVO_CAMBIADO).count(), 1
        )

    @patch("apps.asignaciones.views.generar_o_actualizar_acta")
    def test_assignment_creation_notifies(self, generate_act):
        area = Area.objects.create(nombre="TI")
        cargo = Cargo.objects.create(nombre="Analista")
        ubicacion = Ubicacion.objects.create(nombre="Matriz")
        centro = CentroCosto.objects.create(
            codigo="TI001", nombre="Tecnología", empresa=self.empresa
        )
        colaborador = Colaborador.objects.create(
            nombres="Juan",
            apellidos="Pérez",
            cedula="0123456789",
            correo_corporativo="juan@example.com",
            empresa=self.empresa,
            cargo=cargo,
            area=area,
            ubicacion=ubicacion,
            centro_costo=centro,
            fecha_ingreso=date(2025, 1, 1),
        )
        activo = Activo.objects.create(
            tipo_activo=self.tipo,
            marca="Dell",
            modelo="Latitude",
            serie="ASG-001",
            estado_activo=self.disponible,
        )
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("asignaciones:nueva"),
                {
                    "colaborador": colaborador.pk,
                    "activos": [activo.pk],
                    "fecha_asignacion": "2026-01-20",
                    "observaciones_entrega": "",
                },
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Asignacion.objects.count(), 1)
        notification = Notificacion.objects.get(
            tipo=Notificacion.Tipo.ASIGNACION_CREADA
        )
        self.assertIn(activo.codigo, notification.mensaje)
        self.assertEqual(
            notification.ruta,
            reverse("asignaciones:detalle", args=[Asignacion.objects.get().pk]),
        )


class PurgeNotificationsTests(NotificationBaseTests):
    def test_dry_run_keeps_old_notifications(self):
        notification = self.create_notification(read_at=timezone.now())
        Notificacion.objects.filter(pk=notification.pk).update(
            created_at=timezone.now() - timedelta(days=181)
        )
        output = StringIO()
        with override_settings(
            NOTIFICATIONS_READ_RETENTION_DAYS=180,
            NOTIFICATIONS_UNREAD_RETENTION_DAYS=365,
        ):
            call_command("purge_old_notifications", "--dry-run", stdout=output)
        self.assertIn("se eliminarían 1", output.getvalue())
        self.assertTrue(Notificacion.objects.filter(pk=notification.pk).exists())

    def test_command_deletes_only_expired_records(self):
        old_read = self.create_notification(read_at=timezone.now())
        recent_read = self.create_notification(read_at=timezone.now())
        old_unread = self.create_notification()
        Notificacion.objects.filter(pk=old_read.pk).update(
            created_at=timezone.now() - timedelta(days=181)
        )
        Notificacion.objects.filter(pk=old_unread.pk).update(
            created_at=timezone.now() - timedelta(days=366)
        )
        with override_settings(
            NOTIFICATIONS_READ_RETENTION_DAYS=180,
            NOTIFICATIONS_UNREAD_RETENTION_DAYS=365,
        ):
            call_command("purge_old_notifications", "--batch-size=1")
        self.assertFalse(Notificacion.objects.filter(pk=old_read.pk).exists())
        self.assertFalse(Notificacion.objects.filter(pk=old_unread.pk).exists())
        self.assertTrue(Notificacion.objects.filter(pk=recent_read.pk).exists())

    def test_demo_command_creates_exactly_two_repeatable_notifications(self):
        call_command("seed_demo_notifications", username=self.user.username)
        call_command("seed_demo_notifications", username=self.user.username)
        self.assertEqual(
            Notificacion.objects.filter(
                destinatario=self.user,
                fingerprint__startswith="demo-notification-v2-",
            ).count(),
            2,
        )


class NotificationAdminTests(NotificationBaseTests):
    def test_admin_changelist_supports_filters(self):
        admin = User.objects.create_superuser(
            username="admin", password="secret123", email="admin@example.com"
        )
        self.create_notification()
        self.client.force_login(admin)
        response = self.client.get(
            reverse("admin:notificaciones_notificacion_changelist"),
            {"tipo": Notificacion.Tipo.ACTIVO_CREADO, "estado_lectura": "pendiente"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activo registrado")

    def test_admin2_exposes_notification_admin(self):
        admin = User.objects.create_superuser(
            username="admin2", password="secret123", email="admin2@example.com"
        )
        self.client.force_login(admin)
        response = self.client.get(reverse("admin2-auditoria"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse("admin:notificaciones_notificacion_changelist")
        )
