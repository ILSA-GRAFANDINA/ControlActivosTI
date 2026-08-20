from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0009_alter_atributoactivo_tipo_dato_texto_protegido"),
    ]

    operations = [
        migrations.CreateModel(
            name="UbicacionFisicaActivo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100, unique=True)),
                ("descripcion", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Ubicacion fisica de activo",
                "verbose_name_plural": "Ubicaciones fisicas de activos",
                "ordering": ["nombre"],
            },
        ),
    ]
