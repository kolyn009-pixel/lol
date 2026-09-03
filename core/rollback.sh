#!/bin/sh
set -eu
APP_DIR="${1:-$(pwd)}"
BACKUP_ROOT="${APP_DIR}/deploy_backups"
BACKUP_DIR="${2:-}"
if [ -z "$BACKUP_DIR" ]; then
  BACKUP_DIR=$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort -r | head -1)
fi
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
  echo "Backup not found" >&2
  exit 1
fi
cp -a "$BACKUP_DIR"/*.py "$APP_DIR/" 2>/dev/null || true
[ -f "$BACKUP_DIR/tutor.db" ] && cp -a "$BACKUP_DIR/tutor.db" "$APP_DIR/tutor.db"
[ -f "$BACKUP_DIR/token.json" ] && cp -a "$BACKUP_DIR/token.json" "$APP_DIR/token.json"
[ -f "$BACKUP_DIR/credentials.json" ] && cp -a "$BACKUP_DIR/credentials.json" "$APP_DIR/credentials.json"
echo "Rolled back from: $BACKUP_DIR"
