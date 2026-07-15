import hashlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from pypdf import PdfReader, PdfWriter


@dataclass
class PdfProcesado:
    archivo: ContentFile
    nombre_original: str
    tamano_original: int
    tamano_almacenado: int
    checksum_sha256: str
    paginas: int
    estado_compresion: str


def _limites_pdf():
    return (
        int(getattr(settings, "FACTURAS_PDF_MAX_SIZE", 15 * 1024 * 1024)),
        int(getattr(settings, "FACTURAS_PDF_MAX_PAGES", 300)),
    )


def _tiene_firma_digital(contenido):
    muestras = (b"/ByteRange", b"/Type/Sig", b"/Type /Sig", b"/SubFilter")
    return any(muestra in contenido for muestra in muestras)


def _abrir_pdf(contenido, max_paginas):
    try:
        reader = PdfReader(BytesIO(contenido), strict=False)
        if reader.is_encrypted:
            raise ValidationError("No se permiten facturas PDF cifradas o protegidas con contrasena.")
        paginas = len(reader.pages)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("El archivo esta corrupto o no es un PDF valido.") from exc

    if paginas < 1:
        raise ValidationError("El PDF debe contener al menos una pagina.")
    if paginas > max_paginas:
        raise ValidationError(f"El PDF supera el limite de {max_paginas} paginas.")
    return reader, paginas


def validar_y_optimizar_pdf(archivo):
    max_bytes, max_paginas = _limites_pdf()
    nombre_original = Path(getattr(archivo, "name", "documento.pdf")).name
    if Path(nombre_original).suffix.lower() != ".pdf":
        raise ValidationError("El archivo debe tener extension .pdf.")

    content_type = (getattr(archivo, "content_type", "") or "").lower()
    if content_type not in {"application/pdf", "application/x-pdf"}:
        raise ValidationError("El tipo MIME del archivo debe ser application/pdf.")

    archivo.seek(0)
    contenido = archivo.read(max_bytes + 1)
    archivo.seek(0)
    if len(contenido) > max_bytes:
        limite_mb = max_bytes / (1024 * 1024)
        raise ValidationError(f"El PDF supera el tamano maximo permitido de {limite_mb:g} MB.")
    if not contenido.startswith(b"%PDF-"):
        raise ValidationError("El encabezado del archivo no corresponde a un PDF real.")
    if b"%%EOF" not in contenido[-2048:]:
        raise ValidationError("El PDF esta incompleto o corrupto.")

    reader, paginas = _abrir_pdf(contenido, max_paginas)
    checksum = hashlib.sha256(contenido).hexdigest()
    resultado = contenido
    estado = "sin_reduccion"

    if _tiene_firma_digital(contenido):
        estado = "firma_digital"
    else:
        try:
            writer = PdfWriter()
            writer.clone_document_from_reader(reader)
            for page in writer.pages:
                page.compress_content_streams()
            optimizado = BytesIO()
            writer.write(optimizado)
            contenido_optimizado = optimizado.getvalue()
            _, paginas_optimizadas = _abrir_pdf(contenido_optimizado, max_paginas)
            if paginas_optimizadas != paginas:
                raise ValueError("La optimizacion altero el numero de paginas.")
            if len(contenido_optimizado) < len(contenido):
                resultado = contenido_optimizado
                estado = "comprimido"
        except Exception:
            resultado = contenido
            estado = "fallo_compresion"

    nombre_interno = f"documento-{checksum[:12]}.pdf"
    return PdfProcesado(
        archivo=ContentFile(resultado, name=nombre_interno),
        nombre_original=nombre_original[:255],
        tamano_original=len(contenido),
        tamano_almacenado=len(resultado),
        checksum_sha256=checksum,
        paginas=paginas,
        estado_compresion=estado,
    )

