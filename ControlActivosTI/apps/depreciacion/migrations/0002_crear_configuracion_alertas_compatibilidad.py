from django.db import migrations


TABLA_CONFIGURACION = "depreciacion_configuracionalertasdepreciacion"


def crear_tabla_configuracion_si_falta(apps, schema_editor):
    tablas = set(schema_editor.connection.introspection.table_names())
    if TABLA_CONFIGURACION in tablas:
        return
    modelo = apps.get_model("depreciacion", "ConfiguracionAlertasDepreciacion")
    schema_editor.create_model(modelo)


class Migration(migrations.Migration):
    dependencies = [
        ("depreciacion", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            crear_tabla_configuracion_si_falta,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
