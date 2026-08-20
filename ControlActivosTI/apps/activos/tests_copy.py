from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalogos.models import (
    AtributoActivo,
    EstadoActivo,
    TipoActivo,
    TipoActivoAtributo,
    UbicacionFisicaActivo,
)

from .attribute_services import guardar_valores_atributos
from .encryption import decrypt_protected_text
from .models import Activo, FotoActivo, ValorAtributoActivo


class ActivoCopyFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("copiador", password="testpass123")
        self.estado = EstadoActivo.objects.create(nombre="Disponible copia", permite_asignacion=True)
        self.tipo = TipoActivo.objects.create(nombre="Laptop copia")
        self.otro_tipo = TipoActivo.objects.create(nombre="Monitor copia")
        self.ubicacion_fisica = UbicacionFisicaActivo.objects.create(nombre="Logistica copia")
        self.ram = AtributoActivo.objects.create(
            nombre="RAM para copia",
            clave="ram_para_copia",
            tipo_dato=AtributoActivo.TipoDato.ENTERO,
            unidad="GB",
        )
        self.licencia = AtributoActivo.objects.create(
            nombre="Licencia para copia",
            clave="licencia_para_copia",
            tipo_dato=AtributoActivo.TipoDato.TEXTO_PROTEGIDO,
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo, atributo=self.ram, obligatorio=True, orden=1
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo, atributo=self.licencia, obligatorio=True, orden=2
        )
        self.base = Activo.objects.create(
            tipo_activo=self.tipo,
            marca="Dell",
            modelo="Latitude 5440",
            serie="BASE-COPIA-001",
            codigo_sap="SAP-BASE-COPIA",
            cpu="Intel Core i7",
            ram="32 GB",
            disco="1 TB SSD",
            sistema_operativo="Windows 11",
            estado_activo=self.estado,
            observaciones="Ficha que se reutilizara.",
        )
        guardar_valores_atributos(
            self.base,
            {"ram_para_copia": 32, "licencia_para_copia": "SECRETO-COPIABLE-1234"},
            usuario=self.user,
        )
        # La copia debe ignorar incluso una foto ya asociada al origen. Se usa
        # bulk_create para que la prueba no dependa del procesamiento de Pillow.
        FotoActivo.objects.bulk_create(
            [FotoActivo(activo=self.base, imagen="activos/base/foto.webp", orden=1)]
        )
        self.client.force_login(self.user)

    def _post_data(self):
        return {
            "activo_base_id": str(self.base.pk),
            # Intenta alterar el tipo: el backend debe conservar el del origen.
            "tipo_activo": str(self.otro_tipo.pk),
            "ubicacion_fisica": str(self.ubicacion_fisica.pk),
            "marca": "Dell",
            "modelo": "Latitude 5440",
            "serie": "COPIA-002",
            "codigo_sap": "SAP-COPIA-002",
            "cpu": "Intel Core i7",
            "ram": "32 GB",
            "disco": "1 TB SSD",
            "sistema_operativo": "Windows 11",
            "fecha_compra": "",
            "valor": "",
            "incluir_en_depreciacion": "on",
            "estado_activo": str(self.estado.pk),
            "observaciones": "Ficha que se reutilizara.",
            "atributo__ram_para_copia": "32",
            "atributo__licencia_para_copia": "",
            "fotos-TOTAL_FORMS": "2",
            "fotos-INITIAL_FORMS": "0",
            "fotos-MIN_NUM_FORMS": "0",
            "fotos-MAX_NUM_FORMS": "8",
        }

    def test_nuevo_primero_muestra_las_dos_formas_de_creacion(self):
        response = self.client.get(reverse("activos:nuevo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empezar desde 0")
        self.assertContains(response, "Basarse en uno ya creado")
        self.assertContains(response, reverse("activos:seleccionar-base"))

    def test_selector_reutiliza_busqueda_y_filtros_del_inventario(self):
        response = self.client.get(
            reverse("activos:seleccionar-base"),
            {"q": "Latitude", "tipo": self.tipo.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.base.codigo)
        self.assertContains(response, f"?basado_en={self.base.pk}")
        self.assertContains(response, "data-asset-filters", html=False)
        self.assertContains(response, "data-filter-popover", html=False)
        self.assertContains(response, 'data-filter-tab="estado"', html=False)
        self.assertContains(response, "data-live-filter-summary", html=False)
        self.assertEqual(list(response.context["activos"]), [self.base])

    def test_formulario_precarga_datos_bloquea_tipo_y_no_precarga_fotos(self):
        response = self.client.get(reverse("activos:nuevo"), {"basado_en": self.base.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nuevo activo basado en otro")
        self.assertContains(response, "Latitude 5440")
        self.assertTrue(response.context["form"].fields["tipo_activo"].disabled)
        self.assertContains(response, 'name="atributo__ram_para_copia" value="32"', html=False)
        self.assertNotContains(response, "foto.webp")
        self.assertEqual(response.context["formset"].initial_form_count(), 0)

    def test_copia_crea_otro_activo_con_tipo_inmutable_atributos_y_sin_fotos(self):
        response = self.client.post(
            f"{reverse('activos:nuevo')}?basado_en={self.base.pk}",
            self._post_data(),
        )

        self.assertEqual(response.status_code, 302)
        copia = Activo.objects.get(serie="COPIA-002")
        self.assertNotEqual(copia.pk, self.base.pk)
        self.assertEqual(copia.tipo_activo, self.tipo)
        self.assertEqual(copia.marca, self.base.marca)
        self.assertEqual(copia.modelo, self.base.modelo)
        self.assertEqual(copia.fotos.count(), 0)
        self.assertEqual(
            copia.valores_atributos.get(atributo=self.ram).valor_entero,
            32,
        )
        secreto = ValorAtributoActivo.objects.get(activo=copia, atributo=self.licencia)
        self.assertEqual(decrypt_protected_text(secreto.valor_texto), "SECRETO-COPIABLE-1234")
