from unittest.mock import Mock

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.http import urlencode

from apps.auditoria.models import RegistroAuditoria
from apps.catalogos.admin import (
    CentroCostoAdminForm,
    TipoActivoAtributoAdmin,
)
from apps.catalogos.models import (
    AtributoActivo,
    CentroCosto,
    DepartamentoEmpresa,
    Empresa,
    TipoActivo,
    TipoActivoAtributo,
)


class DepartamentoEmpresaTests(TestCase):
    def setUp(self):
        self.empresa_ilsa = Empresa.objects.create(nombre="ILSA")
        self.empresa_grafa = Empresa.objects.create(nombre="GRAFA")

    def test_allows_same_department_name_in_different_companies(self):
        dep_ilsa = DepartamentoEmpresa.objects.create(
            empresa=self.empresa_ilsa,
            nombre="Sistemas",
        )
        dep_grafa = DepartamentoEmpresa.objects.create(
            empresa=self.empresa_grafa,
            nombre="Sistemas",
        )

        self.assertEqual(str(dep_ilsa), "ILSA - Sistemas")
        self.assertEqual(str(dep_grafa), "GRAFA - Sistemas")

    def test_centrocosto_can_group_multiple_departments_from_same_company(self):
        sistemas = DepartamentoEmpresa.objects.create(
            empresa=self.empresa_ilsa,
            nombre="Sistemas",
        )
        administracion = DepartamentoEmpresa.objects.create(
            empresa=self.empresa_ilsa,
            nombre="Administracion",
        )
        ceco = CentroCosto.objects.create(
            codigo="230100001",
            nombre="Sistemas Compartido",
            empresa=self.empresa_ilsa,
        )

        ceco.departamentos.add(sistemas, administracion)

        self.assertEqual(ceco.departamentos_resumen, "Administracion, Sistemas")
        self.assertEqual(
            list(ceco.departamentos.order_by("nombre").values_list("nombre", flat=True)),
            ["Administracion", "Sistemas"],
        )


class CentroCostoAdminFormTests(TestCase):
    def setUp(self):
        self.empresa_ilsa = Empresa.objects.create(nombre="ILSA")
        self.empresa_grafa = Empresa.objects.create(nombre="GRAFA")
        self.dep_ilsa = DepartamentoEmpresa.objects.create(
            empresa=self.empresa_ilsa,
            nombre="Sistemas",
        )
        self.dep_grafa = DepartamentoEmpresa.objects.create(
            empresa=self.empresa_grafa,
            nombre="Administracion",
        )

    def test_only_shows_departments_from_selected_company(self):
        form = CentroCostoAdminForm(data={"empresa": self.empresa_ilsa.pk})

        departamentos = list(form.fields["departamentos"].queryset)

        self.assertIn(self.dep_ilsa, departamentos)
        self.assertNotIn(self.dep_grafa, departamentos)

    def test_rejects_departments_from_another_company(self):
        form = CentroCostoAdminForm(
            data={
                "codigo": "230100010",
                "nombre": "CECO Compartido",
                "empresa": self.empresa_ilsa.pk,
                "tipo": CentroCosto.TipoCentroCosto.OPERATIVO,
                "departamentos": [self.dep_grafa.pk],
                "acepta_asignaciones": True,
                "activo": True,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("departamentos", form.errors)

    def test_accepts_departments_from_the_same_company(self):
        form = CentroCostoAdminForm(
            data={
                "codigo": "230100011",
                "nombre": "CECO Compartido",
                "empresa": self.empresa_ilsa.pk,
                "tipo": CentroCosto.TipoCentroCosto.OPERATIVO,
                "departamentos": [self.dep_ilsa.pk],
                "acepta_asignaciones": True,
                "activo": True,
            }
        )

        self.assertTrue(form.is_valid())


class TipoActivoAtributoAdminTests(TestCase):
    def test_al_agregar_desde_filtro_preselecciona_tipo_activo(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin-tipo-inicial",
            email="tipo-inicial@example.com",
            password="prueba",
        )
        tipo = TipoActivo.objects.create(nombre="Licencia con tipo inicial")
        filtros = urlencode({"tipo_activo__id__exact": tipo.pk})
        request = RequestFactory().get(
            "/admin/catalogos/tipoactivoatributo/add/",
            {"_changelist_filters": filtros},
        )
        request.user = usuario
        model_admin = TipoActivoAtributoAdmin(TipoActivoAtributo, admin.site)

        initial = model_admin.get_changeform_initial_data(request)

        self.assertEqual(initial["tipo_activo"], str(tipo.pk))

    def test_nueva_asociacion_calcula_el_orden_siguiente(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin-orden-automatico",
            email="orden@example.com",
            password="prueba",
        )
        tipo = TipoActivo.objects.create(nombre="Licencia con orden automatico")
        primero = AtributoActivo.objects.create(
            nombre="Fabricante orden automatico",
            clave="fabricante_orden_automatico",
            tipo_dato=AtributoActivo.TipoDato.TEXTO_CORTO,
        )
        segundo = AtributoActivo.objects.create(
            nombre="Titular orden automatico",
            clave="titular_orden_automatico",
            tipo_dato=AtributoActivo.TipoDato.TEXTO_CORTO,
        )
        TipoActivoAtributo.objects.create(
            tipo_activo=tipo,
            atributo=primero,
            orden=1,
        )

        request = RequestFactory().get("/admin/catalogos/tipoactivoatributo/add/")
        request.user = usuario
        model_admin = TipoActivoAtributoAdmin(TipoActivoAtributo, admin.site)
        form_class = model_admin.get_form(request)
        form = form_class(
            data={
                "tipo_activo": tipo.pk,
                "atributo": segundo.pk,
                "mostrar_detalle": "on",
                "activo": "on",
                "validaciones": "{}",
            }
        )

        self.assertNotIn("orden", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.orden, 2)

        self.client.force_login(usuario)
        respuesta = self.client.get(
            reverse("admin:catalogos_tipoactivoatributo_add")
        )
        self.assertEqual(respuesta.status_code, 200)

    def test_quitar_del_tipo_desactiva_y_conserva_la_asociacion(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin-atributos",
            email="admin@example.com",
            password="prueba",
        )
        tipo = TipoActivo.objects.create(nombre="Monitor para desasociar")
        atributo = AtributoActivo.objects.create(
            nombre="Frecuencia para desasociar",
            clave="frecuencia_desasociar",
            tipo_dato=AtributoActivo.TipoDato.ENTERO,
            unidad="Hz",
        )
        configuracion = TipoActivoAtributo.objects.create(
            tipo_activo=tipo,
            atributo=atributo,
            orden=1,
        )
        request = RequestFactory().post("/admin/catalogos/tipoactivoatributo/")
        request.user = usuario
        model_admin = TipoActivoAtributoAdmin(TipoActivoAtributo, admin.site)
        model_admin.message_user = Mock()

        model_admin.quitar_del_tipo(
            request,
            TipoActivoAtributo.objects.filter(pk=configuracion.pk),
        )

        configuracion.refresh_from_db()
        self.assertFalse(configuracion.activo)
        self.assertTrue(AtributoActivo.objects.filter(pk=atributo.pk).exists())
        self.assertTrue(TipoActivoAtributo.objects.filter(pk=configuracion.pk).exists())
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                entidad="TipoActivoAtributo",
                objeto_id=str(configuracion.pk),
                accion=RegistroAuditoria.Accion.DESACTIVAR,
            ).exists()
        )
