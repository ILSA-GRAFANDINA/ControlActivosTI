# Despliegue de ControlActivosTI en Ubuntu Server 24.04 LTS

Para desplegar la estructura de atributos configurables, revise primero `docs/ATRIBUTOS_CONFIGURABLES_DESPLIEGUE.md`.

La arquitectura de producción es Apache2 → Gunicorn en `127.0.0.1:8000` → Django → PostgreSQL. El puerto 8000 y PostgreSQL no deben publicarse en la red. Las facturas permanecen en almacenamiento privado y solo Django las entrega después de validar permisos. Apache sirve los estáticos; `/media/` se reenvía a Django deliberadamente porque la aplicación protege fotografías por sesión y no debe publicar actas ni documentos mediante un Alias.

## 1. Paquetes, usuario y directorios

Ubuntu 24.04 incluye Python 3.12, compatible con las dependencias fijadas. Instale:

```bash
sudo apt update
sudo apt install -y apache2 postgresql postgresql-client python3 python3-venv \
  python3-dev build-essential libpq-dev libjpeg-dev zlib1g-dev rsync
sudo adduser --system --group --home /opt/controlactivosti \
  --no-create-home controlactivos
sudo install -d -o root -g controlactivos -m 0750 \
  /opt/controlactivosti /opt/controlactivosti/app /etc/controlactivosti
sudo install -d -o controlactivos -g www-data -m 0750 \
  /var/www/controlactivosti/media /var/www/controlactivosti/private \
  /var/log/controlactivosti
sudo install -d -o root -g www-data -m 0755 /var/www/controlactivosti/static
```

`ghostscript` no es necesario: la validación y optimización de PDF se realiza con `pypdf`. Puede usar `sudo bash install_ubuntu.sh` desde una copia del repositorio para automatizar paquetes, copia, entorno virtual y configuración base. El script conserva el archivo de entorno y pide confirmación si ya existe el destino.

## 2. Código y entorno virtual

Clone o copie el repositorio a `/opt/controlactivosti/app` sin incluir `.env`, `.venv`, `media`, `private_media`, `staticfiles` ni logs. Luego:

```bash
sudo chown -R root:controlactivos /opt/controlactivosti/app
sudo find /opt/controlactivosti/app -type d -exec chmod 0750 {} \;
sudo find /opt/controlactivosti/app -type f -exec chmod 0640 {} \;
sudo python3 -m venv /opt/controlactivosti/venv
sudo /opt/controlactivosti/venv/bin/pip install --upgrade pip
sudo /opt/controlactivosti/venv/bin/pip install -r /opt/controlactivosti/app/requirements.txt
sudo chown -R root:controlactivos /opt/controlactivosti/venv
sudo chmod -R g+rX,o-rwx /opt/controlactivosti/venv
```

Apache (`www-data`) puede leer los estáticos; no puede modificar el código. `controlactivos` escribe únicamente media, facturas privadas y logs. Los permisos de grupo sobre media permiten una futura estrategia de entrega interna con `X-Sendfile`, pero la configuración inicial mantiene el control de acceso en Django.

## 3. PostgreSQL

Elija valores propios en lugar de los marcadores:

```bash
sudo -u postgres psql
CREATE ROLE controlactivos_app LOGIN PASSWORD 'REEMPLAZAR_CON_CLAVE_SEGURA'
  NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE controlactivos OWNER controlactivos_app ENCODING 'UTF8';
\connect controlactivos
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO controlactivos_app;
\q
```

La aplicación solo lee `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` y `DB_PORT`. No cambie ni elimine migraciones existentes.

## 4. Variables de entorno

```bash
sudo install -o root -g controlactivos -m 0640 \
  /opt/controlactivosti/app/.env.example \
  /etc/controlactivosti/controlactivosti.env
sudo editor /etc/controlactivosti/controlactivosti.env
```

Genere `SECRET_KEY` sin guardarla en el historial:

```bash
/opt/controlactivosti/venv/bin/python -c \
  'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Configure `APP_ENV=production`, `DEBUG=False`, la base, y la IP o dominio en `ALLOWED_HOSTS`. `CSRF_TRUSTED_ORIGINS` requiere orígenes completos, por ejemplo `http://192.0.2.10` o posteriormente `https://activos.interno.example`. Para varios valores use comas. No coloque comillas de shell ni comentarios al final de una asignación.

## 5. Migración desde el servidor actual

Antes del corte detenga escrituras en el sistema anterior. Exporte PostgreSQL:

```bash
pg_dump -h HOST_ACTUAL -U USUARIO_ACTUAL -Fc -f controlactivos.dump BASE_ACTUAL
```

Copie el archivo de forma segura a Ubuntu y restaure sobre la base vacía:

```bash
sudo -u postgres pg_restore --clean --if-exists --no-owner \
  --role=controlactivos_app --dbname=controlactivos controlactivos.dump
sudo -u postgres psql -d controlactivos \
  -c 'GRANT USAGE, CREATE ON SCHEMA public TO controlactivos_app;'
```

Si la base destino ya contiene información, tome un respaldo y revise primero `pg_restore --list`; no use `--clean` sin una ventana de migración aprobada. Después ejecute `migrate`, que aplica únicamente migraciones pendientes y conserva datos.

Transfiera archivos preservando subdirectorios:

