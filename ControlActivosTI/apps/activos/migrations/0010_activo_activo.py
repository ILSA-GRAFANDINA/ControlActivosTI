from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activos", "0009_activo_codigo_sap"),
    ]

    operations = [
        migrations.AddField(
            model_name="activo",
            name="activo",
            field=models.BooleanField(
                default=True,
                help_text="Desactiva este registro para conservarlo sin incluirlo en los totales vigentes.",
            ),
        ),
    ]
