from django.db import migrations, models
import django.db.models.deletion


def asignar_modalidad_propia(apps, schema_editor):
    Activo = apps.get_model("activos", "Activo")
    Activo.objects.filter(modalidad_tenencia__isnull=True).update(
        modalidad_tenencia="PROPIO"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("proveedores", "0001_initial"),
        ("activos", "0018_activo_ubicacion_fisica"),
    ]

    operations = [
        migrations.AddField(
            model_name="activo",
            name="modalidad_tenencia",
            field=models.CharField(
                choices=[("PROPIO", "Propio"), ("ARRENDADO", "Arrendado")],
                db_index=True,
                default="PROPIO",
                max_length=12,
                verbose_name="Modalidad de tenencia",
            ),
        ),
        migrations.RunPython(asignar_modalidad_propia, migrations.RunPython.noop),
        migrations.AddField(
            model_name="activo",
            name="proveedor_propietario",
            field=models.ForeignKey(
                blank=True,
                help_text="Proveedor titular del activo cuando la modalidad es arrendada.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="activos_en_arrendamiento",
                to="proveedores.proveedor",
                verbose_name="Proveedor propietario",
            ),
        ),
    ]