```bash
sudo rsync -a --chown=controlactivos:www-data /origen/media/ \
  /var/www/controlactivosti/media/
sudo rsync -a --chown=controlactivos:controlactivos /origen/private_media/ \
  /var/www/controlactivosti/private/
sudo find /var/www/controlactivosti/media -type d -exec chmod 0750 {} \;
sudo find /var/www/controlactivosti/media -type f -exec chmod 0640 {} \;
sudo chmod -R o-rwx /var/www/controlactivosti/private
```

`private_media` contiene facturas; nunca cree un Alias de Apache hacia ese directorio.

## 6. Validación Django y preparación

Los comandos de administración necesitan el entorno externo:

```bash
sudo -u controlactivos bash -c \
  'set -a; source /etc/controlactivosti/controlactivosti.env; set +a; \
  cd /opt/controlactivosti/app; \
  /opt/controlactivosti/venv/bin/python manage.py check; \
  /opt/controlactivosti/venv/bin/python manage.py check --deploy; \
  /opt/controlactivosti/venv/bin/python manage.py makemigrations --check --dry-run; \
  /opt/controlactivosti/venv/bin/python manage.py migrate --noinput; \
  /opt/controlactivosti/venv/bin/python manage.py collectstatic --noinput'
sudo chown -R root:www-data /var/www/controlactivosti/static
sudo chmod -R u=rwX,g=rX,o=rX /var/www/controlactivosti/static
```

Prueba temporal de Gunicorn (finalice con Ctrl+C):

```bash
sudo -u controlactivos bash -c \
  'set -a; source /etc/controlactivosti/controlactivosti.env; set +a; \
  cd /opt/controlactivosti/app; \
  /opt/controlactivosti/venv/bin/gunicorn config.wsgi:application \
  --bind 127.0.0.1:8000 --workers 2 --access-logfile - --error-logfile -'
curl -I http://127.0.0.1:8000/
```

## 7. systemd

El servicio usa 5 workers para 4 vCPU/8 GB, escucha solo en loopback, carga `/etc/controlactivosti/controlactivosti.env`, espera red y PostgreSQL y envía salida a journald.

```bash
sudo install -m 0644 deploy/systemd/controlactivosti.service \
  /etc/systemd/system/controlactivosti.service
sudo systemd-analyze verify /etc/systemd/system/controlactivosti.service
sudo systemctl daemon-reload
sudo systemctl enable --now postgresql apache2 controlactivosti
sudo systemctl status controlactivosti
sudo systemctl restart controlactivosti
sudo systemctl stop controlactivosti
sudo systemctl start controlactivosti
```

Logs:

```bash
sudo journalctl -u controlactivosti -f
sudo journalctl -u postgresql --since today
sudo tail -f /var/log/controlactivosti/application.log
```

Django rota `application.log`; Gunicorn queda en journald. La plantilla `deploy/logrotate/controlactivosti` cubre otros `.log` futuros.

## 8. Apache2

```bash
sudo a2enmod proxy proxy_http headers
sudo install -m 0644 deploy/apache/controlactivosti.conf \
  /etc/apache2/sites-available/controlactivosti.conf
sudo a2ensite controlactivosti.conf
sudo a2dissite 000-default.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Cambie `ServerName _` por la IP o el dominio cuando se defina. El límite HTTP es 20 MiB; Django limita cada factura a 15 MiB. Para HTTPS cree un VirtualHost 443, configure certificado, envíe `X-Forwarded-Proto https`, añada el origen HTTPS y active `ENABLE_HTTPS=True`. No abra 8000 ni 5432:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Apache Full'
sudo ufw enable
```

Errores y accesos Apache:

```bash
sudo tail -f /var/log/apache2/controlactivosti-error.log
sudo tail -f /var/log/apache2/controlactivosti-access.log
```

## 9. Respaldos

Instale el script y prográmelo una sola vez, por ejemplo diariamente con cron:

```bash
sudo install -m 0750 -o root -g root deploy/backup_controlactivosti.sh \
  /usr/local/sbin/backup_controlactivosti
sudo crontab -e
```

Entrada sugerida: `15 2 * * * BACKUP_ROOT=/var/backups/controlactivosti /usr/local/sbin/backup_controlactivosti`. Respalda `pg_dump`, media pública, facturas privadas, configuración y sumas SHA-256. Proteja `/var/backups/controlactivosti`, aplique retención conforme a su política y copie después al NAS con credenciales administradas fuera del repositorio. No se detectaron tareas programadas Windows ni procesos periódicos funcionales que deban migrarse.

## 10. Prueba de aceptación y reinicio

Desde otra computadora abra `http://IP_DEL_SERVIDOR/`. Con usuarios de prueba y permisos representativos verifique: inicio/cierre de sesión; permisos; alta, edición, consulta y baja controlada de activos; proveedores; fotografías y documentos; carga/descarga de PDF; una factura asociada a varios activos; actas; reportes y exportaciones. Revise que una factura sin permiso no sea accesible por URL.

Reinicie la VM en una ventana autorizada:

```bash
sudo reboot
# después:
systemctl is-active postgresql controlactivosti apache2
ss -lntp | grep -E ':(80|443|8000|5432)\b'
curl -I http://127.0.0.1/
```

Confirme que 8000 y 5432 aparecen únicamente en loopback y que la aplicación responde desde la LAN. Las validaciones de Apache, systemd, arranque tras reinicio y acceso desde otra máquina deben ejecutarse en Ubuntu; no pueden certificarse desde un equipo Windows.
