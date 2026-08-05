import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar_evento
from apps.catalogos.models import AtributoActivo, TipoActivoAtributo

from apps.activos.models import Activo, ValorAtributoActivo


LEGACY_FIELDS = {
    "procesador": "cpu",
    "memoria_ram": "ram",
    "almacenamiento": "disco",
    "sistema_operativo": "sistema_operativo",
}

RAM_PATTERN = re.compile(
    r"\s*(\d+)\s*(?:gb|g)?(?:\s*(?:ddr\d+|lpddr\d+x?))?\s*",
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = "Copia las especificaciones heredadas a atributos tipados sin borrar las columnas originales."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--tipo", type=int, action="append", dest="tipos")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size debe ser mayor que cero.")

        atributos = {
            atributo.clave: atributo
            for atributo in AtributoActivo.objects.filter(clave__in=LEGACY_FIELDS)
        }
        faltantes = set(LEGACY_FIELDS) - set(atributos)
        if faltantes:
            raise CommandError(
                "Primero aplica la migracion de configuracion inicial. Faltan: "
                + ", ".join(sorted(faltantes))
            )

        queryset = Activo.objects.select_related("tipo_activo").order_by("pk")
        if options.get("tipos"):
            queryset = queryset.filter(tipo_activo_id__in=options["tipos"])

        creados = actualizados = pendientes = omitidos = 0
        with transaction.atomic():
            for activo in queryset.iterator(chunk_size=batch_size):
                configs = {
                    config.atributo.clave: config
                    for config in TipoActivoAtributo.objects.filter(
                        tipo_activo=activo.tipo_activo,
                        atributo__clave__in=LEGACY_FIELDS,
                    ).select_related("atributo")
                }
                for clave, campo in LEGACY_FIELDS.items():
                    original = (getattr(activo, campo, "") or "").strip()
                    config = configs.get(clave)
                    if not original or not config:
                        omitidos += 1
                        continue
                    atributo = atributos[clave]
                    defaults = {
                        "tipo_activo_origen": activo.tipo_activo,
                        "vigente": True,
                        "valor_original_migracion": original,
                        "requiere_revision": False,
                        "valor_texto": "",
                        "valor_entero": None,
                        "valor_decimal": None,
                        "valor_fecha": None,
                        "valor_booleano": None,
                        "valor_opcion": None,
                    }
                    if clave == "memoria_ram":
                        coincidencia = RAM_PATTERN.fullmatch(original)
                        if coincidencia:
                            defaults["valor_entero"] = int(coincidencia.group(1))
                        else:
                            defaults["requiere_revision"] = True
                            pendientes += 1
                    else:
                        defaults["valor_texto"] = original

                    _valor, creado = ValorAtributoActivo.objects.update_or_create(
                        activo=activo,
                        atributo=atributo,
                        defaults=defaults,
                    )
                    if creado:
                        creados += 1
                    else:
                        actualizados += 1

            registrar_evento(
                entidad="MigracionAtributosActivos",
                objeto_id="legacy-v1",
                accion=RegistroAuditoria.Accion.MIGRAR,
                resumen="Migracion de especificaciones heredadas",
                detalle={
                    "creados": creados,
                    "actualizados": actualizados,
                    "pendientes": pendientes,
                    "omitidos": omitidos,
                    "dry_run": dry_run,
                },
            )
            if dry_run:
                transaction.set_rollback(True)

        modo = "SIMULACION" if dry_run else "APLICADO"
        self.stdout.write(
            self.style.SUCCESS(
                f"{modo}: creados={creados}, actualizados={actualizados}, "
                f"pendientes_revision={pendientes}, omitidos={omitidos}"
            )
        )
