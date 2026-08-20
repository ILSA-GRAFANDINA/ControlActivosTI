from django.db import migrations, models
import django.db.models.deletion


def asignar_ubicacion_inicial(apps, schema_editor):
    Activo = apps.get_model("activos", "Activo")
    UbicacionFisicaActivo = apps.get_model("catalogos", "UbicacionFisicaActivo")
    ubicacion, _created = UbicacionFisicaActivo.objects.get_or_create(
        nombre="Sin ubicacion definida",
        defaults={"descripcion": "Valor inicial para activos pendientes de clasificar."},
    )
    Activo.objects.filter(ubicacion_fisica__isnull=True).update(
        ubicacion_fisica=ubicacion
    )


def revertir_ubicacion_inicial(apps, schema_editor):
    Activo = apps.get_model("activos", "Activo")
    Activo.objects.update(ubicacion_fisica=None)


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0010_ubicacionfisicaactivo"),
        ("activos", "0017_activo_incluir_en_depreciacion"),
    ]

    operations = [
        migrations.AddField(
            model_name="activo",
            name="ubicacion_fisica",
            field=models.ForeignKey(
                help_text="Lugar fisico del activo dentro de la empresa.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="activos",
                to="catalogos.ubicacionfisicaactivo",
                verbose_name="Ubicacion fisica",
            ),
        ),
        migrations.RunPython(asignar_ubicacion_inicial, revertir_ubicacion_inicial),
        migrations.AlterField(
            model_name="activo",
            name="ubicacion_fisica",
            field=models.ForeignKey(
                help_text="Lugar fisico del activo dentro de la empresa.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="activos",
                to="catalogos.ubicacionfisicaactivo",
                verbose_name="Ubicacion fisica",
            ),
        ),
    ]
