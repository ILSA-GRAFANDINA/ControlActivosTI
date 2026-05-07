from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import shutil
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.utils import override_settings
from django.test import TestCase
from django.urls import reverse

from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.catalogos.models import Area, Cargo, CentroCosto, Empresa, EstadoActivo, TipoActivo, TipoEventoActivo, Ubicacion
from apps.colaboradores.models import Colaborador
from PIL import Image

from apps.activos.admin import ActivoAdminForm, EventoActivoAdminForm, FotoActivoInlineForm
from apps.activos.models import Activo, EventoActivo, FotoActivo


User = get_user_model()


def make_test_image_file(name="activo.jpg", size=(2200, 1400), color=(36, 99, 235)):
    buffer = BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(buffer, format="JPEG", quality=95)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def make_test_media_root():
    media_root = Path.cwd() / "test-media" / uuid.uuid4().hex
    media_root.mkdir(parents=True, exist_ok=True)
    return media_root


class ActivoAdminFormTests(TestCase):
    def setUp(self):
        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        self.tipo_mouse = TipoActivo.objects.create(nombre="Mouse")
        self.tipo_laptop = TipoActivo.objects.create(nombre="Laptop")

    def _data_base(self, tipo_activo):
        return {
            "tipo_activo": tipo_activo.pk,
            "marca": "Logitech",
            "modelo": "MX",
            "serie": "S/N",
            "cpu": "Intel Core i5",
            "ram": "16 GB",
            "disco": "512 GB SSD",
            "sistema_operativo": "Windows",
            "fecha_compra": "",
            "valor": "",
            "estado_activo": self.estado.pk,
            "observaciones": "",
        }

    def test_limpia_especificaciones_tecnicas_si_no_aplican_al_tipo(self):
        form = ActivoAdminForm(data=self._data_base(self.tipo_mouse))

        self.assertTrue(form.is_valid(), form.errors)
        activo = form.save()

        self.assertEqual(activo.cpu, "")
        self.assertEqual(activo.ram, "")
        self.assertEqual(activo.disco, "")
        self.assertEqual(activo.sistema_operativo, "")

    def test_conserva_especificaciones_tecnicas_para_laptops(self):
        form = ActivoAdminForm(data=self._data_base(self.tipo_laptop))

        self.assertTrue(form.is_valid(), form.errors)
        activo = form.save()

        self.assertEqual(activo.cpu, "Intel Core i5")
        self.assertEqual(activo.ram, "16 GB")
        self.assertEqual(activo.disco, "512 GB SSD")
        self.assertEqual(activo.sistema_operativo, "Windows")


class ActivoCodigoTests(TestCase):
    def setUp(self):
        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)

    def test_prefijos_principales_del_inventario(self):
        casos = [
            ("Laptop", "LAP"),
            ("Mouse", "MOU"),
            ("MousePad", "MOUP"),
            ("Teclado", "TEC"),
            ("Base para Laptop", "BLP"),
            ("PC", "PC"),
        ]

        for indice, (nombre_tipo, prefijo) in enumerate(casos, start=1):
            tipo = TipoActivo.objects.create(nombre=nombre_tipo)
            activo = Activo.objects.create(
                tipo_activo=tipo,
                marca="Marca",
                modelo=f"Modelo {indice}",
                serie=f"SERIE-{indice}",
                estado_activo=self.estado,
            )

            self.assertTrue(activo.codigo.startswith(f"{prefijo}-"))

    def test_tipo_nuevo_extiende_prefijo_si_las_tres_primeras_letras_ya_existen(self):
        tipo_cable = TipoActivo.objects.create(nombre="Cable")
        primer_activo = Activo.objects.create(
            tipo_activo=tipo_cable,
            marca="Generico",
            modelo="USB",
            serie="CAB-001",
            estado_activo=self.estado,
        )
        segundo_activo = Activo.objects.create(
            tipo_activo=tipo_cable,
            marca="Generico",
            modelo="HDMI",
            serie="CAB-002",
            estado_activo=self.estado,
        )
        tipo_cabina = TipoActivo.objects.create(nombre="Cabina")
        activo_colision = Activo.objects.create(
            tipo_activo=tipo_cabina,
            marca="Generico",
            modelo="Audio",
            serie="CABI-001",
            estado_activo=self.estado,
        )

        self.assertEqual(primer_activo.codigo, "CAB-0001")
        self.assertEqual(segundo_activo.codigo, "CAB-0002")
        self.assertEqual(activo_colision.codigo, "CABI-0001")

    def test_tipo_nuevo_no_usa_prefijo_act(self):
        tipo = TipoActivo.objects.create(nombre="Activo especial")
        activo = Activo.objects.create(
            tipo_activo=tipo,
            marca="Generico",
            modelo="Especial",
            serie="ACT-ESPECIAL-001",
            estado_activo=self.estado,
        )

        self.assertEqual(activo.codigo, "ACTI-0001")


