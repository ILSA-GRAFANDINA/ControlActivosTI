from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalogos.models import Area, Cargo, CentroCosto, Empresa, Ubicacion

from apps.colaboradores.models import Colaborador


User = get_user_model()


class ColaboradorListViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rrhh", password="testpass123")
        self.area = Area.objects.create(nombre="TI")
        self.cargo = Cargo.objects.create(nombre="Soporte")
        self.ubicacion = Ubicacion.objects.create(nombre="Matriz")
        self.empresa_a = Empresa.objects.create(nombre="Andes Corp")
        self.empresa_b = Empresa.objects.create(nombre="Beta Tech")

        Colaborador.objects.create(
            nombres="Ana",
            apellidos="Zambrano",
            cedula="0102030405",
            correo_corporativo="ana@example.com",
            empresa=self.empresa_b,
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            fecha_ingreso=date(2024, 1, 10),
        )
        Colaborador.objects.create(
            nombres="Luis",
            apellidos="Alvarez",
            cedula="0203040506",
            correo_corporativo="luis@example.com",
            empresa=self.empresa_a,
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            fecha_ingreso=date(2024, 2, 15),
        )

    def _crear_colaborador_adicional(self, indice):
        return Colaborador.objects.create(
            nombres=f"Nombre{indice}",
            apellidos="Extra",
            cedula=f"9{indice:09d}",
            correo_corporativo=f"extra{indice}@example.com",
            empresa=self.empresa_a,
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            fecha_ingreso=date(2024, 3, 1),
        )

    def test_list_view_shows_company_separators(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("colaboradores:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Andes Corp")
        self.assertContains(response, "Beta Tech")
        self.assertContains(response, 'text-[11px] font-semibold uppercase')
        self.assertContains(response, "data-scroll-to-results")
        self.assertContains(response, 'id="resultados"')
        self.assertLess(
            response.content.decode().index("Andes Corp"),
            response.content.decode().index("Beta Tech"),
        )

    def test_table_colspan_matches_selected_columns_plus_fixed_columns(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("colaboradores:lista"), {"cols": ["nombre_completo"]})

        self.assertEqual(response.context["total_columnas_tabla"], 2)
        self.assertContains(response, 'colspan="2"')

    def test_list_view_uses_updated_default_columns(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("colaboradores:lista"))

        self.assertEqual(
            response.context["columnas_seleccionadas"],
            ["nombre_completo", "cedula", "empresa", "area", "cargo", "estado"],
        )
        self.assertContains(response, "Nombre completo")
        self.assertContains(response, "Ana Zambrano")
        self.assertContains(response, "Luis Alvarez")

    def test_list_view_shows_name_and_surname_initials(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("colaboradores:lista"),
            {"cols": ["nombre_completo"]},
        )

        self.assertContains(response, 'data-initials="AZ"')
        self.assertContains(response, 'data-initials="LA"')
        self.assertNotContains(response, ">Nombres</th>")
        self.assertNotContains(response, ">Apellidos</th>")

    def test_list_view_alternates_five_avatar_tones(self):
        self.client.force_login(self.user)
        for indice in range(3):
            self._crear_colaborador_adicional(indice)

        response = self.client.get(reverse("colaboradores:lista"))

        for tone in ("cyan", "emerald", "amber", "rose", "violet"):
            self.assertContains(response, f'data-avatar-tone="{tone}"', count=1)

    def test_avatar_and_surname_link_to_detail_without_action_column(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("colaboradores:lista"))
        colaborador = Colaborador.objects.get(cedula="0102030405")
        detail_url = reverse("colaboradores:detalle", args=[colaborador.pk])

        self.assertContains(response, f'href="{detail_url}"', count=2)
        self.assertNotContains(response, ">Acción</th>")
        self.assertNotContains(response, ">Ver detalle</a>")

    def test_list_view_paginates_at_ten_items(self):
        self.client.force_login(self.user)

        for indice in range(1, 10):
            self._crear_colaborador_adicional(indice)

        response = self.client.get(reverse("colaboradores:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(response.context["paginator"].per_page, 10)
        self.assertEqual(len(list(response.context["colaboradores"])), 10)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertTrue(response.context["page_obj"].has_next())
        self.assertContains(response, "Mostrando 1 a 10 de 11 colaboradores")
        self.assertEqual(response.context["query_string"], "")

        second_page = self.client.get(reverse("colaboradores:lista"), {"page": 2})

        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(list(second_page.context["colaboradores"])), 1)
        self.assertEqual(second_page.context["page_obj"].number, 2)
        self.assertFalse(second_page.context["page_obj"].has_next())
        self.assertContains(second_page, "Mostrando 11 a 11 de 11 colaboradores")
    
    def test_list_view_shows_add_colaborador_button(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("colaboradores:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("colaboradores:nuevo"))
        self.assertContains(response, "Agregar colaborador")


class ColaboradorCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rrhh-create", password="testpass123")
        self.area = Area.objects.create(nombre="TI")
        self.cargo = Cargo.objects.create(nombre="Soporte")
        self.ubicacion = Ubicacion.objects.create(nombre="Matriz")
        self.empresa = Empresa.objects.create(nombre="Andes Corp")

    def test_create_view_renders_form(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("colaboradores:nuevo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agregar colaborador")
        self.assertContains(response, "Guardar colaborador")

    def test_create_view_saves_colaborador(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("colaboradores:nuevo"),
            {
                "nombres": "Mariana",
                "apellidos": "Gomez",
                "cedula": "1234567890",
                "correo_corporativo": "mariana@example.com",
                "empresa": self.empresa.pk,
                "cargo": self.cargo.pk,
                "area": self.area.pk,
                "ubicacion": self.ubicacion.pk,
                "centro_costo": "",
                "estado": Colaborador.EstadoColaborador.ACTIVO,
                "fecha_ingreso": "2024-04-01",
                "observaciones": "Alta inicial",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Colaborador.objects.filter(cedula="1234567890").exists())


class ColaboradorDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rrhh-detail", password="testpass123")
        self.area = Area.objects.create(nombre="TI")
        self.cargo = Cargo.objects.create(nombre="Soporte")
        self.ubicacion = Ubicacion.objects.create(nombre="Matriz")
        self.empresa = Empresa.objects.create(nombre="Andes Corp")
        self.ceco = CentroCosto.objects.create(
            codigo="TI-001",
            nombre="Tecnologia",
            empresa=self.empresa,
        )
        self.colaborador = Colaborador.objects.create(
            nombres="Ana",
            apellidos="Zambrano",
            cedula="0102030405",
            correo_corporativo="ana@example.com",
            empresa=self.empresa,
            cargo=self.cargo,
            area=self.area,
            ubicacion=self.ubicacion,
            centro_costo=self.ceco,
            fecha_ingreso=date(2024, 1, 10),
        )

    def test_detail_view_exposes_admin_edit_button(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("colaboradores:detalle", args=[self.colaborador.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:colaboradores_colaborador_change", args=[self.colaborador.pk]),
        )
        self.assertContains(response, "Editar colaborador")
        self.assertContains(response, "Centro de costo")
        self.assertContains(response, "TI-001 - Tecnologia")
