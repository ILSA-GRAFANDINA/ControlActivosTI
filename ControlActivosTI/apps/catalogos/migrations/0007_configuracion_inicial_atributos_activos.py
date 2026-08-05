import re
import unicodedata

from django.db import migrations


ATRIBUTOS = (
    {
        "clave": "procesador",
        "nombre": "Procesador",
        "tipo_dato": "texto_corto",
        "unidad": "",
        "filtrable": True,
    },
    {
        "clave": "memoria_ram",
        "nombre": "Memoria RAM",
        "tipo_dato": "entero",
        "unidad": "GB",
        "filtrable": True,
        "valor_minimo": 0,
    },
    {
        "clave": "almacenamiento",
        "nombre": "Almacenamiento",
        "tipo_dato": "texto_corto",
        "unidad": "",
        "filtrable": True,
    },
    {
        "clave": "sistema_operativo",
        "nombre": "Sistema operativo",
        "tipo_dato": "texto_corto",
        "unidad": "",
        "filtrable": True,
    },
)

PALABRAS_EQUIPOS = ("laptop", "pc", "desktop", "escritorio", "computador", "computadora")


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", texto.lower()).strip()


def crear_configuracion(apps, schema_editor):
    Atributo = apps.get_model("catalogos", "AtributoActivo")
    TipoActivo = apps.get_model("catalogos", "TipoActivo")
    Configuracion = apps.get_model("catalogos", "TipoActivoAtributo")

    atributos = []
    for datos in ATRIBUTOS:
        atributo, _ = Atributo.objects.update_or_create(
            clave=datos["clave"],
            defaults={
                "nombre": datos["nombre"],
                "tipo_dato": datos["tipo_dato"],
                "unidad": datos["unidad"],
                "descripcion": "Creado para migrar de forma progresiva las especificaciones heredadas.",
                "activo": True,
            },
        )
        atributos.append((atributo, datos))

    for tipo in TipoActivo.objects.all().iterator():
        if not any(palabra in normalizar(tipo.nombre) for palabra in PALABRAS_EQUIPOS):
            continue
        for orden, (atributo, datos) in enumerate(atributos, start=1):
            Configuracion.objects.update_or_create(
                tipo_activo=tipo,
                atributo=atributo,
                defaults={
                    "orden": orden,
                    "obligatorio": False,
                    "mostrar_detalle": True,
                    "mostrar_actas": True,
                    "mostrar_reportes": False,
                    "filtrable": datos["filtrable"],
                    "activo": True,
                    "valor_minimo": datos.get("valor_minimo"),
                    "validaciones": {},
                },
            )


class Migration(migrations.Migration):
    dependencies = [("catalogos", "0006_atributoactivo_opcionatributoactivo_and_more")]
    # Una reversa destructiva podría borrar valores creados después del despliegue.
    # La reversión operativa se realiza restaurando el respaldo validado.
    operations = [migrations.RunPython(crear_configuracion, migrations.RunPython.noop)]
