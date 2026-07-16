from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("facturas", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="eventofactura",
            name="accion",
            field=models.CharField(
                choices=[
                    ("creacion", "Creacion"), ("edicion", "Edicion de metadatos"),
                    ("asociacion", "Actualizacion de activos asociados"),
                    ("reemplazo", "Reemplazo de documento"), ("estado", "Cambio de estado"),
                    ("eliminacion", "Eliminacion"), ("descarga", "Descarga de documento"),
                ],
                max_length=20,
            ),
        ),
    ]
