from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activos", "0010_activo_activo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activo",
            name="valor",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Ingresa el valor con coma de miles, por ejemplo 10,482.00.",
                max_digits=12,
                null=True,
                verbose_name="Valor de Compra",
            ),
        ),
    ]
