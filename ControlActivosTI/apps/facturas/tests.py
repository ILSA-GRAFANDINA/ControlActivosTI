import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from apps.activos.forms import ActivoAdminForm
from apps.activos.models import Activo
from apps.catalogos.models import Empresa, EstadoActivo, TipoActivo
from apps.proveedores.models import Proveedor

from apps.facturas.forms import FacturaCompraForm
from apps.facturas.models import FacturaCompra, ReemplazoDocumentoFactura


def pdf_valido(nombre="factura.pdf", paginas=1):
    buffer = BytesIO()
    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(width=612, height=792)
    writer.write(buffer)
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="application/pdf")


def datos_proveedor(identificacion="1790012345001", razon="Proveedor Facturas", activo=True):
    return {
        "tipo_proveedor": Proveedor.TipoProveedor.EMPRESA,
        "tipo_identificacion": Proveedor.TipoIdentificacion.RUC,
        "identificacion": identificacion,
        "razon_social": razon,
        "pais": "Ecuador",
        "activo": activo,
    }


class FacturaBaseTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.mkdtemp(prefix="facturas-tests-")
        self.override = override_settings(
            MEDIA_ROOT=self.media_dir,
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": self.media_dir},
                },
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                "facturas": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": self.media_dir},
                },
            },
        )
        self.override.enable()
        self._factura_storage = FacturaCompra._meta.get_field("archivo").storage
        self._reemplazo_storage = ReemplazoDocumentoFactura._meta.get_field("archivo_anterior").storage
        storage_pruebas = FileSystemStorage(location=self.media_dir)
        FacturaCompra._meta.get_field("archivo").storage = storage_pruebas
        ReemplazoDocumentoFactura._meta.get_field("archivo_anterior").storage = storage_pruebas
        self.user = get_user_model().objects.create_user("facturas", password="testpass123")
        self.proveedor = Proveedor.objects.create(**datos_proveedor())
        self.otro_proveedor = Proveedor.objects.create(
            **datos_proveedor("1790012345002", "Otro proveedor")
        )
        self.empresa = Empresa.objects.create(nombre="ILSA")
        self.otra_empresa = Empresa.objects.create(nombre="GRAFANDINA")
        self.tipo = TipoActivo.objects.create(nombre="Laptop")
        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)

    def tearDown(self):
        FacturaCompra._meta.get_field("archivo").storage = self._factura_storage
        ReemplazoDocumentoFactura._meta.get_field("archivo_anterior").storage = self._reemplazo_storage
        self.override.disable()
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def crear_factura(self, numero="FAC-001", proveedor=None, empresa=None, activa=True):
        form = FacturaCompraForm(
            data={
                "proveedor": (proveedor or self.proveedor).pk,
                "empresa": (empresa or self.empresa).pk,
                "numero_factura": numero,
                "fecha_emision": timezone.localdate(),
                "observaciones": "Compra de equipos",
            },
            files={"archivo": pdf_valido(f"{numero}.pdf")},
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        factura = form.save()
        if not activa:
            factura.activa = False
            factura.save(update_fields=["activa", "updated_at"])
        return factura

    def crear_activo(self, **cambios):
        datos = {
            "tipo_activo": self.tipo,
            "empresa": self.empresa,
            "proveedor": self.proveedor,
            "marca": "Dell",
            "modelo": "Latitude",
            "serie": "SER-001",
            "codigo_sap": "SAP-001",
            "estado_activo": self.estado,
        }
        datos.update(cambios)
        return Activo.objects.create(**datos)


class FacturaModelFormTests(FacturaBaseTests):
    def test_crea_factura_valida_normaliza_y_registra_metadatos(self):
        factura = self.crear_factura(" fac 001 ")
        self.assertEqual(factura.numero_factura, "FAC001")
        self.assertEqual(factura.cargado_por, self.user)
        self.assertEqual(len(factura.checksum_sha256), 64)
        self.assertEqual(factura.numero_paginas, 1)
        self.assertGreater(factura.tamano_original, 0)
        self.assertTrue(factura.archivo.name.startswith("facturas/"))

    def test_rechaza_numero_duplicado_por_proveedor_y_empresa(self):
        self.crear_factura("FAC-001")
        form = FacturaCompraForm(
            data={"proveedor": self.proveedor.pk, "empresa": self.empresa.pk, "numero_factura": " fac-001 ", "fecha_emision": timezone.localdate()},
            files={"archivo": pdf_valido("otra.pdf", paginas=2)}, user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("numero_factura", form.errors)

    def test_permite_mismo_numero_para_otra_empresa(self):
        self.crear_factura("FAC-001")
        factura = self.crear_factura("FAC-001", empresa=self.otra_empresa)
        self.assertEqual(factura.empresa, self.otra_empresa)

    def test_rechaza_fecha_futura(self):
        form = FacturaCompraForm(
            data={"proveedor": self.proveedor.pk, "empresa": self.empresa.pk, "numero_factura": "FUTURA", "fecha_emision": timezone.localdate() + timedelta(days=1)},
            files={"archivo": pdf_valido()}, user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("fecha_emision", form.errors)

    def test_rechaza_archivo_falso_corrupto_y_sobre_limite(self):
        base = {"proveedor": self.proveedor.pk, "empresa": self.empresa.pk, "numero_factura": "INVALIDA", "fecha_emision": timezone.localdate()}
        falso = FacturaCompraForm(data=base, files={"archivo": SimpleUploadedFile("falso.pdf", b"no es pdf", content_type="application/pdf")}, user=self.user)
        self.assertFalse(falso.is_valid())
        corrupto = FacturaCompraForm(data=base, files={"archivo": SimpleUploadedFile("corrupto.pdf", b"%PDF-1.4\nobjeto roto\n%%EOF", content_type="application/pdf")}, user=self.user)
        self.assertFalse(corrupto.is_valid())
        with override_settings(FACTURAS_PDF_MAX_SIZE=20):
            grande = FacturaCompraForm(data=base, files={"archivo": pdf_valido()}, user=self.user)
            self.assertFalse(grande.is_valid())

    def test_rechaza_pdf_cifrado(self):
        buffer = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secreto")
        writer.write(buffer)
        form = FacturaCompraForm(
            data={"proveedor": self.proveedor.pk, "empresa": self.empresa.pk, "numero_factura": "CIFRADA", "fecha_emision": timezone.localdate()},
            files={"archivo": SimpleUploadedFile("cifrada.pdf", buffer.getvalue(), content_type="application/pdf")}, user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("cifradas", str(form.errors))

    def test_conserva_original_cuando_detecta_firma_digital(self):
        archivo = pdf_valido()
        contenido = archivo.read() + b"\n% /ByteRange /Type /Sig /SubFilter\n"
        form = FacturaCompraForm(
            data={"proveedor": self.proveedor.pk, "empresa": self.empresa.pk, "numero_factura": "FIRMADA", "fecha_emision": timezone.localdate()},
            files={"archivo": SimpleUploadedFile("firmada.pdf", contenido, content_type="application/pdf")}, user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)
        factura = form.save()
        self.assertEqual(factura.estado_compresion, FacturaCompra.EstadoCompresion.FIRMA_DIGITAL)
        self.assertEqual(factura.tamano_original, factura.tamano_almacenado)

    def test_detecta_documento_duplicado_por_checksum(self):
        archivo = pdf_valido()
        contenido = archivo.read()
        primero = FacturaCompraForm(
            data={"proveedor": self.proveedor.pk, "empresa": self.empresa.pk, "numero_factura": "DUP-1", "fecha_emision": timezone.localdate()},
            files={"archivo": SimpleUploadedFile("primero.pdf", contenido, content_type="application/pdf")}, user=self.user,
        )
        self.assertTrue(primero.is_valid(), primero.errors)
        primero.save()
        segundo = FacturaCompraForm(
            data={"proveedor": self.proveedor.pk, "empresa": self.empresa.pk, "numero_factura": "DUP-2", "fecha_emision": timezone.localdate()},
            files={"archivo": SimpleUploadedFile("segundo.pdf", contenido, content_type="application/pdf")}, user=self.user,
        )
        self.assertFalse(segundo.is_valid())
        self.assertIn("mismo documento", str(segundo.errors))


class FacturaActivoTests(FacturaBaseTests):
    def test_asocia_varios_activos_y_autocompleta_proveedor_empresa(self):
        factura = self.crear_factura()
        primero = self.crear_activo(factura_compra=factura)
        segundo = self.crear_activo(
            serie="SER-002", codigo_sap="SAP-002", proveedor=None, empresa=None, factura_compra=factura
        )
        self.assertEqual(primero.factura_compra, factura)
        self.assertEqual(segundo.proveedor, self.proveedor)
        self.assertEqual(segundo.empresa, self.empresa)
        self.assertEqual(factura.activos.count(), 2)

    def test_rechaza_proveedor_y_empresa_incompatibles(self):
        factura = self.crear_factura()
        with self.assertRaises(ValidationError):
            self.crear_activo(proveedor=self.otro_proveedor, factura_compra=factura)
        with self.assertRaises(ValidationError):
            self.crear_activo(empresa=self.otra_empresa, factura_compra=factura)

    def test_desvincular_conserva_proveedor_y_bloquea_cambios_factura(self):
        factura = self.crear_factura()
        activo = self.crear_activo(factura_compra=factura)
        activo.factura_compra = None
        activo.save()
        self.assertEqual(activo.proveedor, self.proveedor)
        activo.factura_compra = factura
        activo.save()
        factura.proveedor = self.otro_proveedor
        with self.assertRaises(ValidationError):
            factura.save()

    def test_protege_eliminacion_de_factura_y_proveedor(self):
        factura = self.crear_factura()
        self.crear_activo(factura_compra=factura)
        with self.assertRaises(ProtectedError):
            factura.delete()
        with self.assertRaises(ProtectedError):
            self.proveedor.delete()

    def test_formulario_activo_excluye_archivada_y_conserva_historica(self):
        factura = self.crear_factura(activa=False)
        self.assertNotIn(factura, ActivoAdminForm().fields["factura_compra"].queryset)
        activo = self.crear_activo(factura_compra=None)
        Activo.objects.filter(pk=activo.pk).update(factura_compra=factura)
        activo.refresh_from_db()
        form = ActivoAdminForm(instance=activo)
        self.assertIn(factura, form.fields["factura_compra"].queryset)


class FacturaViewsTests(FacturaBaseTests):
    def setUp(self):
        super().setUp()
        permisos = Permission.objects.filter(content_type__app_label="facturas")
        self.user.user_permissions.set(permisos)
        self.client.force_login(self.user)

    def test_listado_busqueda_filtros_y_detalle(self):
        factura = self.crear_factura()
        self.crear_activo(factura_compra=factura)
        response = self.client.get(reverse("facturas:lista"), {"q": "SER-001", "relaciones": "con_activos"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, factura.numero_factura)
        self.assertContains(response, "Listado de facturas")
        self.assertContains(response, "1 factura encontrada")
        self.assertContains(response, "Agregar factura")
        self.assertContains(response, "bg-cyan-600")
        response = self.client.get(reverse("facturas:detalle", args=[factura.pk]))
        self.assertContains(response, "SER-001")
        self.assertContains(response, "Ocultar SHA-256")
        self.assertContains(response, 'id="factura-sha256"')
        self.assertContains(response, "hidden")

    def test_descarga_protegida_y_autorizada(self):
        factura = self.crear_factura()
        response = self.client.get(reverse("facturas:documento", args=[factura.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertNotIn(str(self.media_dir), str(response.headers))
        self.client.logout()
        response = self.client.get(reverse("facturas:documento", args=[factura.pk]))
        self.assertEqual(response.status_code, 403)

    def test_usuario_sin_permiso_no_puede_consultar_ni_descargar(self):
        factura = self.crear_factura()
        otro = get_user_model().objects.create_user("sin-permiso", password="testpass123")
        self.client.force_login(otro)
        self.assertEqual(self.client.get(reverse("facturas:lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("facturas:documento", args=[factura.pk])).status_code, 403)

    def test_archiva_y_no_elimina_factura_con_activos(self):
        factura = self.crear_factura()
        self.crear_activo(factura_compra=factura)
        self.client.post(reverse("facturas:estado", args=[factura.pk]))
        factura.refresh_from_db()
        self.assertFalse(factura.activa)
        response = self.client.post(reverse("facturas:eliminar", args=[factura.pk]))
        self.assertRedirects(response, reverse("facturas:detalle", args=[factura.pk]))
        self.assertTrue(FacturaCompra.objects.filter(pk=factura.pk).exists())

    def test_asocia_y_desvincula_activos_con_permiso_backend(self):
        self.user.user_permissions.add(Permission.objects.get(codename="change_activo"))
        factura = self.crear_factura()
        activo = self.crear_activo(proveedor=None, empresa=None)
        response = self.client.post(
            reverse("facturas:asociar_activos", args=[factura.pk]), {"activos": [activo.pk]}
        )
        self.assertRedirects(response, reverse("facturas:detalle", args=[factura.pk]))
        activo.refresh_from_db()
        self.assertEqual(activo.factura_compra, factura)
        self.assertEqual(activo.proveedor, self.proveedor)
        response = self.client.post(reverse("facturas:asociar_activos", args=[factura.pk]), {})
        self.assertRedirects(response, reverse("facturas:detalle", args=[factura.pk]))
        activo.refresh_from_db()
        self.assertIsNone(activo.factura_compra)
        self.assertEqual(activo.proveedor, self.proveedor)

    def test_reemplazo_conserva_version_y_trazabilidad(self):
        factura = self.crear_factura()
        checksum_anterior = factura.checksum_sha256
        response = self.client.post(
            reverse("facturas:reemplazar", args=[factura.pk]),
            {"archivo": pdf_valido("corregida.pdf", paginas=2), "motivo": "Correccion autorizada del documento"},
        )
        self.assertRedirects(response, reverse("facturas:detalle", args=[factura.pk]))
        factura.refresh_from_db()
        reemplazo = factura.reemplazos.get()
        self.assertEqual(reemplazo.checksum_anterior, checksum_anterior)
        self.assertTrue(reemplazo.archivo_anterior.storage.exists(reemplazo.archivo_anterior.name))
        self.assertNotEqual(factura.checksum_sha256, checksum_anterior)
        self.assertTrue(factura.eventos.filter(accion="reemplazo").exists())
