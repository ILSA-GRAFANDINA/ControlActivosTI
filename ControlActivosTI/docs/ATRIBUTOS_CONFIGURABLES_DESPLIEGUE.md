# Despliegue de atributos configurables

Esta entrega es aditiva. No elimina `cpu`, `ram`, `disco` ni `sistema_operativo`, no reemplaza la base existente y no carga fixtures.

## Migraciones incluidas

- `catalogos.0006`: catálogo, opciones y configuración por tipo.
- `catalogos.0007`: atributos iniciales y asociación a tipos de cómputo existentes.
- `activos.0016`: valores tipados y permiso de cambio controlado de tipo.
- `actas.0007` y `0008`: instantánea, checksum y protección de actas existentes.
- `auditoria.0001`: auditoría de la nueva estructura.

## Respaldo obligatorio

1. Detener temporalmente las escrituras.
2. Ejecutar:

   ```bash
   sudo BACKUP_ROOT=/var/backups/controlactivosti /usr/local/sbin/backup_controlactivosti
   ```

3. Confirmar `database.dump`, `database.list`, `media.tar.gz`, el entorno y `SHA256SUMS`.
4. Validar:

   ```bash
   cd /var/backups/controlactivosti/AAAAMMDDTHHMMSSZ
   sha256sum --check SHA256SUMS
   pg_restore --list database.dump >/dev/null
   ```

5. Copiar el respaldo al almacenamiento externo autorizado.

## Prevalidación

En una copia de producción:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations --plan
python manage.py test
```

Registrar antes de migrar:

```sql
SELECT count(*) FROM activos_activo;
SELECT count(*) FROM asignaciones_asignacion;
SELECT count(*) FROM asignaciones_devolucion;
SELECT count(*) FROM actas_actaentrega;
SELECT count(*), count(DISTINCT codigo), count(DISTINCT serie) FROM activos_activo;
```

## Aplicación controlada

```bash
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py migrate_legacy_asset_attributes --dry-run
python manage.py migrate_legacy_asset_attributes
python manage.py migrate_legacy_asset_attributes --dry-run
```

La última simulación no debe necesitar crear valores nuevos. La RAM no interpretable queda marcada para revisión y conserva su texto original.

No ejecutar `flush`, `loaddata`, `DROP TABLE`, restauraciones desde Windows ni `pg_restore --clean` sobre producción.

## Validaciones posteriores

- Repetir los conteos SQL; activos, asignaciones, devoluciones y actas deben conservarse.
- Verificar códigos, series, SAP, proveedores y facturas.
- Revisar `SELECT count(*) FROM activos_valoratributoactivo WHERE requiere_revision = TRUE;`.
- Abrir un activo de cada tipo y comprobar detalle, edición, asignación y exportación.
- Descargar actas históricas y confirmar que no fueron regeneradas.
- Crear una asignación autorizada y revisar sus atributos de acta.
- Revisar `/admin/auditoria/registroauditoria/`.

## Reversión

La reversión segura es volver al código anterior y restaurar el respaldo validado. Si ya existen valores nuevos, no deben revertirse tablas individualmente.

1. Detener Gunicorn y bloquear escrituras.
2. Respaldar el estado fallido.
3. Restaurar `database.dump` primero en una base vacía de recuperación.
4. Validar conteos e integridad.
5. Realizar el cambio de base durante una ventana aprobada.
6. Restaurar medios, desplegar el código anterior y ejecutar `check`.

## Pruebas manuales

1. Crear atributos de texto, entero, decimal, fecha, booleano y lista.
2. Asociarlos, ordenarlos, marcarlos obligatorios y comprobar el límite.
3. Crear y editar un activo; provocar un error y verificar que conserva datos.
4. Desactivar un atributo usado y comprobar su valor histórico.
5. Intentar cambiar su clave o tipo de dato.
6. Probar cambio de tipo con y sin historial y permiso especial.
7. Buscar por un atributo filtrable y exportar uno marcado para reportes.
8. Generar actas sin vacíos ni atributos no autorizados.
9. Verificar que no se admiten atributos para contraseñas, tokens o secretos.
