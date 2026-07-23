from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.activos.forms import ActivoAdminForm
from apps.activos.models import Activo
from apps.catalogos.models import Empresa, EstadoActivo, TipoActivo

from apps.proveedores.models import Proveedor


def datos_proveedor(**cambios):
    datos = {
        "tipo_proveedor": Proveedor.TipoProveedor.EMPRESA,
        "tipo_identificacion": Proveedor.TipoIdentificacion.RUC,
        "identificacion": "1790012345001",
        "razon_social": "Tecnologia Andina S.A.",
        "nombre_comercial": "TecAndina",
        "nombre_contacto": "Ana Torres",
        "correo_electronico": "ana@example.com",
        "telefono": "+593 2 555-0101",
        "direccion": "Av. Principal 123",
        "ciudad": "Quito",
        "pais": "Ecuador",
        "observaciones": "Proveedor homologado",
    }
    datos.update(cambios)
    return datos


class ProveedorModelTests(TestCase):
    def test_crea_y_normaliza_proveedor_valido(self):
        proveedor = Proveedor.objects.create(**datos_proveedor(identificacion="179-001-2345 001"))
        self.assertEqual(proveedor.identificacion, "1790012345001")
        self.assertEqual(str(proveedor), "TecAndina")
        self.assertIsInstance(proveedor.telefono, str)

    def test_rechaza_identificacion_duplicada_normalizada(self):
        Proveedor.objects.create(**datos_proveedor())
        duplicado = Proveedor(**datos_proveedor(identificacion="179-001-2345-001", razon_social="Otra"))
        with self.assertRaises(ValidationError):
            duplicado.save()

    def test_valida_ruc_y_cedula_ecuatorianos(self):
        with self.assertRaises(ValidationError):
            Proveedor.objects.create(**datos_proveedor(identificacion="123", tipo_identificacion="ruc"))
        with self.assertRaises(ValidationError):
            Proveedor.objects.create(**datos_proveedor(identificacion="123456789", tipo_identificacion="cedula"))

    def test_acepta_identificacion_extranjera(self):
        proveedor = Proveedor.objects.create(**datos_proveedor(
            identificacion="US-AB 123", tipo_identificacion="extranjera", pais="Estados Unidos"
        ))
        self.assertEqual(proveedor.identificacion, "USAB123")


class ProveedorViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("proveedores", password="testpass123")
        permisos = Permission.objects.filter(content_type__app_label="proveedores")
        self.user.user_permissions.set(permisos)
        self.client.force_login(self.user)

    def test_crear_editar_buscar_filtrar_y_paginar(self):
        response = self.client.post(reverse("proveedores:nuevo"), datos_proveedor())
        self.assertRedirects(response, reverse("proveedores:lista"))
        proveedor = Proveedor.objects.get()

        edicion = datos_proveedor(nombre_comercial="TecAndina Ecuador")
        response = self.client.post(reverse("proveedores:editar", args=[proveedor.pk]), edicion)
        self.assertRedirects(response, reverse("proveedores:detalle", args=[proveedor.pk]))
        proveedor.refresh_from_db()
        self.assertEqual(proveedor.nombre_comercial, "TecAndina Ecuador")

        for numero in range(11):
            Proveedor.objects.create(**datos_proveedor(
                identificacion=f"EXT{numero:02d}", tipo_identificacion="extranjera",
                pais="Colombia", razon_social=f"Proveedor {numero}", nombre_comercial="",
                activo=numero % 2 == 0,
            ))
        response = self.client.get(reverse("proveedores:lista"), {"q": "Ana Torres", "estado": "activo"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item.activo for item in response.context["proveedores"]))
        self.assertContains(response, "7 proveedores encontrados")
        self.assertContains(response, "data-compact-filters")
        self.assertContains(response, "data-filter-actions")
        response = self.client.get(reverse("proveedores:lista"))
        self.assertTrue(response.context["is_paginated"])
        self.assertContains(response, "12 proveedores encontrados")

    def test_activar_y_desactivar(self):
        proveedor = Proveedor.objects.create(**datos_proveedor())
        self.client.post(reverse("proveedores:estado", args=[proveedor.pk]))
        proveedor.refresh_from_db()
        self.assertFalse(proveedor.activo)
        self.client.post(reverse("proveedores:estado", args=[proveedor.pk]))
        proveedor.refresh_from_db()
        self.assertTrue(proveedor.activo)

    def test_columnas_predeterminadas_y_vista_de_tabla_personalizada(self):
        Proveedor.objects.create(**datos_proveedor())

        response = self.client.get(reverse("proveedores:lista"))
        self.assertEqual(
            response.context["columnas_seleccionadas"],
            ["proveedor", "identificacion", "ubicacion", "estado", "activos"],
        )
        self.assertContains(response, "Vista de tabla")
        self.assertContains(response, "TE")
        self.assertContains(response, "border-cyan-200")
        self.assertNotContains(response, "{% cycle")
        self.assertNotContains(response, "{{ proveedor.pais")

        response = self.client.get(
            reverse("proveedores:lista"),
            {"cols": ["proveedor", "contacto", "telefono"]},
        )
        self.assertEqual(
            response.context["columnas_seleccionadas"],
            ["proveedor", "contacto", "telefono"],
        )
        self.assertContains(response, "Ana Torres")

    def test_restringe_usuario_sin_permisos(self):
        otro = get_user_model().objects.create_user("sinpermiso", password="testpass123")
        self.client.force_login(otro)
        self.assertEqual(self.client.get(reverse("proveedores:lista")).status_code, 403)


