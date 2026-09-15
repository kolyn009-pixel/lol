#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tutorbot}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
ENV_FILE="${ENV_FILE:-/etc/tutorbot/adelia.env}"
START_NOW="${START_NOW:-1}"

require_file(){
  [ -f "$1" ] || { echo "ERROR: missing $1" >&2; exit 2; }
}

env_has(){
  key="$1"
  [ -f "$ENV_FILE" ] && grep -q "^${key}=." "$ENV_FILE"
}

[ "$(id -u)" -eq