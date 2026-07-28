"""Configuracion para desarrollo y produccion (APP_ENV=production)."""
from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
APP_ENV = config("APP_ENV", default="development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}


def env_bool(name, default=False):
    return config(name, default=default, cast=bool)


def required(name):
    value = config(name, default="").strip()
    if IS_PRODUCTION and not value:
        raise ImproperlyConfigured(f"La variable {name} es obligatoria en produccion.")
    return value


SECRET_KEY = required("SECRET_KEY") or "django-insecure-development-only-change-me"
DEBUG = env_bool("DEBUG", default=not IS_PRODUCTION)
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured("DEBUG debe ser False en produccion.")
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="" if IS_PRODUCTION else "127.0.0.1,localhost,testserver", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "django.contrib.humanize",
    "apps.accounts", "apps.catalogos",
    "apps.colaboradores", "apps.proveedores", "apps.facturas", "apps.activos",
    "apps.asignaciones", "apps.actas", "apps.auditoria", "apps.notificaciones",
    "apps.depreciacion",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": [
    "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
    "django.contrib.messages.context_processors.messages", "apps.accounts.context_processors.current_user_profile",
    "apps.notificaciones.context_processors.notifications_context",
]}}]
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": required("DB_NAME") or "controlactivos_dev",
    "USER": required("DB_USER") or "postgres", "PASSWORD": required("DB_PASSWORD"),
    "HOST": config("DB_HOST", default="127.0.0.1"), "PORT": config("DB_PORT", default="5432"),
    "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60 if IS_PRODUCTION else 0, cast=int),
    "CONN_HEALTH_CHECKS": IS_PRODUCTION,
}}
LANGUAGE_CODE = config("LANGUAGE_CODE", default="es-ec")
TIME_ZONE = config("TIME_ZONE", default="America/Guayaquil")
USE_I18N = USE_TZ = True
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["apps.accounts.hashers.ControlActivosScryptPasswordHasher", "django.contrib.auth.hashers.PBKDF2PasswordHasher", "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher", "django.contrib.auth.hashers.Argon2PasswordHasher", "django.contrib.auth.hashers.BCryptSHA256PasswordHasher"]

STATIC_URL = "/static/"
STATIC_ROOT = Path(config("STATIC_ROOT", default="/var/www/controlactivosti/static" if IS_PRODUCTION else str(BASE_DIR / "staticfiles")))
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(config("MEDIA_ROOT", default="/var/www/controlactivosti/media" if IS_PRODUCTION else str(BASE_DIR / "media")))
PRIVATE_MEDIA_ROOT = Path(config("PRIVATE_MEDIA_ROOT", default="/var/www/controlactivosti/private" if IS_PRODUCTION else str(BASE_DIR / "private_media")))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "facturas": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": PRIVATE_MEDIA_ROOT}},
}
FILE_UPLOAD_MAX_MEMORY_SIZE = config("FILE_UPLOAD_MAX_MEMORY_SIZE", default=2621440, cast=int)
DATA_UPLOAD_MAX_MEMORY_SIZE = config("DATA_UPLOAD_MAX_MEMORY_SIZE", default=20 * 1024 * 1024, cast=int)
FACTURAS_PDF_MAX_SIZE = config("FACTURAS_PDF_MAX_SIZE", default=15 * 1024 * 1024, cast=int)
FACTURAS_PDF_MAX_PAGES = config("FACTURAS_PDF_MAX_PAGES", default=300, cast=int)
LOGIN_URL, LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL = "accounts:login", "/dashboard/", "accounts:login"
NOTIFICATIONS_READ_RETENTION_DAYS = config(
    "NOTIFICATIONS_READ_RETENTION_DAYS", default=180, cast=int
)
NOTIFICATIONS_UNREAD_RETENTION_DAYS = config(
    "NOTIFICATIONS_UNREAD_RETENTION_DAYS", default=365, cast=int
)

USE_X_FORWARDED_HOST = IS_PRODUCTION
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
ENABLE_HTTPS = env_bool("ENABLE_HTTPS", False)
SECURE_SSL_REDIRECT = SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = IS_PRODUCTION and ENABLE_HTTPS
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000 if ENABLE_HTTPS else 0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = ENABLE_HTTPS
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False) and ENABLE_HTTPS
SESSION_COOKIE_HTTPONLY = CSRF_COOKIE_HTTPONLY = SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SAMESITE = CSRF_COOKIE_SAMESITE = "Lax"
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

LOG_DIR = Path(config("LOG_DIR", default="/var/log/controlactivosti" if IS_PRODUCTION else str(BASE_DIR / "logs")))
if IS_PRODUCTION:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ImproperlyConfigured(f"No se pudo preparar LOG_DIR: {exc}") from exc
file_handler = {"class": "logging.handlers.RotatingFileHandler", "filename": str(LOG_DIR / "application.log"), "maxBytes": 10485760, "backupCount": 10, "formatter": "standard", "encoding": "utf-8"} if IS_PRODUCTION else {"class": "logging.StreamHandler", "formatter": "standard"}
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "formatters": {"standard": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}, "application": file_handler},
    "loggers": {"django": {"handlers": ["console", "application"] if IS_PRODUCTION else ["console"], "level": "INFO", "propagate": False}, "controlactivos": {"handlers": ["application"], "level": "INFO", "propagate": False}},
}
