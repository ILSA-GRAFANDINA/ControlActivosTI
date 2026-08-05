from django.db import migrations


def marcar_emitidas(apps, schema_editor):
    ActaEntrega = apps.get_model("actas", "ActaEntrega")
    ActaEntrega.objects.exclude(archivo="").filter(archivo__isnull=False).update(emitida=True)


class Migration(migrations.Migration):
    dependencies = [("actas", "0007_actaentrega_checksum_sha256_actaentrega_emitida_and_more")]
    operations = [migrations.RunPython(marcar_emitidas, migrations.RunPython.noop)]
