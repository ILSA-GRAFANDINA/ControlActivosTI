from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0004_departamentoempresa_centrocosto_departamentos"),
        ("activos", "0011_alter_activo_valor"),
    ]

    operations = [
        migrations.AddField(
            model_name="activo",
            name="empresa",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="activos",
                to="catalogos.empresa",
            ),
        ),
    ]
