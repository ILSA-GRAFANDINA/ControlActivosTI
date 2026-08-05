from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.forms import modelform_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import FormView, TemplateView

from apps.activos.models import Activo, EventoActivo
from apps.asignaciones.models import Asignacion, AsignacionDetalle
from apps.catalogos.models import (
    AtributoActivo,
    Area,
    Cargo,
    CentroCosto,
    DepartamentoEmpresa,
    Empresa,
    EstadoActivo,
    TipoActivo,
    TipoActivoAtributo,
    TipoEventoActivo,
    Ubicacion,
)
from apps.catalogos.forms import (
    AtributoActivoAdmin2Form,
    OpcionAtributoActivoAdmin2FormSet,
    TipoActivoAtributoAdmin2Form,
)
from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar_evento
from apps.colaboradores.models import Colaborador
from apps.notificaciones.models import Notificacion


User = get_user_model()
ASIGNACIONES_ABIERTAS = [
    Asignacion.EstadoAsignacion.ACTIVA,
    Asignacion.EstadoAsignacion.PARCIAL,
]


def get_admin_changelist_url(model):
    opts = model._meta
    return reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")


CATALOG_CONFIG = {
    "areas": {
        "model": Area,
        "title": "Áreas",
        "singular": "Área",
        "description": "Organizan colaboradores, reportes y segmentacion interna.",
        "fields": ["nombre", "descripcion", "activo"],
        "columns": ["nombre", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_area_changelist",
    },
    "cargos": {
        "model": Cargo,
        "title": "Cargos",
        "singular": "Cargo",
        "description": "Definen los puestos o roles asociados a cada colaborador.",
        "fields": ["nombre", "descripcion", "activo"],
        "columns": ["nombre", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_cargo_changelist",
    },
    "empresas": {
        "model": Empresa,
        "title": "Empresas",
        "singular": "Empresa",
        "description": "Permiten clasificar colaboradores y estructura empresarial.",
        "fields": ["nombre", "descripcion", "activo"],
        "columns": ["nombre", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_empresa_changelist",
    },
    "departamentos": {
        "model": DepartamentoEmpresa,
        "title": "Departamentos de empresa",
        "singular": "Departamento de empresa",
        "description": "Agrupan departamentos propios de cada empresa para vincularlos a un CECO compartido.",
        "fields": ["empresa", "nombre", "descripcion", "activo"],
        "columns": ["nombre", "empresa", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_departamentoempresa_changelist",
    },
    "ubicaciones": {
        "model": Ubicacion,
        "title": "Ubicaciones",
        "singular": "Ubicacion",
        "description": "Controlan sedes, oficinas o lugares fisicos relacionados.",
        "fields": ["nombre", "descripcion", "activo"],
        "columns": ["nombre", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_ubicacion_changelist",
    },
    "tipos-activo": {
        "model": TipoActivo,
        "title": "Tipos de activo",
        "singular": "Tipo de activo",
        "description": "Determinan la categoria general del equipo y su prefijo de codigo.",
        "fields": ["nombre", "descripcion", "activo"],
        "columns": ["nombre", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_tipoactivo_changelist",
    },
    "estados-activo": {
        "model": EstadoActivo,
        "title": "Estados de activo",
        "singular": "Estado de activo",
        "description": "Controlan la disponibilidad y el ciclo operativo de cada activo.",
        "fields": ["nombre", "descripcion", "permite_asignacion", "activo"],
        "columns": ["nombre", "permite_asignacion", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_estadoactivo_changelist",
    },
    "tipos-evento": {
        "model": TipoEventoActivo,
        "title": "Tipos de evento",
        "singular": "Tipo de evento",
        "description": "Clasifican eventos historicos o de seguimiento sobre activos.",
        "fields": ["nombre", "descripcion", "activo"],
        "columns": ["nombre", "activo", "updated_at"],
        "admin_changelist": "admin:catalogos_tipoeventoactivo_changelist",
    },
}


ADMIN2_MODULES = [
    {
        "slug": "usuarios",
        "title": "Usuarios",
        "description": "Gestiona accesos internos, cuentas administrativas y perfiles sensibles.",
        "icon_label": "US",
        "eyebrow": "Accesos",
    },
    {
        "slug": "catalogos",
        "title": "Configuración",
        "description": "Mantiene estados, tipos y tablas maestras que alimentan la operacion.",
        "icon_label": "CT",
        "eyebrow": "Configuracion",
    },
    {
        "slug": "seguridad",
        "title": "Seguridad",
        "description": "Revisa permisos, cuentas con privilegios y puntos de control interno.",
        "icon_label": "SG",
        "eyebrow": "Control",
    },
    {
        "slug": "reportes",
        "title": "Reportes",
        "description": "Resume tendencias de inventario, asignaciones y distribución por área.",
        "icon_label": "RP",
        "eyebrow": "Analitica",
    },
    {
        "slug": "inventario",
        "title": "Activos",
        "description": "Monitorea el parque de activos con foco en disponibilidad y estado actual.",
        "icon_label": "IN",
        "eyebrow": "Operacion",
    },
    {
        "slug": "auditoria",
        "title": "Auditoria",
        "description": "Concentra actividad reciente para seguimiento y trazabilidad operativa.",
        "icon_label": "AU",
        "eyebrow": "Seguimiento",
    },
]


class Admin2AccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_staff or user.is_superuser


class Admin2BaseContextMixin:
    page_title = "Admin2"
    page_subtitle = "Backoffice experimental"

    def get_module_cards(self):
        cards = []
        metrics = self.get_module_metrics()

        for module in ADMIN2_MODULES:
            item = module.copy()
            item["url"] = reverse(f"admin2-{module['slug']}")
            item.update(metrics.get(module["slug"], {}))
            cards.append(item)
        return cards

    def get_catalog_cards(self):
        cards = []
        for slug, config in CATALOG_CONFIG.items():
            model = config["model"]
            cards.append(
                {
                    "slug": slug,
                    "title": config["title"],
                    "description": config["description"],
                    "count": model.objects.count(),
                    "active_count": model.objects.filter(activo=True).count(),
                    "url": reverse("admin2-catalogo-lista", args=[slug]),
                    "admin_url": reverse(config["admin_changelist"]),
                }
            )
        return cards

    def get_module_metrics(self):
        activos_vigentes = Activo.objects.filter(activo=True)
        activos_disponibles = activos_vigentes.filter(
            estado_activo__permite_asignacion=True
        ).count()
        usuarios_staff = User.objects.filter(is_staff=True).count()
        eventos_recientes = EventoActivo.objects.count()

        return {
            "usuarios": {
                "metric_label": "Cuentas staff",
                "metric_value": usuarios_staff,
            },
            "catalogos": {
                "metric_label": "Tablas maestras activas",
                "metric_value": len(CATALOG_CONFIG),
            },
            "seguridad": {
                "metric_label": "Usuarios activos",
                "metric_value": User.objects.filter(is_active=True).count(),
            },
            "reportes": {
                "metric_label": "Asignaciones activas",
                "metric_value": Asignacion.objects.filter(
                    estado_asignacion__in=ASIGNACIONES_ABIERTAS
                ).count(),
            },
            "inventario": {
                "metric_label": "Activos disponibles",
                "metric_value": activos_disponibles,
            },
            "auditoria": {
                "metric_label": "Actividad registrada",
                "metric_value": eventos_recientes + Notificacion.objects.count(),
            },
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["admin2_modules"] = self.get_module_cards()
        context["admin2_page_title"] = self.page_title
        context["admin2_page_subtitle"] = self.page_subtitle
        context["admin2_sidebar_shortcuts"] = [
            {"label": "Inicio admin", "url": reverse("admin:index")},
            {"label": "Usuarios", "url": reverse("admin:auth_user_changelist")},
            {"label": "Activos", "url": get_admin_changelist_url(Activo)},
            {"label": "Asignaciones", "url": get_admin_changelist_url(Asignacion)},
            {"label": "Colaboradores", "url": get_admin_changelist_url(Colaborador)},
            {"label": "Notificaciones", "url": get_admin_changelist_url(Notificacion)},
            {"label": "Configuración", "url": reverse("admin:app_list", kwargs={"app_label": "catalogos"})},
        ]
        return context


class Admin2HomeView(Admin2AccessMixin, Admin2BaseContextMixin, TemplateView):
    template_name = "admin2/inicio.html"
    page_title = "Consola administrativa"
    page_subtitle = "Puerta de entrada guiada hacia Django Admin"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        modelos_registrados = len(admin.site._registry)
        usuarios_staff = User.objects.filter(is_staff=True).count()
        activos_registrados = Activo.objects.filter(activo=True).count()
        asignaciones_activas = Asignacion.objects.filter(
            estado_asignacion__in=ASIGNACIONES_ABIERTAS
        ).count()

        context["resumen"] = [
            {"label": "Entradas de admin", "value": modelos_registrados, "tone": "cyan"},
            {"label": "Usuarios staff", "value": usuarios_staff, "tone": "blue"},
            {"label": "Asignaciones activas", "value": asignaciones_activas, "tone": "emerald"},
            {"label": "Activos registrados", "value": activos_registrados, "tone": "amber"},
        ]
        context["admin2_sidebar_shortcuts"] = []
        context["accesos_rapidos"] = [
            {"label": "Inicio Django Admin", "url": reverse("admin:index")},
            {"label": "Usuarios", "url": reverse("admin:auth_user_changelist")},
            {"label": "Activos", "url": get_admin_changelist_url(Activo)},
            {"label": "Asignaciones", "url": get_admin_changelist_url(Asignacion)},
        ]

        context["admin_groups"] = [
            {
                "section_id": "accesos-seguridad",
                "title": "Accesos y permisos",
                "subtitle": "Administrar ingreso, privilegios o estructura de permisos.",
                "tone": "emerald",
                "items": [
                    {
                        "eyebrow": "Auth",
                        "title": "Usuarios",
                        "description": "Crea cuentas, activa o desactiva accesos.",
                        "url": reverse("admin:auth_user_changelist"),
                        "meta_label": "Registros",
                        "meta_value": User.objects.count(),
                    },
                    {
                        "eyebrow": "Auth",
                        "title": "Grupos",
                        "description": "Administra perfiles de permisos.",
                        "url": reverse("admin:auth_group_changelist"),
                        "meta_label": "Grupos",
                        "meta_value": Group.objects.count(),
                    },
                ],
            },
            {
                "section_id": "inventario-ti",
                "title": "Activos",
                "subtitle": "Revisar equipos, estados e inventario en general.",
                "tone": "slate",
                "items": [
                    {
                        "eyebrow": "Activos",
                        "title": "Activos",
                        "description": "Consulta o edita la ficha completa de cada equipo registrado.",
                        "url": get_admin_changelist_url(Activo),
                        "meta_label": "Total",
                        "meta_value": Activo.objects.filter(activo=True).count(),
                    },
                    {
                        "eyebrow": "Seguimiento",
                        "title": "Eventos de activos",
                        "description": "Revisa historial, novedades y movimientos asociados a los activos.",
                        "url": get_admin_changelist_url(EventoActivo),
                        "meta_label": "Eventos",
                        "meta_value": EventoActivo.objects.count(),
                    },
                ],
            },
            {
                "section_id": "colaboradores-entregas",
                "title": "Colaboradores",
                "subtitle": "Relacionar personas con equipos. Control de entregas.",
                "tone": "emerald",
                "items": [
                    {
                        "eyebrow": "Personas",
                        "title": "Colaboradores",
                        "description": "Actualiza información del personal.",
                        "url": get_admin_changelist_url(Colaborador),
                        "meta_label": "Colaboradores",
                        "meta_value": Colaborador.objects.count(),
                    },
                    {
                        "eyebrow": "Entrega",
                        "title": "Asignaciones",
                        "description": "Gestiona entregas, recepciones y estado administrativo de cada asignación.",
                        "url": get_admin_changelist_url(Asignacion),
                        "meta_label": "Activas",
                        "meta_value": asignaciones_activas,
                    },
                    {
                        "eyebrow": "Detalle",
                        "title": "Detalle de asignaciones",
                        "description": "Líneas internas de cada entrega.",
                        "url": get_admin_changelist_url(AsignacionDetalle),
                        "meta_label": "Lineas",
                        "meta_value": AsignacionDetalle.objects.count(),
                    },
                ],
            },
            {
                "section_id": "catalogos-estructura",
                "title": "Tablas maestras",
                "subtitle": "Mantener tablas maestras y configuraciones de atributos.",
                "tone": "slate",
                "items": [
                    {
                        "eyebrow": "Catálogos",
                        "title": "Áreas",
                        "description": "Clasifica las áreas internas para organizar colaboradores y reportes.",
                        "url": get_admin_changelist_url(Area),
                        "meta_label": "Registros",
                        "meta_value": Area.objects.count(),
                    },
                    {
                        "eyebrow": "Catálogos",
                        "title": "Cargos",
                        "description": "Mantiene los puestos o roles disponibles.",
                        "url": get_admin_changelist_url(Cargo),
                        "meta_label": "Registros",
                        "meta_value": Cargo.objects.count(),
                    },
                    {
                        "eyebrow": "Catálogos",
                        "title": "Empresas",
                        "description": "Agrega, edita o elimina empresas.",
                        "url": get_admin_changelist_url(Empresa),
                        "meta_label": "Registros",
                        "meta_value": Empresa.objects.count(),
                    },
                    {
                        "eyebrow": "Catálogos",
                        "title": "Ubicaciones",
                        "description": "Gestiona sedes, oficinas o puntos físicos.",
                        "url": get_admin_changelist_url(Ubicacion),
                        "meta_label": "Registros",
                        "meta_value": Ubicacion.objects.count(),
                    },
                    {
                        "eyebrow": "Catálogos",
                        "title": "Centros de costo",
                        "description": "Controla la estructura CECO para asignaciones y contabilidad.",
                        "url": get_admin_changelist_url(CentroCosto),
                        "meta_label": "Registros",
                        "meta_value": CentroCosto.objects.count(),
                    },
                    {
                        "eyebrow": "Catálogos",
                        "title": "Tipos de activo",
                        "description": "Define las categorías generales disponibles para registrar equipos.",
                        "url": get_admin_changelist_url(TipoActivo),
                        "meta_label": "Registros",
                        "meta_value": TipoActivo.objects.count(),
                    },
                    {
                        "eyebrow": "Catálogos",
                        "title": "Estados de activo",
                        "description": "Configura el estado operativo que determina disponibilidad.",
                        "url": get_admin_changelist_url(EstadoActivo),
                        "meta_label": "Registros",
                        "meta_value": EstadoActivo.objects.count(),
                    },
                    {
                        "eyebrow": "Catálogos",
                        "title": "Tipos de evento",
                        "description": "Mantiene las clases de eventos usadas para el seguimiento histórico.",
                        "url": get_admin_changelist_url(TipoEventoActivo),
                        "meta_label": "Registros",
                        "meta_value": TipoEventoActivo.objects.count(),
                    },
                ],
            },
        ]
        context["admin2_scroll_sections"] = [
            {"label": "Resumen", "url": "#admin2-resumen", "icon_label": "IN"},
            {"label": "Seguridad", "url": "#accesos-seguridad", "icon_label": "SG"},
            {"label": "Activos", "url": "#inventario-ti", "icon_label": "AC"},
            {"label": "Colaboradores", "url": "#colaboradores-entregas", "icon_label": "CO"},
            {"label": "Configuración", "url": "#catalogos-estructura", "icon_label": "CF"},
            {"label": "Administrador", "url": "#admin2-accesos-extra", "icon_label": "AD"},
        ]
        context["admin_support_links"] = [
            {
                "label": "Inicio Completo",
                "description": "Vista general con todas las apps registradas en Django Admin.",
                "url": reverse("admin:index"),
            },
            {
                "label": "App de catálogos",
                "description": "Entrada agrupada para áreas, cargos, empresas, departamentos, ubicaciones y CECO.",
                "url": reverse("admin:app_list", kwargs={"app_label": "catalogos"}),
            },
            {
                "label": "App de activos",
                "description": "Activos y Eventos de activos.",
                "url": reverse("admin:app_list", kwargs={"app_label": "activos"}),
            },
            {
                "label": "App de asignaciones",
                "description": "Asignaciones y sus líneas internas.",
                "url": reverse("admin:app_list", kwargs={"app_label": "asignaciones"}),
            },
        ]
        return context


class Admin2ModuleView(Admin2AccessMixin, Admin2BaseContextMixin, TemplateView):
    template_name = "admin2/modulo.html"
    module_slug = ""

    MODULE_DETAILS = {
        "usuarios": {
            "title": "Usuarios",
            "subtitle": "Accesos y perfiles internos",
            "description": "Vista para revisar quienes tienen acceso y apoyarte en Django Admin para permisos avanzados.",
        },
        "catalogos": {
            "title": "Configuración",
            "subtitle": "Tablas maestras del sistema",
            "description": "Panel para administrar catálogos desde /admin2 y dejar en Django Admin solo lo más técnico.",
        },
        "seguridad": {
            "title": "Seguridad",
            "subtitle": "Permisos y supervision interna",
            "description": "Espacio para vigilar cuentas privilegiadas y puntos que merecen revision periodica.",
        },
        "reportes": {
            "title": "Reportes",
            "subtitle": "Panorama ejecutivo del backoffice",
            "description": "Resumen de indicadores que ayudan a tomar decisiones sin salir a cada modulo operativo.",
        },
        "inventario": {
            "title": "Activos",
            "subtitle": "Control del parque de activos",
            "description": "Lectura administrativa del inventario con foco en estado, disponibilidad y ultimos ingresos.",
        },
        "auditoria": {
            "title": "Auditoria",
            "subtitle": "Actividad reciente y trazabilidad",
            "description": "Seguimiento de movimientos y eventos para detectar cambios importantes y mantener contexto operativo.",
        },
    }

    def get_module_data(self):
        return self.MODULE_DETAILS[self.module_slug]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = self.get_module_data()
        payload = self.get_module_payload()
        context["module"] = data
        context["admin2_page_title"] = data["title"]
        context["admin2_page_subtitle"] = data["subtitle"]
        context.update(payload)
        return context

    def get_module_payload(self):
        method = getattr(self, f"build_{self.module_slug}_payload")
        return method()

    def build_usuarios_payload(self):
        users = User.objects.order_by("-date_joined", "-id")[:8]
        rows = []
        for user in users:
            access_label = "Superusuario" if user.is_superuser else "Staff" if user.is_staff else "Basico"
            access_tone = "emerald" if user.is_superuser else "cyan" if user.is_staff else "slate"
            rows.append(
                {
                    "cells": [
                        {"value": user.get_username(), "subvalue": user.get_full_name() or "Sin nombre completo"},
                        {"value": user.email or "-", "subvalue": "Correo principal"},
                        {"value": access_label, "badge": True, "tone": access_tone},
                        {
                            "value": user.last_login.strftime("%d/%m/%Y %H:%M") if user.last_login else "Sin ingreso",
                            "subvalue": f"Alta: {user.date_joined.strftime('%d/%m/%Y')}",
                        },
                    ]
                }
            )

        return {
            "stats": [
                {"label": "Usuarios totales", "value": User.objects.count()},
                {"label": "Usuarios activos", "value": User.objects.filter(is_active=True).count()},
                {"label": "Cuentas staff", "value": User.objects.filter(is_staff=True).count()},
                {"label": "Superusuarios", "value": User.objects.filter(is_superuser=True).count()},
            ],
            "module_actions": [
                {"label": "Usuarios en Django Admin", "url": reverse("admin:auth_user_changelist"), "kind": "primary"},
                {"label": "Grupos y permisos", "url": reverse("admin:auth_group_changelist"), "kind": "secondary"},
            ],
            "table_title": "Ultimas cuentas registradas",
            "table_columns": ["Usuario", "Correo", "Acceso", "Ultimo ingreso"],
            "table_rows": rows,
            "table_empty_message": "Todavia no hay usuarios para mostrar.",
            "info_panels": [
                {
                    "title": "Como lo manejaremos aqui",
                    "items": [
                        {"label": "Consulta y supervision", "value": "Desde /admin2"},
                        {"label": "Permisos avanzados", "value": "Desde Django Admin"},
                        {"label": "Evitar duplicar complejidad", "value": "Decisiones mas mantenibles"},
                    ],
                }
            ],
        }

    def build_catalogos_payload(self):
        rows = []
        for item in self.get_catalog_cards():
            rows.append(
                {
                    "cells": [
                        {"value": item["title"], "url": item["url"], "subvalue": item["description"]},
                        {"value": item["count"]},
                        {"value": item["active_count"], "subvalue": "Registros activos"},
                        {"value": "Gestionar", "badge": True, "tone": "cyan", "url": item["url"]},
                    ]
                }
            )

        return {
            "stats": [
                {"label": "Catalogos", "value": len(CATALOG_CONFIG)},
                {"label": "Areas", "value": Area.objects.count()},
                {"label": "Estados", "value": EstadoActivo.objects.count()},
                {"label": "Tipos", "value": TipoActivo.objects.count()},
            ],
            "module_actions": [
                {"label": "Abrir catálogos", "url": reverse("admin2-catalogo-lista", args=["areas"]), "kind": "primary"},
                {"label": "Catalogos en Django Admin", "url": reverse("admin:catalogos_area_changelist"), "kind": "secondary"},
                {"label": "Atributos de activos", "url": reverse("admin2-atributos-lista"), "kind": "secondary"},
                {"label": "Configurar por tipo", "url": reverse("admin2-configuraciones-atributos-lista"), "kind": "secondary"},
            ],
            "table_title": "Catalogos disponibles",
            "table_columns": ["Catalogo", "Total", "Activos", "Accion"],
            "table_rows": rows,
            "table_empty_message": "No hay catálogos configurados.",
            "info_panels": [
                {
                    "title": "Catalogos administrables desde /admin2",
                    "items": [
                        {"label": item["title"], "value": item["count"], "url": item["url"]}
                        for item in self.get_catalog_cards()[:5]
                    ],
                }
            ],
        }

    def build_seguridad_payload(self):
        privileged_users = User.objects.filter(is_staff=True).order_by("username")
        rows = []
        for user in privileged_users[:8]:
            rows.append(
                {
                    "cells": [
                        {"value": user.username, "subvalue": user.email or "Sin correo"},
                        {
                            "value": "Superusuario" if user.is_superuser else "Staff",
                            "badge": True,
                            "tone": "emerald" if user.is_superuser else "amber",
                        },
                        {"value": "Activo" if user.is_active else "Inactivo", "badge": True, "tone": "cyan" if user.is_active else "rose"},
                        {"value": user.last_login.strftime("%d/%m/%Y %H:%M") if user.last_login else "Sin ingreso"},
                    ]
                }
            )

        return {
            "stats": [
                {"label": "Staff", "value": User.objects.filter(is_staff=True).count()},
                {"label": "Superusuarios", "value": User.objects.filter(is_superuser=True).count()},
                {"label": "Usuarios activos", "value": User.objects.filter(is_active=True).count()},
                {"label": "Asignaciones abiertas", "value": Asignacion.objects.filter(estado_asignacion__in=ASIGNACIONES_ABIERTAS).count()},
            ],
            "module_actions": [
                {"label": "Gestionar grupos", "url": reverse("admin:auth_group_changelist"), "kind": "primary"},
                {"label": "Ver usuarios", "url": reverse("admin:auth_user_changelist"), "kind": "secondary"},
            ],
            "table_title": "Cuentas con privilegios",
            "table_columns": ["Usuario", "Nivel", "Estado", "Ultimo acceso"],
            "table_rows": rows,
            "table_empty_message": "No hay cuentas staff para revisar.",
            "info_panels": [
                {
                    "title": "Puntos de control",
                    "items": [
                        {"label": "Revisa superusuarios", "value": "Solo los estrictamente necesarios"},
                        {"label": "Usa grupos", "value": "Permisos mas faciles de mantener"},
                        {"label": "Monitorea ultimo acceso", "value": "Detecta cuentas dormidas"},
                    ],
                }
            ],
        }

    def build_reportes_payload(self):
        activos_vigentes = Activo.objects.filter(activo=True)
        valor_total = activos_vigentes.aggregate(total=Sum("valor")).get("total") or 0
        activos_por_estado = (
            activos_vigentes.values("estado_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "estado_activo__nombre")[:6]
        )
        asignaciones_por_mes = (
            Asignacion.objects.annotate(mes=TruncMonth("fecha_asignacion"))
            .values("mes")
            .annotate(total=Count("id"))
            .order_by("-mes")[:6]
        )
        rows = []
        for item in activos_por_estado:
            rows.append(
                {
                    "cells": [
                        {"value": item["estado_activo__nombre"] or "Sin estado"},
                        {"value": item["total"]},
                        {
                            "value": "Disponible" if (item["estado_activo__nombre"] or "").lower() == "disponible" else "Seguimiento",
                            "badge": True,
                            "tone": "emerald" if (item["estado_activo__nombre"] or "").lower() == "disponible" else "slate",
                        },
                    ]
                }
            )

        month_panel_items = []
        for item in asignaciones_por_mes:
            if item["mes"]:
                month_panel_items.append({"label": item["mes"].strftime("%b %Y"), "value": item["total"]})

        areas = (
            Colaborador.objects.values("area__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "area__nombre")[:5]
        )

        return {
            "stats": [
                {"label": "Valor del inventario", "value": f"${valor_total}"},
                {"label": "Activos disponibles", "value": activos_vigentes.filter(estado_activo__permite_asignacion=True).count()},
                {"label": "Activos asignados", "value": activos_vigentes.filter(estado_activo__nombre__iexact="Asignado").count()},
                {"label": "Asignaciones totales", "value": Asignacion.objects.count()},
            ],
            "module_actions": [
                {"label": "Abrir dashboard", "url": reverse("dashboard-inicio"), "kind": "primary"},
                {"label": "Ir a asignaciones", "url": reverse("asignaciones:lista"), "kind": "secondary"},
            ],
            "table_title": "Activos por estado",
            "table_columns": ["Estado", "Total", "Lectura"],
            "table_rows": rows,
            "table_empty_message": "No hay datos de estado para mostrar.",
            "info_panels": [
                {"title": "Asignaciones por mes", "items": month_panel_items or [{"label": "Sin movimientos", "value": "-"}]},
                {
                    "title": "Colaboradores por área",
                    "items": [{"label": item["area__nombre"] or "Sin área", "value": item["total"]} for item in areas] or [{"label": "Sin datos", "value": "-"}],
                },
            ],
        }

    def build_inventario_payload(self):
        activos = (
            Activo.objects.filter(activo=True)
            .select_related("tipo_activo", "estado_activo")
            .order_by("-created_at", "-id")[:8]
        )
        rows = []
        for activo in activos:
            rows.append(
                {
                    "cells": [
                        {"value": activo.codigo, "url": reverse("activos:detalle", args=[activo.pk]), "subvalue": str(activo.tipo_activo)},
                        {"value": f"{activo.marca} {activo.modelo}".strip(), "subvalue": f"Serie: {activo.serie}"},
                        {
                            "value": activo.estado_activo.nombre,
                            "badge": True,
                            "tone": "orange"
                            if "operativo" in activo.estado_activo.nombre.lower() or "en uso" in activo.estado_activo.nombre.lower()
                            else "emerald"
                            if activo.estado_activo.permite_asignacion
                            else "cyan"
                            if activo.estado_activo.nombre.lower() == "asignado"
                            else "amber",
                        },
                        {"value": activo.created_at.strftime("%d/%m/%Y")},
                    ]
                }
            )

        estados = (
            Activo.objects.filter(activo=True).values("estado_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "estado_activo__nombre")[:5]
        )
        tipos = (
            Activo.objects.filter(activo=True).values("tipo_activo__nombre")
            .annotate(total=Count("id"))
            .order_by("-total", "tipo_activo__nombre")[:5]
        )

        return {
            "stats": [
                {"label": "Total activos", "value": Activo.objects.filter(activo=True).count()},
                {"label": "Disponibles", "value": Activo.objects.filter(activo=True, estado_activo__permite_asignacion=True).count()},
                {"label": "Con fotografia", "value": Activo.objects.filter(activo=True, fotos__isnull=False).distinct().count()},
                {"label": "Tipos registrados", "value": TipoActivo.objects.count()},
            ],
            "module_actions": [
                {"label": "Ver inventario completo", "url": reverse("activos:lista"), "kind": "primary"},
                {"label": "Depreciaciones de activos", "url": reverse("depreciacion:reporte"), "kind": "secondary"},
                {"label": "Configurar depreciación", "url": reverse("depreciacion:configurar-alertas"), "kind": "secondary"},
                {"label": "Crear asignación", "url": reverse("asignaciones:nueva"), "kind": "secondary"},
            ],
            "table_title": "Ultimos activos incorporados",
            "table_columns": ["Código", "Equipo", "Estado", "Alta"],
            "table_rows": rows,
            "table_empty_message": "No hay activos para mostrar.",
            "info_panels": [
                {
                    "title": "Inventario por estado",
                    "items": [{"label": item["estado_activo__nombre"] or "Sin estado", "value": item["total"]} for item in estados] or [{"label": "Sin datos", "value": "-"}],
                },
                {
                    "title": "Inventario por tipo",
                    "items": [{"label": item["tipo_activo__nombre"] or "Sin tipo", "value": item["total"]} for item in tipos] or [{"label": "Sin datos", "value": "-"}],
                },
            ],
        }

    def build_auditoria_payload(self):
        eventos = (
            EventoActivo.objects.select_related("activo", "tipo_evento", "usuario_responsable")
            .order_by("-fecha_evento", "-id")[:8]
        )
        rows = []
        for evento in eventos:
            rows.append(
                {
                    "cells": [
                        {"value": evento.activo.codigo, "url": reverse("activos:detalle", args=[evento.activo_id]), "subvalue": str(evento.tipo_evento)},
                        {"value": evento.detalle[:80] + ("..." if len(evento.detalle) > 80 else "")},
                        {"value": evento.usuario_responsable.get_username()},
                        {"value": evento.fecha_evento.strftime("%d/%m/%Y %H:%M")},
                    ]
                }
            )

        ultimas_asignaciones = Asignacion.objects.select_related("colaborador").order_by("-updated_at", "-id")[:5]

        registros_atributos = RegistroAuditoria.objects.select_related("usuario").order_by("-created_at", "-id")[:8]
        return {
            "stats": [
                {"label": "Eventos de activo", "value": EventoActivo.objects.count()},
                {"label": "Notificaciones", "value": Notificacion.objects.count()},
                {"label": "Asignaciones activas", "value": Asignacion.objects.filter(estado_asignacion__in=ASIGNACIONES_ABIERTAS).count()},
                {"label": "Pendientes", "value": Notificacion.objects.filter(read_at__isnull=True).count()},
                {"label": "Cambios de atributos", "value": RegistroAuditoria.objects.count()},
            ],
            "module_actions": [
                {"label": "Ver activos", "url": reverse("activos:lista"), "kind": "primary"},
                {"label": "Administrar notificaciones", "url": get_admin_changelist_url(Notificacion), "kind": "secondary"},
                {"label": "Auditoria de atributos", "url": reverse("admin:auditoria_registroauditoria_changelist"), "kind": "secondary"},
            ],
            "table_title": "Eventos recientes de activos",
            "table_columns": ["Activo", "Detalle", "Usuario", "Fecha"],
            "table_rows": rows,
            "table_empty_message": "No hay eventos registrados todavia.",
            "info_panels": [
                {
                    "title": "Ultimos cambios de atributos",
                    "items": [
                        {
                            "label": registro.resumen,
                            "value": registro.created_at.strftime("%d/%m/%Y %H:%M"),
                        }
                        for registro in registros_atributos
                    ] or [{"label": "Sin cambios registrados", "value": "-"}],
                },
                {
                    "title": "Ultimas asignaciones tocadas",
                    "items": [
                        {"label": item.codigo_asignacion or "Sin codigo", "value": item.colaborador.apellidos, "url": reverse("asignaciones:lista")}
                        for item in ultimas_asignaciones
                    ] or [{"label": "Sin movimientos", "value": "-"}],
                }
            ],
        }


class Admin2CatalogsContextMixin(Admin2AccessMixin, Admin2BaseContextMixin):
    catalog_slug = ""
    template_name = "admin2/catalogo_lista.html"

    def dispatch(self, request, *args, **kwargs):
        self.catalog_slug = kwargs["catalog_slug"]
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        if self.catalog_slug == "tipos-activo":
            return self.request.user.is_superuser or self.request.user.has_perm(
                "catalogos.manage_asset_attribute_schema"
            )
        return super().test_func()

    def get_catalog_config(self):
        try:
            return CATALOG_CONFIG[self.catalog_slug]
        except KeyError as exc:
            raise Http404("Catalogo no encontrado.") from exc

    def get_catalog_model(self):
        return self.get_catalog_config()["model"]

    def get_catalog_queryset(self):
        queryset = self.get_catalog_model().objects.all()
        query = self.request.GET.get("q", "").strip()
        estado = self.request.GET.get("estado", "").strip()

        if query:
            queryset = queryset.filter(nombre__icontains=query)
        if estado == "activos":
            queryset = queryset.filter(activo=True)
        elif estado == "inactivos":
            queryset = queryset.filter(activo=False)
        return queryset.order_by("nombre")

    def get_catalog_cards(self):
        cards = super().get_catalog_cards()
        for card in cards:
            card["is_active"] = card["slug"] == self.catalog_slug
        return cards

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.get_catalog_config()
        context["catalog"] = config
        context["catalog_slug"] = self.catalog_slug
        context["catalog_cards"] = self.get_catalog_cards()
        context["catalog_query"] = self.request.GET.get("q", "").strip()
        context["catalog_estado"] = self.request.GET.get("estado", "").strip()
        context["admin2_page_title"] = config["title"]
        context["admin2_page_subtitle"] = "Catalogos administrados desde /admin2"
        return context


class Admin2CatalogListView(Admin2CatalogsContextMixin, TemplateView):
    template_name = "admin2/catalogo_lista.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.get_catalog_config()
        objects = list(self.get_catalog_queryset())
        context["catalog_columns"] = config["columns"]
        context["catalog_has_assignation_column"] = "permite_asignacion" in config["columns"]
        context["catalog_objects"] = objects
        context["catalog_total"] = len(objects)
        context["catalog_active_total"] = sum(1 for item in objects if getattr(item, "activo", False))
        context["create_url"] = reverse("admin2-catalogo-crear", args=[self.catalog_slug])
        context["admin_catalog_url"] = reverse(config["admin_changelist"])
        context["is_asset_type_catalog"] = self.catalog_slug == "tipos-activo"
        return context


class Admin2CatalogFormView(Admin2CatalogsContextMixin, FormView):
    template_name = "admin2/catalogo_formulario.html"
    object = None
    action_label = "Guardar"

    def get_form_class(self):
        config = self.get_catalog_config()
        form_class = modelform_factory(
            config["model"],
            fields=config["fields"],
        )
        if "descripcion" in form_class.base_fields:
            form_class.base_fields["descripcion"].widget = forms.Textarea(
                attrs={"rows": 4}
            )
        for field_name, field in form_class.base_fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({"class": "admin2-checkbox"})
            else:
                base_class = "admin2-input"
                if isinstance(field.widget, forms.Textarea):
                    base_class = "admin2-textarea"
                field.widget.attrs.update({"class": base_class})
        return form_class

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.object is not None:
            kwargs["instance"] = self.object
        return kwargs

    def get_success_url(self):
        return reverse("admin2-catalogo-lista", args=[self.catalog_slug])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = self.get_catalog_config()
        context["catalog"] = config
        context["catalog_slug"] = self.catalog_slug
        context["catalog_cards"] = self.get_catalog_cards()
        context["form_title"] = f"{self.action_label} {config['singular'].lower()}"
        context["form_submit_label"] = self.action_label
        context["back_url"] = self.get_success_url()
        context["admin2_page_title"] = config["title"]
        context["admin2_page_subtitle"] = f"{self.action_label} registro en {config['title']}"
        return context

    def form_valid(self, form):
        self.object = form.save()
        messages.success(
            self.request,
            f"{self.get_catalog_config()['singular']} guardado correctamente.",
        )
        return redirect(self.get_success_url())


class Admin2CatalogCreateView(Admin2CatalogFormView):
    action_label = "Crear"


class Admin2CatalogUpdateView(Admin2CatalogFormView):
    action_label = "Actualizar"

    def dispatch(self, request, *args, **kwargs):
        self.object = get_object_or_404(
            self.get_catalog_model(),
            pk=kwargs["pk"],
        )
        return super().dispatch(request, *args, **kwargs)


class Admin2AttributeSchemaAccessMixin(Admin2AccessMixin, Admin2BaseContextMixin):
    """Acceso separado: crear activos no concede acceso al esquema dinamico."""

    def test_func(self):
        user = self.request.user
        return user.is_superuser or user.has_perm("catalogos.manage_asset_attribute_schema")

    def get_schema_context(self):
        return {
            "admin2_page_subtitle": "Atributos configurables por tipo de activo",
            "attribute_count": AtributoActivo.objects.count(),
            "configuration_count": TipoActivoAtributo.objects.filter(activo=True).count(),
        }


class Admin2AtributoListView(Admin2AttributeSchemaAccessMixin, TemplateView):
    template_name = "admin2/atributos_lista.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        tipo_dato = self.request.GET.get("tipo_dato", "").strip()
        estado = self.request.GET.get("estado", "").strip()
        queryset = AtributoActivo.objects.prefetch_related("configuraciones_tipo__tipo_activo")
        if query:
            queryset = queryset.filter(
                Q(nombre__icontains=query) | Q(clave__icontains=query) | Q(descripcion__icontains=query)
            )
        if tipo_dato:
            queryset = queryset.filter(tipo_dato=tipo_dato)
        if estado == "activos":
            queryset = queryset.filter(activo=True)
        elif estado == "inactivos":
            queryset = queryset.filter(activo=False)
        context.update(self.get_schema_context())
        context.update({
            "admin2_page_title": "Atributos de activos",
            "atributos": queryset.order_by("nombre", "clave"),
            "query": query,
            "tipo_dato": tipo_dato,
            "estado": estado,
            "tipos_dato": AtributoActivo.TipoDato.choices,
        })
        return context


class Admin2AtributoFormView(Admin2AttributeSchemaAccessMixin, FormView):
    template_name = "admin2/atributo_formulario.html"
    form_class = AtributoActivoAdmin2Form
    object = None

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("pk"):
            self.object = get_object_or_404(AtributoActivo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.object
        return kwargs

    def get_formset(self):
        kwargs = {"instance": self.object, "prefix": "opciones"}
        if self.request.method == "POST":
            kwargs["data"] = self.request.POST
        return OpcionAtributoActivoAdmin2FormSet(**kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_schema_context())
        context.update({
            "admin2_page_title": "Editar atributo" if self.object else "Nuevo atributo",
            "formset": kwargs.get("formset") or self.get_formset(),
            "object": self.object,
        })
        return context

    def form_valid(self, form):
        formset = self.get_formset()
        if not formset.is_valid():
            return self.render_to_response(self.get_context_data(form=form, formset=formset))
        change = bool(self.object and self.object.pk)
        anterior_activo = self.object.activo if change else None
        with transaction.atomic():
            self.object = form.save(commit=False)
            if not self.object.created_by_id:
                self.object.created_by = self.request.user
            self.object.updated_by = self.request.user
            self.object.save()
            formset.instance = self.object
            formset.save()
            accion = RegistroAuditoria.Accion.MODIFICAR if change else RegistroAuditoria.Accion.CREAR
            if change and anterior_activo != self.object.activo:
                accion = RegistroAuditoria.Accion.ACTIVAR if self.object.activo else RegistroAuditoria.Accion.DESACTIVAR
            registrar_evento(
                entidad="AtributoActivo", objeto_id=self.object.pk, accion=accion,
                resumen=f"{self.object.nombre} ({self.object.clave})", usuario=self.request.user,
                detalle={"campos": form.changed_data, "opciones_actualizadas": formset.has_changed()},
            )
        messages.success(self.request, "Atributo guardado correctamente.")
        return redirect("admin2-atributos-lista")


class Admin2ConfiguracionAtributoListView(Admin2AttributeSchemaAccessMixin, TemplateView):
    template_name = "admin2/configuraciones_atributos_lista.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        tipo_id = self.request.GET.get("tipo", "").strip()
        estado = self.request.GET.get("estado", "").strip()
        queryset = TipoActivoAtributo.objects.select_related("tipo_activo", "atributo")
        if query:
            queryset = queryset.filter(
                Q(tipo_activo__nombre__icontains=query)
                | Q(atributo__nombre__icontains=query)
                | Q(atributo__clave__icontains=query)
            )
        if tipo_id.isdigit():
            queryset = queryset.filter(tipo_activo_id=tipo_id)
        if estado == "activos":
            queryset = queryset.filter(activo=True)
        elif estado == "inactivos":
            queryset = queryset.filter(activo=False)
        context.update(self.get_schema_context())
        context.update({
            "admin2_page_title": "Atributos por tipo de activo",
            "configuraciones": queryset.order_by("tipo_activo__nombre", "orden", "atributo__nombre"),
            "tipos_activo": TipoActivo.objects.annotate(
                atributos_activos=Count(
                    "configuraciones_atributos",
                    filter=Q(configuraciones_atributos__activo=True),
                )
            ).order_by("nombre"),
            "query": query, "tipo_id": tipo_id, "estado": estado,
            "limite_atributos": int(getattr(settings, "MAX_ATRIBUTOS_ACTIVOS_POR_TIPO", 10)),
        })
        return context


class Admin2ConfiguracionAtributoFormView(Admin2AttributeSchemaAccessMixin, FormView):
    template_name = "admin2/configuracion_atributo_formulario.html"
    form_class = TipoActivoAtributoAdmin2Form
    object = None

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get("pk"):
            self.object = get_object_or_404(TipoActivoAtributo, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"instance": self.object, "creando": self.object is None})
        if self.object is None and self.request.method == "GET" and self.request.GET.get("tipo", "").isdigit():
            kwargs["initial"] = {"tipo_activo": self.request.GET["tipo"]}
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_schema_context())
        limite = int(getattr(settings, "MAX_ATRIBUTOS_ACTIVOS_POR_TIPO", 10))
        context.update({
            "admin2_page_title": "Editar configuracion" if self.object else "Vincular atributo a un tipo",
            "object": self.object,
            "limite_atributos": limite,
        })
        return context

    def form_valid(self, form):
        change = bool(self.object and self.object.pk)
        anterior_activo = self.object.activo if change else None
        with transaction.atomic():
            self.object = form.save(commit=False)
            TipoActivo.objects.select_for_update().get(pk=self.object.tipo_activo_id)
            if not change:
                ultimo = (
                    TipoActivoAtributo.objects.filter(tipo_activo_id=self.object.tipo_activo_id, activo=True)
                    .aggregate(maximo=Max("orden"))["maximo"] or 0
                )
                self.object.orden = ultimo + 1
            if not self.object.created_by_id:
                self.object.created_by = self.request.user
            self.object.updated_by = self.request.user
            self.object.save()
            accion = RegistroAuditoria.Accion.MODIFICAR if change else RegistroAuditoria.Accion.ASOCIAR
            if change and anterior_activo != self.object.activo:
                accion = RegistroAuditoria.Accion.ACTIVAR if self.object.activo else RegistroAuditoria.Accion.DESACTIVAR
            registrar_evento(
                entidad="TipoActivoAtributo", objeto_id=self.object.pk, accion=accion,
                resumen=f"{self.object.atributo.nombre} en {self.object.tipo_activo.nombre}",
                usuario=self.request.user,
                detalle={"campos": form.changed_data, "orden": self.object.orden},
            )
        messages.success(self.request, "Configuracion guardada correctamente.")
        return redirect("admin2-configuraciones-atributos-lista")


class Admin2ConfiguracionAtributoDesactivarView(Admin2AttributeSchemaAccessMixin, View):
    def post(self, request, pk):
        configuracion = get_object_or_404(
            TipoActivoAtributo.objects.select_related("tipo_activo", "atributo"), pk=pk
        )
        if configuracion.activo:
            configuracion.activo = False
            configuracion.updated_by = request.user
            configuracion.save(update_fields=("activo", "updated_by", "updated_at"))
            registrar_evento(
                entidad="TipoActivoAtributo", objeto_id=configuracion.pk,
                accion=RegistroAuditoria.Accion.DESACTIVAR,
                resumen=f"{configuracion.atributo.nombre} fue quitado de {configuracion.tipo_activo.nombre}",
                usuario=request.user,
                detalle={"historial_conservado": True},
            )
            messages.success(request, "El atributo fue quitado del tipo; sus valores historicos se conservaron.")
        return redirect("admin2-configuraciones-atributos-lista")


class Admin2UsuariosView(Admin2ModuleView):
    module_slug = "usuarios"


class Admin2CatalogosView(Admin2ModuleView):
    module_slug = "catalogos"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["catalog_cards"] = self.get_catalog_cards()
        return context


class Admin2SeguridadView(Admin2ModuleView):
    module_slug = "seguridad"


class Admin2ReportesView(Admin2ModuleView):
    module_slug = "reportes"


class Admin2InventarioView(Admin2ModuleView):
    module_slug = "inventario"


class Admin2AuditoriaView(Admin2ModuleView):
    module_slug = "auditoria"
