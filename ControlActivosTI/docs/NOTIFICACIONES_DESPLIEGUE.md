# Despliegue del módulo de notificaciones

El módulo usa únicamente Django y PostgreSQL. No necesita Redis, Celery ni
WebSockets.

## Variables opcionales

```dotenv
NOTIFICATIONS_READ_RETENTION_DAYS=180
NOTIFICATIONS_UNREAD_RETENTION_DAYS=365
```

## Despliegue controlado en Ubuntu

1. Realizar un respaldo verificado de PostgreSQL (`pg_dump`) antes del cambio.
2. Activar el entorno virtual e instalar las dependencias ya declaradas.
3. Revisar el plan sin modificar datos:

   ```bash
   python manage.py showmigrations notificaciones
   python manage.py migrate --plan
   ```

4. Aplicar solo las migraciones pendientes:

   ```bash
   python manage.py migrate
   python manage.py check --deploy
   python manage.py collectstatic --noinput
   ```

La migración crea una tabla y sus índices; no reemplaza bases, no elimina
tablas existentes y no importa datos de desarrollo.

## Limpieza mensual

Antes de programarla:

```bash
python manage.py purge_old_notifications --dry-run
python manage.py purge_old_notifications --batch-size 1000
```

Ejemplo de `cron` mensual (ajustar rutas y usuario del servicio):

```cron
25 2 1 * * cd /var/www/controlactivosti && /var/www/controlactivosti/.venv/bin/python manage.py purge_old_notifications --batch-size 1000 >> /var/log/controlactivosti/purge-notifications.log 2>&1
```

Alternativamente se puede ejecutar el mismo comando desde un `systemd timer`.
