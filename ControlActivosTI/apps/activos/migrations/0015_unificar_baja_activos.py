from django.db import migrations


def separar_baja_de_eliminacion(apps, schema_editor):
    EstadoActivo = apps.get_model("catalogos", "EstadoActivo")
    Activo = apps.get_model("activos", "Activo")

    estados_baja = EstadoActivo.objects.filter(nombre__iexact="Dado de baja")
    ids_estados_baja = list(estados_baja.values_list("pk", flat=True))

    if ids_estados_baja:
        estado_baja_id = ids_estados_baja[0]
        # Antes de esta separación, activo=False era presentado al usuario como
        # "Dado de baja". Se conservan esos registros bajo el nuevo estado
        # operativo visible; las eliminaciones lógicas empiezan desde esta versión.
        Activo.objects.filter(activo=False).update(
            activo=True,
            estado_activo_id=estado_baja_id,
        )
        Activo.objects.filter(estado_activo_id__in=ids_estados_baja).update(
            activo=True
        )
        estados_baja.update(activo=True, permite_asignacion=False)


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0005_alter_empresa_options"),
        ("activos", "0014_activo_factura_compra"),
    ]

    operations = [
        migrations.RunPython(
            separar_baja_de_eliminacion,
            migrations.RunPython.noop,
        ),
    ]
