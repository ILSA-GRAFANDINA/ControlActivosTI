from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.catalogos.models import (
    AtributoActivo,
    EstadoActivo,
    OpcionAtributoActivo,
    TipoActivo,
    TipoActivoAtributo,
    UbicacionFisicaActivo,
)

from .attribute_services import guardar_valores_atributos
from .encryption import decrypt_protected_text
from .forms import ActivoAdminForm
from .models import Activo, ValorAtributoActivo


class AtributosConfigurablesModelTests(TestCase):
    def setUp(self):
        self.tipo = TipoActivo.objects.create(nombre="Laptop configurable")
        self.estado = EstadoActivo.objects.create(nombre="Disponible atributos", permite_asignacion=True)
        self.ram, _ = AtributoActivo.objects.update_or_create(
            clave="memoria_ram",
            defaults={
                "nombre": "Memoria RAM",
                "tipo_dato": AtributoActivo.TipoDato.ENTERO,
                "unidad": "GB",
                "activo": True,
            },
        )
        self.config = TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo,
            atributo=self.ram,
            obligatorio=True,
            orden=1,
            valor_minimo=4,
            valor_maximo=256,
            mostrar_actas=True,
        )
        self.activo = Activo.objects.create(
            tipo_activo=self.tipo,
            marca="Dell",
            modelo="Latitude",
            serie="ATTR-001",
            estado_activo=self.estado,
        )

    def test_guarda_valor_tipado_unico_y_sin_unidad_embebida(self):
        guardar_valores_atributos(self.activo, {"memoria_ram": 16})
        valor = ValorAtributoActivo.objects.get(activo=self.activo, atributo=self.ram)
        self.assertEqual(valor.valor_entero, 16)
        self.assertEqual(valor.valor_formateado, "16 GB")
        self.activo.refresh_from_db()
        self.assertEqual(self.activo.ram, "16 GB")
        with self.assertRaisesMessage(ValidationError, "sin la unidad GB"):
            guardar_valores_atributos(self.activo, {"memoria_ram": "32 GB"})

    def test_rechaza_valor_fuera_de_rango_y_atributo_ajeno(self):
        with self.assertRaises(ValidationError):
            guardar_valores_atributos(self.activo, {"memoria_ram": 2})
        with self.assertRaises(ValidationError):
            guardar_valores_atributos(self.activo, {"direccion_ip": "10.0.0.1"})

    def test_no_permite_cambiar_tipo_de_dato_ni_eliminar_atributo_usado(self):
        guardar_valores_atributos(self.activo, {"memoria_ram": 16})
        self.ram.tipo_dato = AtributoActivo.TipoDato.FECHA
        with self.assertRaises(ValidationError):
            self.ram.save()
        self.ram.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.ram.delete()

    def test_lista_solo_acepta_opciones_del_mismo_atributo(self):
        panel = AtributoActivo.objects.create(
            nombre="Panel", clave="tipo_panel", tipo_dato=AtributoActivo.TipoDato.LISTA
        )
        opcion = OpcionAtributoActivo.objects.create(
            atributo=panel, clave="ips", nombre="IPS", orden=1
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo, atributo=panel, orden=2
        )
        guardar_valores_atributos(
            self.activo, {"memoria_ram": 16, "tipo_panel": opcion}
        )
        self.assertEqual(
            ValorAtributoActivo.objects.get(activo=self.activo, atributo=panel).valor_opcion,
            opcion,
        )

    def test_guarda_fecha_como_valor_tipado(self):
        vencimiento = AtributoActivo.objects.create(
            nombre="Vencimiento garantia",
            clave="vencimiento_garantia",
            tipo_dato=AtributoActivo.TipoDato.FECHA,
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo,
            atributo=vencimiento,
            orden=2,
        )

        guardar_valores_atributos(
            self.activo,
            {"memoria_ram": 16, "vencimiento_garantia": date(2027, 5, 12)},
        )

        valor = ValorAtributoActivo.objects.get(activo=self.activo, atributo=vencimiento)
        self.assertEqual(valor.valor_fecha, date(2027, 5, 12))
        self.assertEqual(valor.valor_formateado, "12/05/2027")

    def test_texto_protegido_se_cifra_y_se_muestra_enmascarado(self):
        licencia = AtributoActivo.objects.create(
            nombre="Codigo de licencia",
            clave="codigo_licencia",
            tipo_dato=AtributoActivo.TipoDato.TEXTO_PROTEGIDO,
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo,
            atributo=licencia,
            orden=2,
            mostrar_actas=True,
        )

        guardar_valores_atributos(
            self.activo,
            {"memoria_ram": 16, "codigo_licencia": "ABCD-1234-WXYZ-7890"},
        )

        valor = ValorAtributoActivo.objects.get(activo=self.activo, atributo=licencia)
        self.assertNotIn("ABCD-1234-WXYZ-7890", valor.valor_texto)
        self.assertEqual(decrypt_protected_text(valor.valor_texto), "ABCD-1234-WXYZ-7890")
        self.assertEqual(valor.valor_formateado, "ABCD****7890")

    @override_settings(MAX_ATRIBUTOS_ACTIVOS_POR_TIPO=1)
    def test_limite_de_atributos_es_configurable(self):
        segundo = AtributoActivo.objects.create(
            nombre="Procesador limite", clave="procesador_limite",
            tipo_dato=AtributoActivo.TipoDato.TEXTO_CORTO,
        )
        with self.assertRaises(ValidationError):
            TipoActivoAtributo.objects.create(
                tipo_activo=self.tipo, atributo=segundo, orden=2
            )


class ActivoDynamicFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("atributos-user", password="x")
        self.tipo = TipoActivo.objects.create(nombre="Monitor dinamico")
        self.estado = EstadoActivo.objects.create(nombre="Disponible dinamico", permite_asignacion=True)
        self.ubicacion_fisica = UbicacionFisicaActivo.objects.create(nombre="Produccion")
        self.tamano = AtributoActivo.objects.create(
            nombre="Tamano de pantalla", clave="tamano_pantalla",
            tipo_dato=AtributoActivo.TipoDato.DECIMAL, unidad="pulgadas",
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo, atributo=self.tamano, obligatorio=True,
            orden=1, valor_minimo=10, valor_maximo=100,
        )

    def data(self, valor="24"):
        return {
            "tipo_activo": self.tipo.pk,
            "ubicacion_fisica": self.ubicacion_fisica.pk,
            "marca": "LG",
            "modelo": "Ultra",
            "serie": "MON-DYN-1",
            "codigo_sap": "",
            "fecha_compra": "",
            "valor": "",
            "estado_activo": self.estado.pk,
            "observaciones": "",
            "atributo__tamano_pantalla": valor,
        }

    def test_formulario_crea_campo_por_clave_y_valida_en_backend(self):
        form = ActivoAdminForm(data=self.data(), usuario=self.user, permitir_cambio_vigencia=False)
        self.assertIn("atributo__tamano_pantalla", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        activo = form.save()
        guardar_valores_atributos(activo, form.valores_atributos_limpios(), usuario=self.user)
        self.assertEqual(activo.valores_atributos.get().valor_formateado, "24 pulgadas")
        self.assertTrue(RegistroAuditoria.objects.filter(objeto_id=str(activo.pk)).exists())

    def test_formulario_conserva_error_junto_al_atributo(self):
        form = ActivoAdminForm(data=self.data("5"), usuario=self.user, permitir_cambio_vigencia=False)
        self.assertFalse(form.is_valid())
        self.assertIn("atributo__tamano_pantalla", form.errors)

    def test_formulario_no_renderiza_ni_borra_texto_protegido_existente(self):
        licencia = AtributoActivo.objects.create(
            nombre="Codigo de licencia dinamico",
            clave="codigo_licencia_dinamico",
            tipo_dato=AtributoActivo.TipoDato.TEXTO_PROTEGIDO,
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=self.tipo,
            atributo=licencia,
            obligatorio=True,
            orden=2,
        )
        activo = Activo.objects.create(
            tipo_activo=self.tipo,
            marca="LG",
            modelo="Ultra",
            serie="MON-DYN-SECRET",
            estado_activo=self.estado,
        )
        guardar_valores_atributos(
            activo,
            {"tamano_pantalla": "24", "codigo_licencia_dinamico": "LIC-1111-2222-XYZ"},
            usuario=self.user,
        )
        valor_original = activo.valores_atributos.get(atributo=licencia).valor_texto

        form = ActivoAdminForm(
            data={**self.data("24"), "atributo__codigo_licencia_dinamico": ""},
            instance=activo,
            usuario=self.user,
            permitir_cambio_vigencia=False,
        )

        self.assertFalse(form.fields["atributo__codigo_licencia_dinamico"].required)
        self.assertTrue(form.is_valid(), form.errors)
        guardar_valores_atributos(activo, form.valores_atributos_limpios(), usuario=self.user)
        self.assertEqual(
            activo.valores_atributos.get(atributo=licencia).valor_texto,
            valor_original,
        )

    def test_modulo_de_caracteristicas_queda_entre_paneles_y_fotos(self):
        activo = Activo.objects.create(
            tipo_activo=self.tipo,
            marca="LG",
            modelo="Ultra QA",
            serie="MON-DETALLE-DYN-1",
            estado_activo=self.estado,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("activos:detalle", args=[activo.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Características específicas")
        self.assertContains(response, "Tamano de pantalla")
        self.assertContains(response, "Sin registrar")
        contenido = response.content.decode()
        self.assertLess(contenido.index("Asignación actual"), contenido.index("caracteristicas-titulo"))
        self.assertLess(contenido.index("caracteristicas-titulo"), contenido.index("Fotos del activo"))

        guardar_valores_atributos(activo, {"tamano_pantalla": "24"}, usuario=self.user)
        response = self.client.get(reverse("activos:detalle", args=[activo.pk]))
        self.assertContains(response, "24 pulgadas")

    def test_detalle_no_muestra_campos_legacy_no_vinculados_al_tipo(self):
        tipo_sin_atributos = TipoActivo.objects.create(nombre="Monitor sin CPU vinculado")
        activo = Activo.objects.create(
            tipo_activo=tipo_sin_atributos,
            marca="LG",
            modelo="Solo monitor",
            serie="MON-SIN-CPU-1",
            estado_activo=self.estado,
        )
        Activo.objects.filter(pk=activo.pk).update(cpu="CPU LEGACY NO VINCULADO")
        self.client.force_login(self.user)

        response = self.client.get(reverse("activos:detalle", args=[activo.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["atributos_configurables"], [])
        self.assertNotContains(response, "CPU LEGACY NO VINCULADO")
        self.assertContains(response, "caracteristicas-titulo")
        self.assertContains(
            response,
            "Este tipo de activo no tiene características configuradas para mostrar en el detalle.",
        )

class LegacyAttributeMigrationCommandTests(TestCase):
    def test_dry_run_es_repetible_y_no_escribe(self):
        tipo = TipoActivo.objects.create(nombre="Laptop comando")
        estado = EstadoActivo.objects.create(nombre="Disponible comando")
        definiciones = (
            ("procesador", AtributoActivo.TipoDato.TEXTO_CORTO, ""),
            ("memoria_ram", AtributoActivo.TipoDato.ENTERO, "GB"),
            ("almacenamiento", AtributoActivo.TipoDato.TEXTO_CORTO, ""),
            ("sistema_operativo", AtributoActivo.TipoDato.TEXTO_CORTO, ""),
        )
        for orden, (clave, tipo_dato, unidad) in enumerate(definiciones, 1):
            atributo, _ = AtributoActivo.objects.update_or_create(
                clave=clave,
                defaults={"nombre": clave, "tipo_dato": tipo_dato, "unidad": unidad, "activo": True},
            )
            TipoActivoAtributo.objects.create(
                tipo_activo=tipo, atributo=atributo, orden=orden
            )
        Activo.objects.create(
            tipo_activo=tipo, estado_activo=estado, marca="Dell", modelo="X",
            serie="CMD-1", cpu="Intel i7", ram="16 GB", disco="512 GB SSD",
            sistema_operativo="Windows 11",
        )
        salida = StringIO()
        call_command("migrate_legacy_asset_attributes", "--dry-run", stdout=salida)
        self.assertIn("SIMULACION", salida.getvalue())
        self.assertEqual(ValorAtributoActivo.objects.count(), 0)

    def test_migra_ram_con_generacion_ddr_sin_marcar_revision(self):
        tipo = TipoActivo.objects.create(nombre="Laptop RAM DDR")
        estado = EstadoActivo.objects.create(nombre="Disponible RAM DDR")
        atributo, _ = AtributoActivo.objects.update_or_create(
            clave="memoria_ram",
            defaults={
                "nombre": "Memoria RAM",
                "tipo_dato": AtributoActivo.TipoDato.ENTERO,
                "unidad": "GB",
                "activo": True,
            },
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=tipo,
            atributo=atributo,
            orden=1,
        )
        almacenamiento = AtributoActivo.objects.get(clave="almacenamiento")
        almacenamiento.unidad = "GB"
        almacenamiento.save()
        TipoActivoAtributo.objects.create(
            tipo_activo=tipo,
            atributo=almacenamiento,
            orden=2,
        )
        activo = Activo.objects.create(
            tipo_activo=tipo,
            estado_activo=estado,
            marca="Dell",
            modelo="DDR",
            serie="DDR-1",
            ram="24 DDR5",
            disco="1 TB SSD",
        )

        call_command("migrate_legacy_asset_attributes")

        valor = ValorAtributoActivo.objects.get(activo=activo, atributo=atributo)
        self.assertEqual(valor.valor_entero, 24)
        self.assertFalse(valor.requiere_revision)
        self.assertEqual(
            ValorAtributoActivo.objects.get(
                activo=activo,
                atributo=almacenamiento,
            ).valor_formateado,
            "1 TB SSD",
        )
