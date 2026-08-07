import base64
import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError


ENCRYPTED_TEXT_PREFIX = "fernet$"
MASK_CHARACTER = "*"


def _fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:
        raise ValidationError(
            "Instala la dependencia cryptography para guardar atributos protegidos."
        ) from exc

    secret = getattr(settings, "ATTRIBUTE_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(str(secret).encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key), InvalidToken


def encrypt_protected_text(value):
    value = str(value or "").strip()
    if not value:
        return ""
    fernet, _ = _fernet()
    token = fernet.encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_TEXT_PREFIX}{token}"


def decrypt_protected_text(value):
    value = str(value or "")
    if not value:
        return ""
    if not value.startswith(ENCRYPTED_TEXT_PREFIX):
        return value
    fernet, invalid_token = _fernet()
    token = value.removeprefix(ENCRYPTED_TEXT_PREFIX).encode("ascii")
    try:
        return fernet.decrypt(token).decode("utf-8")
    except invalid_token as exc:
        raise ValidationError("El valor protegido no se pudo descifrar.") from exc


def mask_protected_text(value, visible=4):
    plain_text = decrypt_protected_text(value)
    if not plain_text:
        return ""
    if len(plain_text) <= visible * 2:
        return MASK_CHARACTER * len(plain_text)
    return f"{plain_text[:visible]}{MASK_CHARACTER * 4}{plain_text[-visible:]}"
