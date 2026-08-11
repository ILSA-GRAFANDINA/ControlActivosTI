import logging
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404, HttpResponseRedirect, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.utils.text import get_valid_filename
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.catalogos.models import Empresa
from apps.notificaciones.services import NotificationService
from apps.proveedores.models import Proveedor

from .forms import AsociarActivosForm, FacturaCompraForm, ReemplazarDocumentoForm
from .models import EventoFactura, FacturaCompra, ReemplazoDocumentoFactura

logger = logging.getLogger("controlactivos")


def ip_cliente(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",", 1)[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def registrar_evento(factura, accion, usuario, detalle=None):
    EventoFactura.objects.create(
        factura=factura,
        numero_factura=factura.numero_factura,
        accion=accion,
        detalle=detalle or {},
        usuario=usuario,
    )


class FacturaListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "facturas.view_facturacompra"
    raise_exception = True
    model = FacturaCompra
    template_name = "facturas/lista.html"
    context_object_name = "facturas"
    paginate_by = 12
    FILTER_SESSION_KEY = "facturas_filtros_guardados"
    FILTER_FIELDS = ("q", "fecha_desde", "fecha_hasta", "orden")
    FILTER_MULTI_FIELDS = ("proveedor", "empresa", "estado", "relaciones", "cols")
    ESTADOS_FILTRO = (
        ("activa", "Activas"),
        ("archivada", "Archivadas"),
    )
    RELACIONES_FILTRO = (
        ("con_activos", "Con activos"),
        ("sin_activos", "Sin activos"),
    )
    ORDENES = {
        "recientes": ("-fecha_emision", "-id"),
        "antiguas": ("fecha_emision", "id"),
        "numero_asc": ("numero_factura", "id"),
        "numero_desc": ("-numero_factura", "-id"),
    }
    ORDENES_CHOICES = (
        ("recientes", "Emisión más reciente"),
        ("antiguas", "Emisión más antigua"),
        ("numero_asc", "Factura: A a Z"),
        ("numero_desc", "Factura: Z a A"),
    )
    COLUMNAS_DISPONIBLES = [
        ("proveedor", "Proveedor"),
        ("empresa", "Empresa"),
        ("emision", "Emisión"),
        ("documento", "Documento"),
        ("estado", "Estado"),
        ("activos", "Activos"),
    ]
    COLUMNAS_POR_DEFECTO = ["proveedor", "empresa", "emision", "documento", "estado", "activos"]

    def _default_filters(self):
        return {
            **{
                field: "recientes" if field == "orden" else ""
                for field in self.FILTER_FIELDS
            },
            **{field: [] for field in self.FILTER_MULTI_FIELDS},
        }

    def _sanitize_filters(self, filtros):
        filtros = {**self._default_filters(), **(filtros or {})}
        for field in ("q", "fecha_desde", "fecha_hasta"):
            filtros[field] = (filtros.get(field, "") or "").strip()
        filtros["orden"] = (
            filtros["orden"] if filtros.get("orden") in self.ORDENES else "recientes"
        )

        estados_validos = {value for value, _ in self.ESTADOS_FILTRO}
        relaciones_validas = {value for value, _ in self.RELACIONES_FILTRO}
        columnas_validas = {key for key, _ in self.COLUMNAS_DISPONIBLES}
        validadores = {
            "proveedor": str.isdigit,
            "empresa": str.isdigit,
            "estado": lambda value: value in estados_validos,
            "relaciones": lambda value: value in relaciones_validas,
            "cols": lambda value: value in columnas_validas,
        }
        for field in self.FILTER_MULTI_FIELDS:
            values = filtros.get(field, [])
            if isinstance(values, str):
                values = [value for value in values.split(",") if value]
            filtros[field] = list(
                dict.fromkeys(
                    str(value).strip()
                    for value in values
                    if str(value).strip() and validadores[field](str(value).strip())
                )
            )
        filtros["cols"] = filtros["cols"] or self.COLUMNAS_POR_DEFECTO
        return filtros

    def _filters_from_request(self):
        source = self.request.GET
        filtros = {
            field: (source.get(field, "") or "").strip()
            for field in self.FILTER_FIELDS
        }
        filtros["orden"] = filtros["orden"] or "recientes"
        for field in self.FILTER_MULTI_FIELDS:
            filtros[field] = source.getlist(field)
        return self._sanitize_filters(filtros)

    def _has_filter_params(self):
        return any(
            field in self.request.GET
            for field in (*self.FILTER_FIELDS, *self.FILTER_MULTI_FIELDS)
        )

    def get_active_filters(self):
        if hasattr(self, "_active_filters"):
            return self._active_filters

        if self.request.GET.get("reset") == "1":
            self.request.session.pop(self.FILTER_SESSION_KEY, None)
            self.request.session.modified = True
            self._active_filters = self._default_filters()
            return self._active_filters

        if self._has_filter_params():
            self._active_filters = self._filters_from_request()
            self.request.session[self.FILTER_SESSION_KEY] = self._active_filters
            self.request.session.modified = True
            return self._active_filters

        filtros_guardados = self.request.session.get(self.FILTER_SESSION_KEY, {})
        self._active_filters = self._sanitize_filters(
            filtros_guardados if isinstance(filtros_guardados, dict) else {}
        )
        return self._active_filters

    def build_filter_querydict(self, filtros=None):
        filtros = filtros or self.get_active_filters()
        params = QueryDict("", mutable=True)
        if filtros["q"]:
            params["q"] = filtros["q"]
        for field in self.FILTER_MULTI_FIELDS:
            if field == "cols" and filtros[field] == self.COLUMNAS_POR_DEFECTO:
                continue
            params.setlist(field, filtros[field])
        if filtros["fecha_desde"]:
            params["fecha_desde"] = filtros["fecha_desde"]
        if filtros["fecha_hasta"]:
            params["fecha_hasta"] = filtros["fecha_hasta"]
        if filtros["orden"] != "recientes":
            params["orden"] = filtros["orden"]
        return params

    def get_selected_columns(self):
        seleccionadas = self.get_active_filters()["cols"]
        return seleccionadas or self.COLUMNAS_POR_DEFECTO

    def get_queryset(self):
        filtros = self.get_active_filters()
        queryset = FacturaCompra.objects.select_related("proveedor", "empresa", "cargado_por").annotate(
            activos_count=Count("activos", distinct=True)
        )
        q = filtros["q"]
        if q:
            queryset = queryset.filter(
                Q(numero_factura__icontains=q)
                | Q(proveedor__razon_social__icontains=q)
                | Q(proveedor__nombre_comercial__icontains=q)
                | Q(proveedor__identificacion__icontains=q)
                | Q(activos__codigo__icontains=q)
                | Q(activos__serie__icontains=q)
                | Q(activos__marca__icontains=q)
                | Q(activos__modelo__icontains=q)
            ).distinct()

        if filtros["proveedor"]:
            queryset = queryset.filter(proveedor_id__in=filtros["proveedor"])
        if filtros["empresa"]:
            queryset = queryset.filter(empresa_id__in=filtros["empresa"])

        estados = filtros["estado"]
        if estados and set(estados) != {"activa", "archivada"}:
            queryset = queryset.filter(activa="activa" in estados)

        relaciones = filtros["relaciones"]
        if relaciones and set(relaciones) != {"con_activos", "sin_activos"}:
            if "con_activos" in relaciones:
                queryset = queryset.filter(activos_count__gt=0)
            elif "sin_activos" in relaciones:
                queryset = queryset.filter(activos_count=0)

        fecha_desde = parse_date(filtros["fecha_desde"])
        fecha_hasta = parse_date(filtros["fecha_hasta"])
        if fecha_desde:
            queryset = queryset.filter(fecha_emision__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_emision__lte=fecha_hasta)

        return queryset.order_by(*self.ORDENES[filtros["orden"]])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtros = self.get_active_filters()
        columnas_seleccionadas = self.get_selected_columns()
        context.update({
            "busqueda": filtros["q"],
            "proveedor_seleccionado": filtros["proveedor"][0] if filtros["proveedor"] else "",
            "proveedores_seleccionados": filtros["proveedor"],
            "empresa_seleccionada": filtros["empresa"][0] if filtros["empresa"] else "",
            "empresas_seleccionadas": filtros["empresa"],
            "estado_seleccionado": filtros["estado"][0] if filtros["estado"] else "",
            "estados_seleccionados": filtros["estado"],
            "relaciones_seleccionadas": filtros["relaciones"][0] if filtros["relaciones"] else "",
            "relaciones_lista_seleccionadas": filtros["relaciones"],
            "fecha_desde": filtros["fecha_desde"],
            "fecha_hasta": filtros["fecha_hasta"],
            "orden_seleccionado": filtros["orden"],
            "proveedores": Proveedor.objects.order_by("razon_social"),
            "empresas": Empresa.objects.order_by("nombre"),
            "estados_filtro": self.ESTADOS_FILTRO,
            "relaciones_filtro": self.RELACIONES_FILTRO,
            "ordenes_disponibles": self.ORDENES_CHOICES,
            "columnas_disponibles": self.COLUMNAS_DISPONIBLES,
            "columnas_seleccionadas": columnas_seleccionadas,
            "total_columnas_tabla": len(columnas_seleccionadas) + 1,
            "cantidad_filtros_activos": (
                bool(filtros["q"])
                + sum(len(filtros[field]) for field in self.FILTER_MULTI_FIELDS if field != "cols")
                + bool(filtros["fecha_desde"])
                + bool(filtros["fecha_hasta"])
                + (filtros["orden"] != "recientes")
            ),
        })
        context["query_string"] = self.build_filter_querydict(filtros).urlencode()
        if context.get("is_paginated"):
            context["page_numbers"] = context["paginator"].get_elided_page_range(context["page_obj"].number)
        return context


class FacturaFormMixin:
    model = FacturaCompra
    form_class = FacturaCompraForm
    template_name = "facturas/formulario.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class FacturaCreateView(LoginRequiredMixin, PermissionRequiredMixin, FacturaFormMixin, CreateView):
    permission_required = "facturas.add_facturacompra"
    raise_exception = True

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                registrar_evento(
                    self.object,
                    EventoFactura.Accion.CREACION,
                    self.request.user,
                    {
                        "proveedor_id": self.object.proveedor_id,
                        "empresa_id": self.object.empresa_id,
                        "fecha_emision": self.object.fecha_emision.isoformat(),
                        "tamano_original": self.object.tamano_original,
                        "tamano_almacenado": self.object.tamano_almacenado,
                        "estado_compresion": self.object.estado_compresion,
                        "checksum_sha256": self.object.checksum_sha256,
                    },
                )
                NotificationService.factura_guardada(
                    self.object, self.request.user, creada=True
                )
        except Exception:
            archivo = getattr(form.instance, "archivo", None)
            if archivo and archivo.name:
                archivo.storage.delete(archivo.name)
            raise
        messages.success(self.request, "Factura registrada correctamente.")
        return response

    def get_success_url(self):
        return reverse("facturas:detalle", args=[self.object.pk])


class FacturaUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FacturaFormMixin, UpdateView):
    permission_required = "facturas.change_facturacompra"
    raise_exception = True

    def get_queryset(self):
        return FacturaCompra.objects.select_related("proveedor", "empresa").prefetch_related("activos")

    def form_valid(self, form):
        cambios = set(form.changed_data) & {
            "proveedor",
            "empresa",
            "numero_factura",
            "fecha_emision",
        }
        with transaction.atomic():
            response = super().form_valid(form)
            registrar_evento(
                self.object, EventoFactura.Accion.EDICION, self.request.user,
                {"proveedor_id": self.object.proveedor_id, "empresa_id": self.object.empresa_id},
            )
            NotificationService.factura_guardada(
                self.object, self.request.user, cambios=cambios
            )
        messages.success(self.request, "Metadatos de la factura actualizados correctamente.")
        return response

    def get_success_url(self):
        return reverse("facturas:detalle", args=[self.object.pk])


class FacturaDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "facturas.view_facturacompra"
    raise_exception = True
    model = FacturaCompra
    template_name = "facturas/detalle.html"
    context_object_name = "factura"

    def get_queryset(self):
        return FacturaCompra.objects.select_related("proveedor", "empresa", "cargado_por").prefetch_related(
            "activos__tipo_activo", "activos__estado_activo", "reemplazos__reemplazado_por",
            "eventos__usuario",
        ).annotate(activos_count=Count("activos", distinct=True))


class FacturaAsociarActivosView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = ("facturas.associate_facturacompra", "activos.change_activo")
    raise_exception = True
    template_name = "facturas/asociar_activos.html"

    def get_factura(self, pk):
        return get_object_or_404(
            FacturaCompra.objects.select_related("proveedor", "empresa").prefetch_related("activos"), pk=pk
        )

    def get_context(self, factura, form):
        activos_disponibles = list(form.fields["activos"].queryset)
        if form.is_bound:
            activos_seleccionados = self.request.POST.getlist("activos")
        else:
            activos_seleccionados = [
                str(pk) for pk in factura.activos.values_list("pk", flat=True)
            ]
        return {
            "factura": factura,
            "form": form,
            "activos_disponibles": activos_disponibles,
            "activos_seleccionados": activos_seleccionados,
            "activos_asociados_ids": set(
                factura.activos.values_list("pk", flat=True)
            ),
            "tipos_disponibles": sorted(
                {activo.tipo_activo for activo in activos_disponibles},
                key=lambda tipo: tipo.nombre.lower(),
            ),
            "estados_disponibles": sorted(
                {activo.estado_activo for activo in activos_disponibles},
                key=lambda estado: estado.nombre.lower(),
            ),
        }

    def get(self, request, pk):
        factura = self.get_factura(pk)
        form = AsociarActivosForm(factura=factura)
        return render(request, self.template_name, self.get_context(factura, form))

    def post(self, request, pk):
        factura = self.get_factura(pk)
        form = AsociarActivosForm(request.POST, factura=factura)
        if not form.is_valid():
            return render(request, self.template_name, self.get_context(factura, form))
        if not factura.activa:
            messages.error(request, "No se pueden crear asociaciones nuevas con una factura archivada.")
            return redirect("facturas:detalle", pk=pk)
        seleccionados = list(form.cleaned_data["activos"])
        ids_seleccionados = {activo.pk for activo in seleccionados}
        with transaction.atomic():
            for activo in factura.activos.exclude(pk__in=ids_seleccionados):
                activo.factura_compra = None
                activo.save(update_fields=["factura_compra", "updated_at"])
            for activo in seleccionados:
                activo.factura_compra = factura
                activo.save()
            registrar_evento(
                factura, EventoFactura.Accion.ASOCIACION, request.user,
                {"activos_ids": sorted(ids_seleccionados)},
            )
        messages.success(request, "Asociaciones de activos actualizadas correctamente.")
        return redirect("facturas:detalle", pk=pk)


