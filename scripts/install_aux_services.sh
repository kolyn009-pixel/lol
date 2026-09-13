#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tutorbot}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
ENV_FILE="${ENV_FILE:-/etc/tutorbot/adelia.env}"
START_NOW="${START_NOW:-1}"

require_file(){
  [ -f "$1" ] || { echo "ERROR: missing $1" >&2; exit 2; }
}

require_env(){
  key="$1"
  if [ ! -f "$ENV_FILE" ] || ! grep -q "^${key}=." "$ENV_FILE"; then
    echo "ERROR: ${key} is missing from ${ENV_FILE}" >&2
    exit 3
  fi
}

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root" >&2; exit 1; }
require_file "$APP_DIR/web_backend/adelia-receipt-archive.service"
require_file "$APP_DIR/web_backend/receipt_archive_worker.py"
require_file "$APP_DIR/venv/bin/python"
require_env YANDEX_DISK_OAUTH_TOKEN

install -m 0644 \
  "$APP_DIR/web_backend/adelia-receipt-archive.service" \
  "$SYSTEMD_DIR/adelia-receipt-archive.service"

systemctl daemon-reload
systemctl enable adelia-receipt-archive.service >/dev/null

if [ "$START_NOW" = "1" ]; then
  systemctl restart adelia-receipt-archive.service
fi

state="$(systemctl is-active adelia-receipt-archive.service 2>/dev/null || true)"
enabled="$(systemctl is-enabled adelia-receipt-archive.service 2>/dev/null || true)"
printf 'adelia-receipt-archive.service active=%s enabled=%s\n' "$state" "$enabled"

if [ "$START_NOW" = "1" ] && [ "$state" != "active" ]; then
  echo "ERROR: receipt archive service did not start" >&2
  systemctl --no-pager --full status adelia-receipt-archive.service || true
  exit 4
fi

echo "Receipt archive worker installation complete."
