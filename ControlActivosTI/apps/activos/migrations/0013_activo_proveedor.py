import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("proveedores", "0001_initial"), ("activos", "0012_activo_empresa")]
    operations = [
        migrations.AddField(
            model_name="activo",
            name="proveedor",
            field=models.ForeignKey(blank=True, help_text="Proveedor de adquisicion del activo.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="activos", to="proveedores.proveedor"),
        ),
    ]
