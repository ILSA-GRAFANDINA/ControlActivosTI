from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0004_departamentoempresa_centrocosto_departamentos"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="empresa",
            options={
                "ordering": ["nombre"],
                "verbose_name": "Empresa",
                "verbose_name_plural": "Empresas de Activos",
            },
        ),
    ]