class ProveedorActivoTests(TestCase):
    def setUp(self):
        self.tipo = TipoActivo.objects.create(nombre="Laptop")
        self.estado = EstadoActivo.objects.create(nombre="Disponible", permite_asignacion=True)
        self.empresa = Empresa.objects.create(nombre="ILSA")
        self.activo_proveedor = Proveedor.objects.create(**datos_proveedor())
        self.inactivo = Proveedor.objects.create(**datos_proveedor(
            identificacion="EXT-999", tipo_identificacion="extranjera", pais="Peru",
            razon_social="Proveedor historico", nombre_comercial="", activo=False,
        ))

    def datos_activo(self, **cambios):
        datos = {
            "tipo_activo": self.tipo.pk, "empresa": self.empresa.pk,
            "marca": "Dell", "modelo": "Latitude", "serie": "SER-1",
            "codigo_sap": "SAP-1", "cpu": "i5", "ram": "16 GB", "disco": "512 GB",
            "sistema_operativo": "Windows", "fecha_compra": "2026-01-01", "valor": "1000",
            "estado_activo": self.estado.pk, "activo": "on", "observaciones": "",
        }
        datos.update(cambios)
        return datos

    def test_asocia_proveedor_y_permite_activo_sin_proveedor(self):
        form = ActivoAdminForm(data=self.datos_activo(proveedor=self.activo_proveedor.pk))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().proveedor, self.activo_proveedor)
        form = ActivoAdminForm(data=self.datos_activo(serie="SER-2", codigo_sap="SAP-2", proveedor=""))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().proveedor)

    def test_excluye_inactivo_en_alta_y_conserva_historico_en_edicion(self):
        alta = ActivoAdminForm()
        self.assertNotIn(self.inactivo, alta.fields["proveedor"].queryset)
        activo = Activo.objects.create(
            tipo_activo=self.tipo, empresa=self.empresa, proveedor=self.inactivo,
            marca="Dell", modelo="Latitude", serie="HIST-1", codigo_sap="HIST-1",
            estado_activo=self.estado,
        )
        edicion = ActivoAdminForm(instance=activo)
        self.assertIn(self.inactivo, edicion.fields["proveedor"].queryset)

    def test_protege_eliminacion_con_activos(self):
        Activo.objects.create(
            tipo_activo=self.tipo, empresa=self.empresa, proveedor=self.activo_proveedor,
            marca="Dell", modelo="Latitude", serie="PROT-1", codigo_sap="PROT-1",
            estado_activo=self.estado,
        )
        with self.assertRaises(ProtectedError):
            self.activo_proveedor.delete()
