# Produccion en Windows Server

## Arquitectura y carpetas

Apache `C:\Apache24` recibe `http://10.10.1.253`, sirve `/static/` y reenvia el resto a Waitress en `127.0.0.1:8000`. PostgreSQL 17 debe escuchar solo en localhost. Use una cuenta de servicio dedicada, sin inicio interactivo ni privilegios administrativos.

Mantenga releases de codigo separados de `D:\ControlActivosTI\static`, `media`, `private_media`, `logs` y `backups`. Conceda a la cuenta del servicio lectura del release, lectura/escritura en esas cinco carpetas y ningun permiso adicional.

## Preparacion

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `.env`: genere `SECRET_KEY`, configure el usuario PostgreSQL de aplicacion (sin SUPERUSER, CREATEDB ni CREATEROLE), contraseña, hosts y rutas. Cree la base UTF-8 y limite PostgreSQL a `127.0.0.1:5432`. No versione `.env`.

```powershell
.\.venv\Scripts\python.exe manage.py check --deploy
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
.\deploy\start-waitress.ps1
```

El comando equivalente exacto es:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 config.wsgi:application
```

Copie/adapte `deploy/apache/controlactivos.conf.example`, habilite `proxy_module`, `proxy_http_module`, `headers_module` y `rewrite_module`, valide con `C:\Apache24\bin\httpd.exe -t` y reinicie Apache. Abra en Firewall solo TCP/80 (y posteriormente 443); no abra 8000 ni 5432.

## Operacion, actualizacion y rollback

Antes de cada release respalde PostgreSQL con `pg_dump` y copie `media`/`private_media`. Despliegue un release nuevo, conserve el anterior, ejecute `deploy.ps1`, pruebe `/health/` y reinicie el servicio de forma controlada. En rollback restaure el release anterior; revierta base de datos solo desde un respaldo compatible. En produccion se ejecuta `migrate`, nunca `makemigrations`, y no se editan archivos del release manualmente.

Los logs de Django están en `LOG_DIR\application.log`; Apache usa sus logs separados. Diagnostico: `manage.py check --deploy`, `manage.py showmigrations`, `httpd.exe -t`, `Get-Service ControlActivosTI` e `Invoke-WebRequest http://127.0.0.1:8000/health/`.

Para HTTPS agregue el certificado y VirtualHost 443 en Apache, cambie `CSRF_TRUSTED_ORIGINS` a `https://...`, haga que Apache envie `X-Forwarded-Proto https` y solo entonces establezca `ENABLE_HTTPS=True`. Agregue DNS a `ALLOWED_HOSTS` sin cambiar código.
