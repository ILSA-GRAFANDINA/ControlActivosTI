# Depreciación automática

El módulo calcula automáticamente la depreciación tomando:

- costo: `Activo.valor`;
- fecha de inicio: `Activo.fecha_compra`;
- valor residual: cero;
- vida útil: 36 meses;
- método: línea recta.

No existe una ficha adicional que deba llenarse. Si el activo no tiene fecha o
valor de compra, se muestra como pendiente de información hasta corregir su ficha.

En `admin2 > Inventario > Configurar alertas` únicamente se administran:

- meses de anticipación de la primera alerta (3 por defecto);
- frecuencia de recordatorios posteriores (6 meses por defecto).

La depreciación es una estimación interna y no cambia el estado operativo, las
asignaciones ni genera movimientos contables.

## Despliegue en Ubuntu

1. Respaldar PostgreSQL:
   `pg_dump -Fc -d controlactivos_prod -f /ruta-segura/controlactivos_YYYYMMDD.dump`.
2. Revisar `python manage.py migrate --plan`.
3. Instalar dependencias: `pip install -r requirements.txt`.
4. Ejecutar primero en desarrollo:
   `python manage.py migrate` y `python manage.py test apps.depreciacion`.
5. Aplicar en producción: `python manage.py migrate`.
6. Validar sin escrituras:
   `python manage.py check_asset_depreciation --dry-run`.
7. Instalar los archivos `controlactivosti-depreciation.service` y
   `controlactivosti-depreciation.timer` de `deploy/systemd/`.
8. Ejecutar:
   `sudo systemctl daemon-reload` y
   `sudo systemctl enable --now controlactivosti-depreciation.timer`.

El timer se ejecuta diariamente. La tarea es idempotente y, si hubo una
interrupción prolongada, crea únicamente el aviso vencido más reciente.

## Reversión

1. Desactivar el timer:
   `sudo systemctl disable --now controlactivosti-depreciation.timer`.
2. Revertir el código.
3. No revertir las tablas de eventos si ya contienen notificaciones sin revisar
   primero la trazabilidad.
4. Ante una reversión total aprobada, restaurar el respaldo en una base nueva y
   validarla antes de cambiar la conexión. Nunca usar una base de desarrollo para
   sobrescribir producción.
