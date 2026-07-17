#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/controlactivosti}"
ENV_FILE="${ENV_FILE:-/etc/controlactivosti/controlactivosti.env}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_ROOT}/${STAMP}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: ejecute este script como root." >&2
  exit 1
fi
if [[ ! -r "${ENV_FILE}" ]]; then
  echo "ERROR: no se puede leer ${ENV_FILE}." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
: "${DB_NAME:?Falta DB_NAME}"
: "${DB_USER:?Falta DB_USER}"
: "${DB_HOST:?Falta DB_HOST}"
: "${DB_PORT:?Falta DB_PORT}"

install -d -m 0750 "${DEST}"
PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
  --host="${DB_HOST}" --port="${DB_PORT}" --username="${DB_USER}" \
  --format=custom --file="${DEST}/database.dump" "${DB_NAME}"
tar --create --gzip --file="${DEST}/media.tar.gz" -C /var/www/controlactivosti media private
install -m 0600 "${ENV_FILE}" "${DEST}/controlactivosti.env"
sha256sum "${DEST}/database.dump" "${DEST}/media.tar.gz" "${DEST}/controlactivosti.env" > "${DEST}/SHA256SUMS"
echo "Respaldo creado en ${DEST}. Cópielo al NAS mediante el mecanismo autorizado."
