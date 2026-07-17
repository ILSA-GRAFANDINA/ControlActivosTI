#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=/opt/controlactivosti
APP_DIR="${APP_ROOT}/app"
VENV="${APP_ROOT}/venv"
ENV_DIR=/etc/controlactivosti
WEB_ROOT=/var/www/controlactivosti
LOG_DIR=/var/log/controlactivosti
SERVICE_USER=controlactivos

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || die "Ejecute con sudo: sudo ./install_ubuntu.sh"
[[ -f manage.py && -f requirements.txt ]] || die "Ejecute desde la raíz del proyecto."

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  apache2 postgresql postgresql-client python3 python3-venv python3-dev \
  build-essential libpq-dev libjpeg-dev zlib1g-dev rsync

id "${SERVICE_USER}" >/dev/null 2>&1 || \
  useradd --system --home "${APP_ROOT}" --shell /usr/sbin/nologin "${SERVICE_USER}"

install -d -o root -g "${SERVICE_USER}" -m 0750 "${APP_ROOT}" "${ENV_DIR}"
install -d -o "${SERVICE_USER}" -g www-data -m 0750 \
  "${WEB_ROOT}/media" "${WEB_ROOT}/private" "${LOG_DIR}"
install -d -o root -g www-data -m 0755 "${WEB_ROOT}/static"

if [[ -e "${APP_DIR}" ]]; then
  read -r -p "${APP_DIR} ya existe. ¿Sincronizar el código sin borrar archivos ajenos? [s/N] " answer
  [[ "${answer,,}" == "s" ]] || die "Instalación cancelada sin modificar el código."
else
  install -d -o root -g "${SERVICE_USER}" -m 0750 "${APP_DIR}"
fi
rsync -a --exclude='.git' --exclude='.venv' --exclude='.env' \
  --exclude='media' --exclude='private_media' --exclude='staticfiles' ./ "${APP_DIR}/"
chown -R root:"${SERVICE_USER}" "${APP_DIR}"
find "${APP_DIR}" -type d -exec chmod 0750 {} +
find "${APP_DIR}" -type f -exec chmod 0640 {} +

if [[ ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/pip" install --upgrade pip
"${VENV}/bin/pip" install --requirement "${APP_DIR}/requirements.txt"
chown -R root:"${SERVICE_USER}" "${VENV}"
chmod -R g+rX,o-rwx "${VENV}"

if [[ ! -e "${ENV_DIR}/controlactivosti.env" ]]; then
  install -o root -g "${SERVICE_USER}" -m 0640 \
    "${APP_DIR}/.env.example" "${ENV_DIR}/controlactivosti.env"
  echo "IMPORTANTE: complete ${ENV_DIR}/controlactivosti.env antes de iniciar."
else
  echo "Se conservó ${ENV_DIR}/controlactivosti.env existente."
fi

install -o root -g root -m 0644 "${APP_DIR}/deploy/systemd/controlactivosti.service" \
  /etc/systemd/system/controlactivosti.service
install -o root -g root -m 0644 "${APP_DIR}/deploy/apache/controlactivosti.conf" \
  /etc/apache2/sites-available/controlactivosti.conf
install -o root -g root -m 0644 "${APP_DIR}/deploy/logrotate/controlactivosti" \
  /etc/logrotate.d/controlactivosti
a2enmod proxy proxy_http headers
a2ensite controlactivosti.conf
systemctl daemon-reload

echo "Archivos instalados. Configure PostgreSQL y el entorno; después siga DEPLOY_UBUNTU.md."
