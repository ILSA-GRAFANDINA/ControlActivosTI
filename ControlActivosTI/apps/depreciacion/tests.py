from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.activos.models import Activo
from apps.catalogos.models import EstadoActivo, TipoActivo
from apps.notificaciones.models import Notificacion

from apps.depreciacion.models import (
    ConfiguracionAlertasDepreciacion,
    EventoNotificacionDepreciacion,
)
from apps.depreciacion.services import (
    DepreciationNotificationService,
    DepreciationService,
)

User = get_user_model()


class DepreciacionAutomaticaTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="secret"
        )
        self.tipo = TipoActivo.objects.create(nombre="Laptop")
        self.operativo = EstadoActivo.objects.create(
            nombre="Disponible", permite_asignacion=True
        )
        self.baja = EstadoActivo.objects.create(
            nombre="Dado de baja", permite_asignacion=False
        )

    def activo(self, **kwargs):
        data = {
            "tipo_activo": self.tipo,
            "marca": "Dell",
            "modelo": "Latitude",
            "serie": f"SER-{Activo.objects.count()}",
            "fecha_compra": date(2024, 1, 31),
            "valor": Decimal("1200.00"),
            "estado_activo": self.operativo,
        }
        data.update(kwargs)
        return Activo.objects.create(**data)

    def test_calcula_automaticamente_desde_activo(self):
        activo = self.activo()
        resultado = DepreciationService.calcular(activo, date(2025, 1, 31))
        self.assertTrue(resultado.configurado)
        self.assertEqual(resultado.costo_adquisicion, activo.valor)
        self.assertEqual(resultado.fecha_inicio, activo.fecha_compra)
        self.assertEqual(resultado.fecha_fin, date(2027, 1, 31))

    def test_no_crea_ficha_manual_de_depreciacion(self):
        activo = self.activo()
        self.assertFalse(hasattr(activo, "depreciacion"))
        self.assertEqual(DepreciationService.calcular(activo).valor_residual, 0)

    def test_fecha_final_usa_meses_calendario(self):
        activo = self.activo(fecha_compra=date(2024, 2, 29))
        self.assertEqual(
            DepreciationService.calcular(activo).fecha_fin, date(2027, 2, 28)
        )

    def test_antes_de_fecha_compra_es_cero(self):
        resultado = DepreciationService.calcular(self.activo(), date(2023, 1, 1))
        self.assertEqual(resultado.porcentaje_depreciado, 0)
        self.assertEqual(resultado.estado, "No iniciada")

    def test_en_fecha_final_es_cien(self):
        resultado = DepreciationService.calcular(self.activo(), date(2027, 1, 31))
        self.assertEqual(resultado.porcentaje_depreciado, 100)
        self.assertEqual(resultado.valor_contable_estimado, 0)

    def test_despues_de_fecha_final_no_supera_cien(self):
        resultado = DepreciationService.calcular(self.activo(), date(2040, 1, 1))
        self.assertEqual(resultado.porcentaje_depreciado, 100)
        self.assertEqual(resultado.depreciacion_acumulada, Decimal("1200.00"))

    def test_sin_valor_queda_pendiente(self):
        resultado = DepreciationService.calcular(self.activo(valor=None))
        self.assertFalse(resultado.configurado)
        self.assertEqual(resultado.estado, "Pendiente de configuración")

    def test_sin_fecha_queda_pendiente(self):
        resultado = DepreciationService.calcular(self.activo(fecha_compra=None))
        self.assertFalse(resultado.configurado)

    def test_detalle_muestra_depreciacion_sin_configuracion_manual(self):
        activo = self.activo()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("activos:detalle", args=[activo.pk]))
        self.assertContains(response, "Cálculo automático")
        self.assertContains(response, "36 meses")
        self.assertNotContains(response, "Valor residual")
        self.assertNotContains(response, "Registrar ajuste")

    def test_configuracion_global_tiene_valores_predeterminados(self):
        configuracion = ConfiguracionAlertasDepreciacion.obtener()
        self.assertEqual(configuracion.alerta_previa_meses, 3)
        self.assertEqual(configuracion.frecuencia_recordatorio_meses, 6)
        self.assertFalse(configuracion.mostrar_valor_residual)

    def test_admin_puede_cambiar_alertas_y_mostrar_valor_residual(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("depreciacion:configurar-alertas"),
            {
                "alerta_previa_meses": 2,
                "frecuencia_recordatorio_meses": 4,
                "mostrar_valor_residual": "on",
            },
        )
        self.assertRedirects(response, reverse("depreciacion:configurar-alertas"))
        configuracion = ConfiguracionAlertasDepreciacion.objects.get(pk=1)
        self.assertEqual(configuracion.alerta_previa_meses, 2)
        self.assertEqual(configuracion.frecuencia_recordatorio_meses, 4)
        self.assertTrue(configuracion.mostrar_valor_residual)

        activo = self.activo()
        detalle = self.client.get(reverse("activos:detalle", args=[activo.pk]))
        self.assertContains(detalle, "Valor residual")

    def test_alerta_respeta_configuracion_global(self):
        ConfiguracionAlertasDepreciacion.objects.create(
            alerta_previa_meses=2, frecuencia_recordatorio_meses=6
        )
        activo = self.activo(fecha_compra=date(2024, 1, 15))
        eventos = DepreciationService.eventos_vencidos(activo, date(2026, 11, 15))
        self.assertIn(
            (EventoNotificacionDepreciacion.Tipo.ALERTA, date(2026, 11, 15)),
            eventos,
        )

    def test_notificaciones_son_idempotentes(self):
        activo = self.activo()
        fecha = date(2027, 1, 31)
        for _ in range(2):
            DepreciationNotificationService.procesar(
                activo, EventoNotificacionDepreciacion.Tipo.CUMPLIMIENTO, fecha
            )
        self.assertEqual(EventoNotificacionDepreciacion.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_comando_dry_run_no_escribe(self):
        self.activo()
        call_command(
            "check_asset_depreciation",
            evaluation_date="2027-01-31",
            dry_run=True,
            stdout=StringIO(),
        )
        self.assertFalse(EventoNotificacionDepreciacion.objects.exists())

    def test_comando_repetido_no_duplica(self):
        self.activo()
        for _ in range(2):
            call_command(
                "check_asset_depreciation",
                evaluation_date="2027-01-31",
                stdout=StringIO(),
            )
        self.assertEqual(
            EventoNotificacionDepreciacion.objects.filter(omitido=False).count(), 1
        )
        self.assertEqual(Notificacion.objects.count(), 1)

    def test_activo_dado_de_baja_no_notifica(self):
        self.activo(estado_activo=self.baja)
        call_command(
            "check_asset_depreciation",
            evaluation_date="2028-01-31",
            stdout=StringIO(),
        )
        self.assertFalse(EventoNotificacionDepreciacion.objects.exists())

    def test_reporte_incluye_activos_historicos_con_datos(self):
        activo = self.activo(fecha_compra=date(2020, 1, 1))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("depreciacion:reporte"))
        self.assertContains(response, activo.codigo)
        self.assertContains(response, "Vida útil cumplida")

    def test_filtro_estado_se_aplica_antes_de_paginar(self):
        proximo = self.activo(fecha_compra=date(2024, 1, 1))
        for numero in range(30):
            self.activo(
                fecha_compra=date(2025, 1, 1),
                serie=f"NO-PROXIMO-{numero}",
            )

        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("depreciacion:reporte"),
            {
                "estado": "Próximo a cumplir vida útil",
                "fecha": "2026-11-01",
            },
        )

        self.assertEqual(response.context["paginator"].count, 1)
        self.assertEqual(response.context["paginator"].num_pages, 1)
        self.assertContains(response, proximo.codigo)