class FotoActivoInlineFormTests(TestCase):
    def test_conserva_imagen_existente_si_no_se_sube_otra(self):
        estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        tipo_mouse = TipoActivo.objects.create(nombre="Mouse")
        activo = Activo.objects.create(
            tipo_activo=tipo_mouse,
            marca="Logitech",
            modelo="MX",
            serie="S/N",
            estado_activo=estado,
        )
        foto = FotoActivo.objects.create(
            activo=activo,
            imagen="activos/MOU-0001/mouse.jpg",
            descripcion="Foto frontal",
            orden=1,
        )

        form = FotoActivoInlineForm(
            data={
                "activo": activo.pk,
                "descripcion": "Foto actualizada",
                "orden": 1,
            },
            instance=foto,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["imagen"], foto.imagen)


class FotoActivoOptimizadaTests(TestCase):
    def setUp(self):
        self.media_root = make_test_media_root()
        self.override_media = override_settings(MEDIA_ROOT=self.media_root)
        self.override_media.enable()

        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        self.tipo = TipoActivo.objects.create(nombre="Laptop")
        self.activo = Activo.objects.create(
            tipo_activo=self.tipo,
            marca="Dell",
            modelo="Latitude",
            serie="IMG-001",
            estado_activo=self.estado,
        )

    def tearDown(self):
        self.override_media.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    def test_normaliza_imagen_y_crea_variantes_optimizada(self):
        foto = FotoActivo.objects.create(
            activo=self.activo,
            imagen=make_test_image_file(),
            descripcion="Frontal",
            orden=1,
        )

        foto.refresh_from_db()

        self.assertTrue(foto.imagen.name.endswith(".webp"))
        self.assertTrue(foto.imagen_thumb_url.endswith("_thumb.webp"))
        self.assertTrue(foto.imagen_medium_url.endswith("_medium.webp"))
        self.assertTrue(foto.imagen_large_url.endswith("_large.webp"))
        self.assertTrue(self.media_root.joinpath(foto.imagen.name).exists())
        self.assertTrue(self.media_root.joinpath(foto._variant_name("thumb")).exists())
        self.assertTrue(self.media_root.joinpath(foto._variant_name("medium")).exists())
        self.assertTrue(self.media_root.joinpath(foto._variant_name("large")).exists())


class EventoActivoAdminFormTests(TestCase):
    def test_labels_aclaran_valor_tecnico_y_costo(self):
        form = EventoActivoAdminForm()

        self.assertEqual(
            form.fields["valor_nuevo"].label,
            "Nuevo valor final del dato seleccionado",
        )
        self.assertIn("No es el precio", form.fields["valor_nuevo"].help_text)
        self.assertEqual(
            form.fields["costo_adicional"].label,
            "Costo del repuesto o mejora",
        )


class EventoActivoAdminViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin",
            password="testpass123",
            email="admin@example.com",
        )
        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        self.tipo_laptop = TipoActivo.objects.create(nombre="Laptop")
        self.activo = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Dell",
            modelo="Latitude",
            serie="LAP-100",
            estado_activo=self.estado,
        )

    def test_add_view_prefills_active_from_querystring(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("admin:activos_eventoactivo_add"),
            {"activo": self.activo.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["adminform"].form.initial.get("activo"), self.activo.pk)
        self.assertContains(response, "Activo afectado")


class EventoActivoImpactoTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(username="soporte", password="testpass123")
        self.estado_disponible = EstadoActivo.objects.create(
            nombre="Disponible",
            permite_asignacion=True,
        )
        self.estado_mantenimiento = EstadoActivo.objects.create(
            nombre="Mantenimiento",
            permite_asignacion=False,
        )
        self.tipo_laptop = TipoActivo.objects.create(nombre="Laptop")
        self.tipo_mouse = TipoActivo.objects.create(nombre="Mouse")
        self.tipo_evento = TipoEventoActivo.objects.create(nombre="Cambio de RAM")
        self.tipo_mantenimiento = TipoEventoActivo.objects.create(nombre="Mantenimiento")

    def test_evento_tecnico_actualiza_ram_y_suma_valor(self):
        activo = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Dell",
            modelo="Latitude",
            serie="ABC123",
            ram="8 GB",
            valor=Decimal("500.00"),
            estado_activo=self.estado_disponible,
        )

        evento = EventoActivo.objects.create(
            activo=activo,
            tipo_evento=self.tipo_evento,
            detalle="Se instala modulo adicional de memoria.",
            campo_afectado=EventoActivo.CampoAfectado.RAM,
            valor_nuevo="16 GB",
            costo_adicional=Decimal("40.00"),
            sumar_costo_al_valor=True,
            usuario_responsable=self.usuario,
        )

        activo.refresh_from_db()
        evento.refresh_from_db()

        self.assertEqual(evento.valor_anterior, "8 GB")
        self.assertEqual(activo.ram, "16 GB")
        self.assertEqual(activo.valor, Decimal("540.00"))

    def test_evento_puede_actualizar_estado_del_activo(self):
        activo = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="HP",
            modelo="ProBook",
            serie="DEF456",
            ram="8 GB",
            estado_activo=self.estado_disponible,
        )

        EventoActivo.objects.create(
            activo=activo,
            tipo_evento=self.tipo_mantenimiento,
            detalle="Equipo pasa a revision preventiva.",
            nuevo_estado_activo=self.estado_mantenimiento,
            usuario_responsable=self.usuario,
        )

        activo.refresh_from_db()

        self.assertEqual(activo.estado_activo, self.estado_mantenimiento)

    def test_evento_informativo_no_modifica_ficha_del_activo(self):
        activo = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Lenovo",
            modelo="ThinkPad",
            serie="GHI789",
            ram="8 GB",
            valor=Decimal("600.00"),
            estado_activo=self.estado_disponible,
        )

        EventoActivo.objects.create(
            activo=activo,
            tipo_evento=self.tipo_mantenimiento,
            detalle="Limpieza general sin cambio de componentes.",
            usuario_responsable=self.usuario,
        )

        activo.refresh_from_db()

        self.assertEqual(activo.ram, "8 GB")
        self.assertEqual(activo.valor, Decimal("600.00"))

    def test_no_permite_evento_tecnico_en_activo_sin_especificaciones(self):
        activo = Activo.objects.create(
            tipo_activo=self.tipo_mouse,
            marca="Logitech",
            modelo="MX",
            serie="S/N",
            estado_activo=self.estado_disponible,
        )

        evento = EventoActivo(
            activo=activo,
            tipo_evento=self.tipo_evento,
            detalle="Intento de cambio tecnico no aplicable.",
            campo_afectado=EventoActivo.CampoAfectado.RAM,
            valor_nuevo="16 GB",
            usuario_responsable=self.usuario,
        )

        with self.assertRaises(ValidationError):
            evento.full_clean()


class ActivoListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="inventario", password="testpass123")
        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        self.tipo_laptop = TipoActivo.objects.create(nombre="Laptop")
        self.tipo_mouse = TipoActivo.objects.create(nombre="Mouse")

        Activo.objects.create(
            tipo_activo=self.tipo_mouse,
            marca="Logitech",
            modelo="M185",
            serie="MOU-001",
            estado_activo=self.estado,
        )
        Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Dell",
            modelo="Latitude",
            serie="LAP-001",
            estado_activo=self.estado,
        )

    def test_list_view_shows_type_separators(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("activos:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop")
        self.assertContains(response, "Mouse")
        self.assertContains(response, 'text-[11px] font-semibold uppercase')
        self.assertContains(response, "data-scroll-to-results")
        self.assertContains(response, 'id="resultados"')


class ActivoDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="detalle", password="testpass123")
        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        self.estado_asignado = EstadoActivo.objects.create(nombre="Asignado", permite_asignacion=False)
        self.estado_devuelto = EstadoActivo.objects.create(nombre="Bodega", permite_asignacion=True)
        self.tipo_laptop = TipoActivo.objects.create(nombre="Laptop")
        self.area = Area.objects.create(nombre="TI")
        self.cargo = Cargo.objects.create(nombre="Analista")
        self.empresa = Empresa.objects.create(nombre="Acme")
        self.ubicacion = Ubicacion.objects.create(nombre="Matriz")
        self.centro_costo = CentroCosto.objects.create(
            codigo="TI001",
            nombre="Tecnologia",
            empresa=self.empresa,
        )
        self.historial_asignaciones = []
        self.colaborador = Colaborador.objects.create(
            nombres="Ana",
            apellidos="Perez",
            cedula="0102030405",
            correo_corporativo="ana@example.com",
            centro_costo=self.centro_costo,
            empresa=self.empresa,
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            fecha_ingreso=date(2024, 1, 10),
        )
        self.activo = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Dell",
            modelo="Latitude",
            serie="LAP-001",
            estado_activo=self.estado,
        )

        for indice in range(1, 6):
            asignacion = Asignacion.objects.create(
                colaborador=self.colaborador,
                fecha_asignacion=date(2026, 4, indice),
                fecha_devolucion=date(2026, 4, indice + 1),
                usuario_responsable=self.user,
                usuario_recepcion=self.user,
                estado_asignacion=Asignacion.EstadoAsignacion.CERRADA,
            )
            AsignacionDetalle.objects.create(
                asignacion=asignacion,
                activo=self.activo,
                orden=indice,
                activa=False,
                estado_activo_devolucion=self.estado_devuelto,
            )
            self.historial_asignaciones.append(asignacion)

        self.asignacion_activa = Asignacion.objects.create(
            colaborador=self.colaborador,
            fecha_asignacion=date(2026, 4, 6),
            usuario_responsable=self.user,
        )
        AsignacionDetalle.objects.create(
            asignacion=self.asignacion_activa,
            activo=self.activo,
            orden=6,
        )

    def test_detail_view_shows_last_five_assignments_and_keeps_full_history_expandable(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("activos:detalle", args=[self.activo.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_historial_asignaciones"], 6)
        self.assertEqual(len(response.context["historial_asignaciones"]), 5)
        self.assertEqual(len(response.context["historial_asignaciones_completo"]), 1)
        self.assertContains(response, "Mostrando las 5 asignaciones")
        self.assertContains(response, "Ver historial completo")
        self.assertContains(response, "LAP-001")
        self.assertContains(response, reverse("admin:activos_activo_change", args=[self.activo.pk]))
        self.assertContains(response, reverse("asignaciones:detalle", args=[self.asignacion_activa.pk]))
        self.assertContains(response, reverse("asignaciones:detalle", args=[self.historial_asignaciones[0].pk]))

    def test_detail_view_blocks_quarantine_from_available_message(self):
        cuarentena = EstadoActivo.objects.create(nombre="Cuarentena", permite_asignacion=False)
        activo_cuarentena = Activo.objects.create(
            tipo_activo=self.tipo_laptop,
            marca="Lenovo",
            modelo="ThinkPad",
            serie="LAP-002",
            estado_activo=cuarentena,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("activos:detalle", args=[activo_cuarentena.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este activo no está disponible para una nueva asignación")
        self.assertContains(response, "Cuarentena")
        self.assertNotContains(response, "Este activo está disponible para una nueva asignación.")

    def test_detail_view_renders_photo_carousel_with_optimized_urls(self):
        media_root = make_test_media_root()
        try:
            with override_settings(MEDIA_ROOT=media_root):
                FotoActivo.objects.create(
                    activo=self.activo,
                    imagen=make_test_image_file("portada.jpg"),
                    descripcion="Portada",
                    orden=1,
                )

                self.client.force_login(self.user)
                response = self.client.get(reverse("activos:detalle", args=[self.activo.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "data-photo-carousel")
            self.assertContains(response, "data-carousel-slide")
            self.assertContains(response, "data-image-modal")
            self.assertContains(response, ".webp")
            self.assertNotContains(response, 'target="_blank"')
        finally:
            shutil.rmtree(media_root, ignore_errors=True)
