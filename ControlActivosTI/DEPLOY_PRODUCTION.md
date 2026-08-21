# Despliegue En Produccion

Guia rapida para desplegar cambios de ControlActivosTI en el servidor Ubuntu de produccion.

## Rutas

Repo temporal actualizado:

```bash
/tmp/ControlActivosTI
```

Aplicacion productiva:

```bash
/opt/controlactivosti/app
```

Entorno virtual productivo:

```bash
/opt/controlactivosti/venv
```

Servicio systemd:

```bash
controlactivosti
```

Base de datos productiva:

```bash
controlactivos
```

## Regla Importante

No copiar, restaurar ni reemplazar la base de datos de produccion con una base de desarrollo.

En produccion solo se deben aplicar cambios de estructura mediante:

```bash
python manage.py migrate
```

## 1. Entrar Al Repo

```bash
cd /tmp/ControlActivosTI
git status
git pull origin main
```

## 2. Crear Backups

```bash
sudo mkdir -p /opt/controlactivosti/backups
```

Backup de base de datos:

```bash
sudo -u postgres pg_dump -Fc controlactivos > /opt/controlactivosti/backups/controlactivos_$(date +%Y%m%d_%H%M%S).dump
```

Backup del codigo actual en produccion:

```bash
sudo tar -czf /opt/controlactivosti/backups/app_$(date +%Y%m%d_%H%M%S).tar.gz /opt/controlactivosti/app
```

## 3. Copiar Codigo A Produccion

```bash
sudo rsync -av --delete \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='media' \
  --exclude='private_media' \
  --exclude='staticfiles' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.sqlite3' \
  --exclude='*.log' \
  /tmp/ControlActivosTI/ControlActivosTI/ \
  /opt/controlactivosti/app/
```

## 4. Activar Entorno Productivo

```bash
cd /opt/controlactivosti/app
source /opt/controlactivosti/venv/bin/activate
```

## 5. Instalar Dependencias

Ejecutar solo si cambio `requirements.txt`:

```bash
pip install -r requirements.txt
```

## 6. Validar Proyecto

```bash
python manage.py check
```

## 7. Aplicar Migraciones

```bash
python manage.py migrate
```

## 8. Recolectar Archivos Estaticos

```bash
python manage.py collectstatic --noinput
```

## 9. Corregir Permisos

```bash
sudo chown -R root:controlactivos /opt/controlactivosti/app
sudo find /opt/controlactivosti/app -type d -exec chmod 750 {} \;
sudo find /opt/controlactivosti/app -type f -exec chmod 640 {} \;
```

## 10. Reiniciar Servicio

```bash
sudo systemctl restart controlactivosti
sudo systemctl status controlactivosti
```

## 11. Revisar Logs

```bash
sudo journalctl -u controlactivosti -n 80 --no-pager
```

## 12. Probar Respuesta Local

```bash
curl -I http://127.0.0.1:8000
```

Si responde `302`, normalmente esta redirigiendo al login y la aplicacion esta levantada.

## Flujo Completo Rapido

```bash
cd /tmp/ControlActivosTI
git status
git pull origin main

sudo mkdir -p /opt/controlactivosti/backups
sudo -u postgres pg_dump -Fc controlactivos > /opt/controlactivosti/backups/controlactivos_$(date +%Y%m%d_%H%M%S).dump
sudo tar -czf /opt/controlactivosti/backups/app_$(date +%Y%m%d_%H%M%S).tar.gz /opt/controlactivosti/app

sudo rsync -av --delete \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='media' \
  --exclude='private_media' \
  --exclude='staticfiles' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.sqlite3' \
  --exclude='*.log' \
  /tmp/ControlActivosTI/ControlActivosTI/ \
  /opt/controlactivosti/app/

cd /opt/controlactivosti/app
source /opt/controlactivosti/venv/bin/activate

python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput

sudo chown -R root:controlactivos /opt/controlactivosti/app
sudo find /opt/controlactivosti/app -type d -exec chmod 750 {} \;
sudo find /opt/controlactivosti/app -type f -exec chmod 640 {} \;

sudo systemctl restart controlactivosti
sudo systemctl status controlactivosti
curl -I http://127.0.0.1:8000
```

## Si Algo Falla

Ver estado del servicio:

```bash
sudo systemctl status controlactivosti
```

Ver logs recientes:

```bash
sudo journalctl -u controlactivosti -n 120 --no-pager
```

Verificar Django:

```bash
cd /opt/controlactivosti/app
source /opt/controlactivosti/venv/bin/activate
python manage.py check
```

Ver migraciones pendientes:

```bash
python manage.py showmigrations
```
