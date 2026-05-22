from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.actas.models import ActaEntrega
from apps.activos.models import Activo
from apps.catalogos.models import Area, Cargo, CentroCosto, Empresa, EstadoActivo, TipoActivo, Ubicacion
from apps.colaboradores.models import Colaborador

from apps.asignaciones.forms import AsignacionCreateForm
from apps.asignaciones.models import Asignacion, AsignacionDetalle, Devolucion


class AsignacionCreateFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester",
            password="secret123",
        )
        self.area = Area.objects.create(nombre="TI")
        self.cargo = Cargo.objects.create(nombre="Analista")
        self.ubicacion = Ubicacion.objects.create(nombre="Matriz")
        self.empresa = Empresa.objects.create(nombre="Acme")
        self.centro_costo = CentroCosto.objects.create(
            codigo="TI001",
            nombre="Tecnologia",
            empresa=self.empresa,
        )
        self.tipo_activo = TipoActivo.objects.create(nombre="Laptop")
        self.estado_disponible = EstadoActivo.objects.create(
            nombre="Disponible",
            permite_asignacion=True,
        )
        self.estado_asignado = EstadoActivo.objects.create(
            nombre="Asignado",
            permite_asignacion=False,
        )
        self.estado_no_disponible = EstadoActivo.objects.create(
            nombre="Danado",
            permite_asignacion=False,
        )
        self.estado_cuarentena = EstadoActivo.objects.create(
            nombre="Cuarentena",
            permite_asignacion=True,
        )
        self.estado_reparacion = EstadoActivo.objects.create(
            nombre="Reparacion",
            permite_asignacion=True,
        )
        self.colaborador = Colaborador.objects.create(
            nombres="Ana",
            apellidos="Perez",
            cedula="0123456789",
            correo_corporativo="ana.perez@example.com",
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            centro_costo=self.centro_costo,
            fecha_ingreso=date(2024, 1, 10),
        )
        self.activo_disponible = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="Dell",
            modelo="Latitude 5440",
            serie="ABC123",
            codigo_sap="SAP-ASG-001",
            cpu="Intel Core i7",
            ram="16 GB",
            disco="512 GB SSD",
            sistema_operativo="Windows 11",
            estado_activo=self.estado_disponible,
        )
        self.activo_no_disponible = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="HP",
            modelo="ProBook",
            serie="XYZ999",
            codigo_sap="SAP-ASG-002",
            estado_activo=self.estado_no_disponible,
        )
        self.activo_cuarentena = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="Lenovo",
            modelo="ThinkPad",
            serie="CW001",
            codigo_sap="SAP-ASG-003",
            estado_activo=self.estado_cuarentena,
        )
        self.activo_reparacion = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="Acer",
            modelo="Swift",
            serie="RP001",
            codigo_sap="SAP-ASG-004",
            estado_activo=self.estado_reparacion,
        )

    def test_form_only_lists_assignable_assets(self):
        form = AsignacionCreateForm()

        queryset = form.fields["activos"].queryset

        self.assertIn(self.activo_disponible, queryset)
        self.assertIn(self.activo_no_disponible, queryset)
        self.assertIn(self.activo_cuarentena, queryset)
        self.assertIn(self.activo_reparacion, queryset)

    def test_form_renders_detailed_asset_labels_and_filter_metadata(self):
        form = AsignacionCreateForm()
        rendered = str(form["activos"])

        self.assertIn(self.activo_disponible.codigo, rendered)
        self.assertIn("Laptop", rendered)
        self.assertIn("Dell Latitude 5440", rendered)
        self.assertIn("Serie: ABC123", rendered)
        self.assertIn("CPU: Intel Core i7", rendered)
        self.assertIn('data-search="', rendered)
        self.assertNotIn("SAP:", rendered)

    def test_asignacion_detalle_rejects_repair_assets_even_if_state_allows_assignment(self):
        activo_reparacion = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="Acer",
            modelo="Swift 3",
            serie="REP-001",
            codigo_sap="SAP-ASG-010",
            estado_activo=self.estado_reparacion,
        )
        asignacion = Asignacion.objects.create(
            colaborador=self.colaborador,
            fecha_asignacion=date(2026, 4, 20),
            observaciones_entrega="Entrega inicial",
            usuario_responsable=self.user,
        )

        detalle = AsignacionDetalle(
            asignacion=asignacion,
            activo=activo_reparacion,
            orden=1,
        )

        with self.assertRaises(ValidationError):
            detalle.full_clean()

    def test_create_view_renders_asset_table_with_checkboxes(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("asignaciones:nueva"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtrar por estado", html=False)
        self.assertContains(response, "Seleccionar visibles")
        self.assertContains(response, "Marca / Modelo")
        self.assertContains(response, 'type="checkbox"', html=False)
        self.assertContains(response, f'value="{self.activo_disponible.pk}"', html=False)
        self.assertContains(response, "Todos los estados")
        self.assertContains(response, 'selected', html=False)
        self.assertContains(response, f'value="{self.activo_reparacion.pk}"', html=False)
        self.assertContains(response, 'disabled', html=False)
        self.assertContains(response, "Confirmar asignación múltiple")
        self.assertContains(response, "Crear asignación")
        self.assertContains(response, "Regresar")
        self.assertContains(response, "Estás asignando 4 o más activos a un mismo usuario")

    def test_form_rejects_non_assignable_assets_on_post(self):
        form = AsignacionCreateForm(
            data={
                "colaborador": self.colaborador.pk,
                "fecha_asignacion": "2026-04-20",
                "observaciones_entrega": "",
                "activos": [self.activo_disponible.pk, self.activo_reparacion.pk],
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("activos", form.errors)
        self.assertIn("no están disponibles", form.errors["activos"][0])

    def test_devolucion_view_accepts_post_for_active_detail(self):
        asignacion = Asignacion.objects.create(
            colaborador=self.colaborador,
            fecha_asignacion=date(2026, 4, 20),
            observaciones_entrega="Entrega inicial",
            usuario_responsable=self.user,
        )
        detalle = AsignacionDetalle.objects.create(
            asignacion=asignacion,
            activo=self.activo_disponible,
            orden=1,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("asignaciones:devolver", args=[asignacion.pk]))
        formset = response.context_data["formset"]

        payload = {
            "fecha_devolucion": "2026-04-21",
            "observaciones": "Equipo recibido",
            "detalles-TOTAL_FORMS": str(formset.total_form_count()),
            "detalles-INITIAL_FORMS": str(formset.initial_form_count()),
            "detalles-MIN_NUM_FORMS": "0",
            "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-id": str(detalle.pk),
            "detalles-0-asignacion": str(asignacion.pk),
            "detalles-0-devolver": "on",
            "detalles-0-estado_activo_devolucion": str(self.estado_no_disponible.pk),
            "detalles-0-observaciones_devolucion": "Sin novedades",
        }

        post_response = self.client.post(
            reverse("asignaciones:devolver", args=[asignacion.pk]),
            payload,
        )

        self.assertEqual(post_response.status_code, 302)

        asignacion.refresh_from_db()
        detalle.refresh_from_db()
        self.activo_disponible.refresh_from_db()

        self.assertEqual(asignacion.estado_asignacion, Asignacion.EstadoAsignacion.CERRADA)
        self.assertFalse(detalle.activa)
        self.assertEqual(detalle.estado_activo_devolucion, self.estado_no_disponible)
        self.assertEqual(self.activo_disponible.estado_activo, self.estado_no_disponible)
        devolucion = Devolucion.objects.get(asignacion=asignacion)
        self.assertEqual(devolucion.codigo_devolucion, f"DEV-{devolucion.pk:05d}")
        self.assertEqual(post_response["Location"], reverse("asignaciones:devolucion_detalle", args=[devolucion.pk]))
        self.assertTrue(
            ActaEntrega.objects.filter(
                asignacion=asignacion,
                tipo=ActaEntrega.TipoActa.ENTREGA,
            ).exists()
        )
        self.assertTrue(
            ActaEntrega.objects.filter(
                asignacion=asignacion,
                tipo=ActaEntrega.TipoActa.RECEPCION,
            ).exists()
        )

    def test_devolucion_view_allows_partial_return_and_keeps_assignment_open(self):
        activo_teclado = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="Logitech",
            modelo="K120",
            serie="KEY001",
            codigo_sap="SAP-ASG-005",
            estado_activo=self.estado_disponible,
        )
        activo_mouse = Activo.objects.create(
            tipo_activo=self.tipo_activo,
            marca="Logitech",
            modelo="M185",
            serie="MOU001",
            codigo_sap="SAP-ASG-006",
            estado_activo=self.estado_disponible,
        )
        asignacion = Asignacion.objects.create(
            colaborador=self.colaborador,
            fecha_asignacion=date(2026, 4, 20),
            usuario_responsable=self.user,
        )
        detalle_pc = AsignacionDetalle.objects.create(
            asignacion=asignacion,
            activo=self.activo_disponible,
            orden=1,
        )
        detalle_teclado = AsignacionDetalle.objects.create(
            asignacion=asignacion,
            activo=activo_teclado,
            orden=2,
        )
        detalle_mouse = AsignacionDetalle.objects.create(
            asignacion=asignacion,
            activo=activo_mouse,
            orden=3,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("asignaciones:devolver", args=[asignacion.pk]))
        formset = response.context_data["formset"]

        payload = {
            "fecha_devolucion": "2026-04-21",
            "observaciones": "Devuelve solo mouse",
            "detalles-TOTAL_FORMS": str(formset.total_form_count()),
            "detalles-INITIAL_FORMS": str(formset.initial_form_count()),
            "detalles-MIN_NUM_FORMS": "0",
            "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-id": str(detalle_pc.pk),
            "detalles-0-asignacion": str(asignacion.pk),
            "detalles-0-estado_activo_devolucion": "",
            "detalles-0-observaciones_devolucion": "",
            "detalles-1-id": str(detalle_teclado.pk),
            "detalles-1-asignacion": str(asignacion.pk),
            "detalles-1-estado_activo_devolucion": "",
            "detalles-1-observaciones_devolucion": "",
            "detalles-2-id": str(detalle_mouse.pk),
            "detalles-2-asignacion": str(asignacion.pk),
            "detalles-2-devolver": "on",
            "detalles-2-estado_activo_devolucion": str(self.estado_no_disponible.pk),
            "detalles-2-observaciones_devolucion": "Mouse recibido",
        }

        post_response = self.client.post(
            reverse("asignaciones:devolver", args=[asignacion.pk]),
            payload,
        )

        self.assertEqual(post_response.status_code, 302)

        asignacion.refresh_from_db()
        detalle_pc.refresh_from_db()
        detalle_teclado.refresh_from_db()
        detalle_mouse.refresh_from_db()

        self.assertEqual(asignacion.estado_asignacion, Asignacion.EstadoAsignacion.PARCIAL)
        self.assertTrue(detalle_pc.activa)
        self.assertTrue(detalle_teclado.activa)
        self.assertFalse(detalle_mouse.activa)
        self.assertEqual(asignacion.devoluciones.count(), 1)
        devolucion = asignacion.devoluciones.first()
        self.assertEqual(devolucion.codigo_devolucion, f"DEV-{devolucion.pk:05d}")
        self.assertEqual(devolucion.detalles.count(), 1)

        detalle_response = self.client.get(reverse("asignaciones:devolucion_detalle", args=[devolucion.pk]))

        self.assertEqual(detalle_response.status_code, 200)
        self.assertContains(detalle_response, devolucion.codigo_devolucion)
        self.assertContains(detalle_response, detalle_mouse.activo.codigo)
        self.assertNotContains(detalle_response, "Acta entrega")

    def test_devolucion_view_allows_historical_ceco_disabled_after_assignment(self):
        asignacion = Asignacion.objects.create(
            colaborador=self.colaborador,
            fecha_asignacion=date(2026, 4, 20),
            observaciones_entrega="Entrega inicial",
            usuario_responsable=self.user,
        )
        detalle = AsignacionDetalle.objects.create(
            asignacion=asignacion,
            activo=self.activo_disponible,
            orden=1,
        )
        self.centro_costo.acepta_asignaciones = False
        self.centro_costo.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse("asignaciones:devolver", args=[asignacion.pk]))
        formset = response.context_data["formset"]

        payload = {
            "fecha_devolucion": "2026-04-21",
            "observaciones": "Equipo recibido",
            "detalles-TOTAL_FORMS": str(formset.total_form_count()),
            "detalles-INITIAL_FORMS": str(formset.initial_form_count()),
            "detalles-MIN_NUM_FORMS": "0",
            "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-id": str(detalle.pk),
            "detalles-0-asignacion": str(asignacion.pk),
            "detalles-0-devolver": "on",
            "detalles-0-estado_activo_devolucion": str(self.estado_no_disponible.pk),
            "detalles-0-observaciones_devolucion": "Sin novedades",
        }

        post_response = self.client.post(
            reverse("asignaciones:devolver", args=[asignacion.pk]),
            payload,
        )

        self.assertEqual(post_response.status_code, 302)

        asignacion.refresh_from_db()
        detalle.refresh_from_db()

        self.assertEqual(asignacion.estado_asignacion, Asignacion.EstadoAsignacion.CERRADA)
        self.assertFalse(detalle.activa)
        self.assertEqual(asignacion.actas.count(), 2)


class AsignacionListViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="listtester",
            password="secret123",
        )
        self.area = Area.objects.create(nombre="Soporte")
        self.cargo = Cargo.objects.create(nombre="Tecnico")
        self.ubicacion = Ubicacion.objects.create(nombre="Sucursal")
        self.empresa = Empresa.objects.create(nombre="Beta")
        self.centro_costo = CentroCosto.objects.create(
            codigo="OPS001",
            nombre="Operaciones TI",
            empresa=self.empresa,
        )
        self.tipo_laptop = TipoActivo.objects.create(nombre="Laptop")
        self.tipo_mouse = TipoActivo.objects.create(nombre="Mouse")
        self.estado_disponible = EstadoActivo.objects.create(
            nombre="Disponible",
            permite_asignacion=True,
        )
        self.estado_asignado = EstadoActivo.objects.create(
            nombre="Asignado",
            permite_asignacion=False,
        )
        self.estado_devuelto = EstadoActivo.objects.create(
            nombre="Bodega",
            permite_asignacion=True,
        )
        self.colaborador_ana = Colaborador.objects.create(
            nombres="Ana",
            apellidos="Perez",
            cedula="1111111111",
            correo_corporativo="ana.list@example.com",
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            centro_costo=self.centro_costo,
            fecha_ingreso=date(2024, 1, 10),
        )
        self.colaborador_luis = Colaborador.objects.create(
            nombres="Luis",
            apellidos="Mena",
            cedula="2222222222",
            correo_corporativo="luis.list@example.com",
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            centro_costo=self.centro_costo,
            fecha_ingreso=date(2024, 2, 15),
        )
        self.activo_laptop = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Dell",
            modelo="Latitude",
            serie="LAT001",
            codigo_sap="SAP-ASG-007",
            estado_activo=self.estado_disponible,
        )
        self.activo_mouse = Activo.objects.create(
            tipo_activo=self.tipo_mouse,
            marca="Logitech",
            modelo="M185",
            serie="MOU001",
            estado_activo=self.estado_disponible,
        )
        self.asignacion_activa = Asignacion.objects.create(
            colaborador=self.colaborador_ana,
            fecha_asignacion=date(2026, 4, 20),
            usuario_responsable=self.user,
        )
        AsignacionDetalle.objects.create(
            asignacion=self.asignacion_activa,
            activo=self.activo_laptop,
            orden=1,
        )
        self.asignacion_cerrada = Asignacion.objects.create(
            colaborador=self.colaborador_luis,
            fecha_asignacion=date(2026, 4, 10),
            usuario_responsable=self.user,
            estado_asignacion=Asignacion.EstadoAsignacion.CERRADA,
            fecha_devolucion=date(2026, 4, 15),
            usuario_recepcion=self.user,
        )
        AsignacionDetalle.objects.create(
            asignacion=self.asignacion_cerrada,
            activo=self.activo_mouse,
            orden=1,
            activa=False,
            estado_activo_devolucion=self.estado_devuelto,
        )
        ActaEntrega.objects.create(
            asignacion=self.asignacion_activa,
            archivo=SimpleUploadedFile("acta.txt", b"contenido"),
            nombre_archivo="acta.txt",
            usuario_generador=self.user,
        )

    def _crear_asignacion_adicional(self, indice, fecha_asignacion):
        colaborador = Colaborador.objects.create(
            nombres=f"Colaborador{indice}",
            apellidos="Extra",
            cedula=f"9{indice:09d}",
            correo_corporativo=f"extra{indice}@example.com",
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            centro_costo=self.centro_costo,
            fecha_ingreso=date(2024, 3, 1),
        )
        activo = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Acer",
            modelo=f"Model {indice}",
            serie=f"SER{indice:03d}",
            codigo_sap=f"SAP-ASG-2{indice:02d}",
            estado_activo=self.estado_disponible,
        )
        asignacion = Asignacion.objects.create(
            colaborador=colaborador,
            fecha_asignacion=fecha_asignacion,
            usuario_responsable=self.user,
        )
        AsignacionDetalle.objects.create(
            asignacion=asignacion,
            activo=activo,
            orden=1,
        )
        return asignacion

    def test_list_view_filters_by_search_term(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("asignaciones:lista"), {"q": self.activo_laptop.codigo})

        self.assertEqual(response.status_code, 200)
        asignaciones = list(response.context["asignaciones"])
        self.assertEqual(asignaciones, [self.asignacion_activa])

    def test_list_view_filters_by_estado(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("asignaciones:lista"), {"estado": Asignacion.EstadoAsignacion.CERRADA})

        self.assertEqual(response.status_code, 200)
        asignaciones = list(response.context["asignaciones"])
        self.assertEqual(asignaciones, [self.asignacion_cerrada])

    def test_list_view_filters_by_acta(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("asignaciones:lista"), {"acta": "con"})

        self.assertEqual(response.status_code, 200)
        asignaciones = list(response.context["asignaciones"])
        self.assertEqual(asignaciones, [self.asignacion_activa])

    def test_list_view_filters_by_fecha_range(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("asignaciones:lista"),
            {"fecha_desde": "2026-04-15", "fecha_hasta": "2026-04-30"},
        )

        self.assertEqual(response.status_code, 200)
        asignaciones = list(response.context["asignaciones"])
        self.assertEqual(asignaciones, [self.asignacion_activa])

    def test_list_view_orders_by_recent_dates_by_default(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("asignaciones:lista"))

        self.assertEqual(response.status_code, 200)
        asignaciones = list(response.context["asignaciones"])
        self.assertEqual(asignaciones, [self.asignacion_activa, self.asignacion_cerrada])
        self.assertEqual(response.context["orden_seleccionado"], "recientes")
        self.assertContains(response, "data-scroll-to-results")
        self.assertContains(response, 'id="resultados"')

    def test_list_view_orders_by_oldest_dates_when_requested(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("asignaciones:lista"), {"orden": "antiguas"})

        self.assertEqual(response.status_code, 200)
        asignaciones = list(response.context["asignaciones"])
        self.assertEqual(asignaciones, [self.asignacion_cerrada, self.asignacion_activa])
        self.assertContains(response, "Mas antiguas primero")

    def test_list_view_orders_by_recent_activity_when_requested(self):
        self.client.force_login(self.user)

        Asignacion.objects.filter(pk=self.asignacion_activa.pk).update(updated_at=timezone.now())

        response = self.client.get(reverse("asignaciones:lista"), {"orden": "actividad"})

        self.assertEqual(response.status_code, 200)
        asignaciones = list(response.context["asignaciones"])
        self.assertEqual(asignaciones[0], self.asignacion_activa)
        self.assertEqual(response.context["orden_seleccionado"], "actividad")
        self.assertContains(response, "Actividad mas reciente")

    def test_list_view_paginates_at_ten_items_and_preserves_filters(self):
        self.client.force_login(self.user)

        for indice in range(1, 10):
            self._crear_asignacion_adicional(indice, date(2026, 4, indice))

        response = self.client.get(reverse("asignaciones:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(response.context["paginator"].per_page, 10)
        self.assertEqual(len(list(response.context["asignaciones"])), 10)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertContains(response, "Mostrando 1 a 10 de 11 asignaciones")
        self.assertEqual(response.context["query_string"], "")

        second_page = self.client.get(reverse("asignaciones:lista"), {"page": 2})

        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(list(second_page.context["asignaciones"])), 1)
        self.assertEqual(second_page.context["page_obj"].number, 2)
        self.assertFalse(second_page.context["page_obj"].has_next())
        self.assertContains(second_page, "Mostrando 11 a 11 de 11 asignaciones")

        filtered = self.client.get(
            reverse("asignaciones:lista"),
            {"q": self.activo_laptop.codigo},
        )

        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.context["query_string"], f"q={self.activo_laptop.codigo}")