class FacturaDocumentoView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "facturas.download_facturacompra"
    raise_exception = True

    def get(self, request, pk, descargar=False):
        factura = get_object_or_404(FacturaCompra.objects.only("archivo", "nombre_original"), pk=pk)
        if not factura.archivo or not factura.archivo.storage.exists(factura.archivo.name):
            raise Http404("El documento no esta disponible.")
        nombre = get_valid_filename(Path(factura.nombre_original).name) or f"factura-{pk}.pdf"
        response = FileResponse(
            factura.archivo.storage.open(factura.archivo.name, "rb"),
            content_type="application/pdf",
            as_attachment=descargar,
            filename=nombre,
        )
        response["X-Content-Type-Options"] = "nosniff"
        registrar_evento(factura, EventoFactura.Accion.DESCARGA, request.user, {
            "ip": ip_cliente(request), "modo": "descarga" if descargar else "visualizacion",
        })
        logger.info("Documento factura consultado factura_id=%s usuario_id=%s ip=%s", pk, request.user.pk, ip_cliente(request))
        return response


class FacturaEstadoView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "facturas.archive_facturacompra"
    raise_exception = True

    def post(self, request, pk):
        factura = get_object_or_404(FacturaCompra, pk=pk)
        factura.activa = not factura.activa
        factura.save(update_fields=["activa", "updated_at"])
        registrar_evento(
            factura, EventoFactura.Accion.ESTADO, request.user, {"activa": factura.activa}
        )
        NotificationService.factura_guardada(
            factura, request.user, cambios={"estado"}
        )
        messages.success(request, "Factura activada correctamente." if factura.activa else "Factura archivada correctamente.")
        return redirect("facturas:detalle", pk=pk)


