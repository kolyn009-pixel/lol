#!/bin/sh
set -eu
APP_DIR="${1:-$(pwd)}"
BACKUP_ROOT="${APP_DIR}/deploy_backups"
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_ROOT/$STAMP"
cp -a "$APP_DIR"/*.py "$BACKUP_ROOT/$STAMP/" 2>/dev/null || true
[ -f "$APP_DIR/tutor.db" ] && cp -a "$APP_DIR/tutor.db" "$BACKUP_ROOT/$STAMP/tutor.db"
[ -f "$APP_DIR/token.json" ] && cp -a "$APP_DIR/token.json" "$BACKUP_ROOT/$STAMP/token.json"
[ -f "$APP_DIR/credentials.json" ] && cp -a "$APP_DIR/credentials.json" "$BACKUP_ROOT/$STAMP/credentials.json"
echo "Backup: $BACKUP_ROOT/$STAMP"
python3 "$APP_DIR/core/post_update_check.py"
echo "Post-update checks passed"
