from django.db import migrations, models


def renombrar_tipo_eliminacion(apps, schema_editor):
    Notificacion = apps.get_model("notificaciones", "Notificacion")
    Notificacion.objects.filter(tipo="ACTIVO_BAJA").update(
        tipo="ACTIVO_ELIMINADO"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("notificaciones", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            renombrar_tipo_eliminacion,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="notificacion",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("ACTIVO_CREADO", "Activo creado"),
                    ("ACTIVO_CAMBIADO", "Activo modificado"),
                    ("ACTIVO_ELIMINADO", "Activo eliminado"),
                    ("ASIGNACION_CREADA", "Asignación creada"),
                    ("ASIGNACION_CAMBIADA", "Asignación modificada"),
                    ("ASIGNACION_FINALIZADA", "Asignación finalizada"),
                    ("PROVEEDOR_CREADO", "Proveedor creado"),
                    ("PROVEEDOR_CAMBIADO", "Proveedor modificado"),
                    ("FACTURA_CREADA", "Factura creada"),
                    ("FACTURA_CAMBIADA", "Factura modificada"),
                ],
                max_length=28,
            ),
        ),
    ]
