from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0008_atributoactivo_unique_nombre_atributo_ci"),
    ]

    operations = [
        migrations.AlterField(
            model_name="atributoactivo",
            name="tipo_dato",
            field=models.CharField(
                choices=[
                    ("texto_corto", "Texto corto"),
                    ("texto_largo", "Texto largo"),
                    ("texto_protegido", "Texto protegido"),
                    ("entero", "Numero entero"),
                    ("decimal", "Numero decimal"),
                    ("fecha", "Fecha"),
                    ("booleano", "Si / No"),
                    ("lista", "Lista de opciones"),
                ],
                max_length=20,
            ),
        ),
    ]
