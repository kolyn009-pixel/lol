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

env_has(){
  key="$1"
  [ -f "$ENV_FILE" ] && grep -q "^${key}=." "$ENV_FILE"
}

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root" >&2; exit 1; }
require_file "$APP_DIR/web_backend/adelia-receipt-archive.service"
require_file "$APP_DIR/web_backend/receipt_archive_worker.py"
require_file "$APP_DIR/web_backend/telemost_precreate_worker.py"
require_file "$APP_DIR/venv/bin/python"
require_env YANDEX_DISK_OAUTH_TOKEN

install -m 0644 \
  "$APP_DIR/web_backend/adelia-receipt-archive.service" \
  "$SYSTEMD_DIR/adelia-receipt-archive.service"

telemost_installed=0
if env_has YANDEX_TELEMOST_OAUTH_TOKEN && grep -q '^YANDEX_TELEMOST_ENABLED=1$' "$ENV_FILE"; then
  cat > "$SYSTEMD_DIR/adelia-telemost-precreate.service" <<EOF
[Unit]
Description=Adelia Telemost Precreate Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=$APP_DIR/venv/bin/python -m web_backend.telemost_precreate_worker
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
  chmod 0644 "$SYSTEMD_DIR/adelia-telemost-precreate.service"
  telemost_installed=1
else
  echo "Telemost precreate worker skipped: set YANDEX_TELEMOST_ENABLED=1 and YANDEX_TELEMOST_OAUTH_TOKEN in $ENV_FILE"
fi

systemctl daemon-reload
systemctl enable adelia-receipt-archive.service >/dev/null
if [ "$telemost_installed" = "1" ]; then
  systemctl enable adelia-telemost-precreate.service >/dev/null
fi

if [ "$START_NOW" = "1" ]; then
  systemctl restart adelia-receipt-archive.service
  if [ "$telemost_installed" = "1" ]; then
    systemctl restart adelia-telemost-precreate.service
  fi
fi

state="$(systemctl is-active adelia-receipt-archive.service 2>/dev/null || true)"
enabled="$(systemctl is-enabled adelia-receipt-archive.service 2>/dev/null || true)"
printf 'adelia-receipt-archive.service active=%s enabled=%s\n' "$state" "$enabled"

if [ "$START_NOW" = "1" ] && [ "$state" != "active" ]; then
  echo "ERROR: receipt archive service did not start" >&2
  systemctl --no-pager --full status adelia-receipt-archive.service || true
  exit 4
fi

if [ "$telemost_installed" = "1" ]; then
  tstate="$(systemctl is-active adelia-telemost-precreate.service 2>/dev/null || true)"
  tenabled="$(systemctl is-enabled adelia-telemost-precreate.service 2>/dev/null || true)"
  printf 'adelia-telemost-precreate.service active=%s enabled=%s\n' "$tstate" "$tenabled"
  if [ "$START_NOW" = "1" ] && [ "$tstate" != "active" ]; then
    echo "ERROR: Telemost precreate service did not start" >&2
    systemctl --no-pager --full status adelia-telemost-precreate.service || true
    exit 5
  fi
fi

echo "Auxiliary worker installation complete."
