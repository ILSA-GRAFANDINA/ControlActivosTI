from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Proveedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_proveedor", models.CharField(choices=[("persona", "Persona"), ("empresa", "Empresa")], max_length=10)),
                ("tipo_identificacion", models.CharField(choices=[("cedula", "Cedula"), ("ruc", "RUC"), ("extranjera", "Identificacion extranjera")], max_length=12)),
                ("identificacion", models.CharField(db_index=True, max_length=40, unique=True)),
                ("razon_social", models.CharField(max_length=180)),
                ("nombre_comercial", models.CharField(blank=True, max_length=180)),
                ("nombre_contacto", models.CharField(blank=True, max_length=180)),
                ("correo_electronico", models.EmailField(blank=True, max_length=254)),
                ("telefono", models.CharField(blank=True, max_length=40)),
                ("direccion", models.CharField(blank=True, max_length=250)),
                ("ciudad", models.CharField(blank=True, max_length=120)),
                ("pais", models.CharField(default="Ecuador", max_length=100)),
                ("activo", models.BooleanField(db_index=True, default=True)),
                ("observaciones", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Proveedor", "verbose_name_plural": "Proveedores", "ordering": ["razon_social", "identificacion"], "permissions": [("change_proveedor_status", "Puede activar o desactivar proveedores")]},
        ),
    ]