class FacturaReemplazarView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "facturas.replace_facturacompra"
    raise_exception = True
    template_name = "facturas/reemplazar.html"

    def get(self, request, pk):
        factura = get_object_or_404(FacturaCompra, pk=pk)
        return render(request, self.template_name, {"factura": factura, "form": ReemplazarDocumentoForm()})

    def post(self, request, pk):
        factura = get_object_or_404(FacturaCompra, pk=pk)
        form = ReemplazarDocumentoForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"factura": factura, "form": form})
        nuevo = form.pdf_procesado
        if nuevo.checksum_sha256 == factura.checksum_sha256:
            form.add_error("archivo", "El documento nuevo es identico al documento actual.")
            return render(request, self.template_name, {"factura": factura, "form": form})

        nombre_anterior = factura.archivo.name
        storage = factura.archivo.storage
        with storage.open(nombre_anterior, "rb") as anterior:
            copia_anterior = ContentFile(anterior.read(), name="documento-anterior.pdf")
        with transaction.atomic():
            reemplazo = ReemplazoDocumentoFactura(
                factura=factura,
                checksum_anterior=factura.checksum_sha256,
                archivo_nuevo="pendiente",
                checksum_nuevo=nuevo.checksum_sha256,
                motivo=form.cleaned_data["motivo"],
                reemplazado_por=request.user,
            )
            reemplazo.archivo_anterior = copia_anterior
            reemplazo.save()
            factura.archivo = nuevo.archivo
            factura.nombre_original = nuevo.nombre_original
            factura.tamano_original = nuevo.tamano_original
            factura.tamano_almacenado = nuevo.tamano_almacenado
            factura.estado_compresion = nuevo.estado_compresion
            factura.checksum_sha256 = nuevo.checksum_sha256
            factura.numero_paginas = nuevo.paginas
            factura.save()
            reemplazo.archivo_nuevo = factura.archivo.name
            reemplazo.save(update_fields=["archivo_nuevo"])
            registrar_evento(
                factura, EventoFactura.Accion.REEMPLAZO, request.user,
                {"motivo": form.cleaned_data["motivo"], "checksum_anterior": reemplazo.checksum_anterior, "checksum_nuevo": reemplazo.checksum_nuevo},
            )
            NotificationService.factura_guardada(
                factura, request.user, cambios={"documento"}
            )
            transaction.on_commit(lambda: storage.delete(nombre_anterior))
        messages.success(request, "Documento reemplazado y versión anterior conservada en el historial.")
        return redirect("facturas:detalle", pk=pk)


class FacturaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    permission_required = "facturas.delete_facturacompra"
    raise_exception = True
    model = FacturaCompra
    template_name = "facturas/confirmar_eliminar.html"
    success_url = reverse_lazy("facturas:lista")

    def form_valid(self, form):
        factura = self.object
        if factura.activos.exists():
            messages.error(self.request, "No se puede eliminar una factura con activos relacionados. Archivala en su lugar.")
            return HttpResponseRedirect(reverse("facturas:detalle", args=[factura.pk]))
        storage = factura.archivo.storage
        archivos = [factura.archivo.name] if factura.archivo else []
        archivos.extend(
            factura.reemplazos.exclude(archivo_anterior="").values_list("archivo_anterior", flat=True)
        )
        try:
            with transaction.atomic():
                registrar_evento(
                    factura, EventoFactura.Accion.ELIMINACION, self.request.user,
                    {"proveedor_id": factura.proveedor_id, "empresa_id": factura.empresa_id},
                )
                response = super().form_valid(form)
                if archivos:
                    transaction.on_commit(lambda: [storage.delete(nombre) for nombre in archivos])
        except ProtectedError:
            messages.error(self.request, "La factura tiene relaciones protegidas y no puede eliminarse.")
            return HttpResponseRedirect(reverse("facturas:detalle", args=[factura.pk]))
        messages.success(self.request, "Factura eliminada correctamente.")
        return response
