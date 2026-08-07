from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activos", "0016_alter_activo_options_valoratributoactivo"),
    ]

    operations = [
        migrations.AddField(
            model_name="activo",
            name="incluir_en_depreciacion",
            field=models.BooleanField(
                default=True,
                help_text="Desmarca esta opción si el activo no debe depreciarse ni generar alertas.",
                verbose_name="Incluir en depreciación",
            ),
        ),
    ]
