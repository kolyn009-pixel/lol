#!/usr/bin/env bash
set -euo pipefail

# Run on the Adelia Ubuntu host from the repository root, after connecting from Mac.
# Required: ADELIA_SERVICE, ADELIA_DB_PATH, ADELIA_HEALTH_URL.
# Optional: ADELIA_REF (default release branch), ADELIA_BACKUP_DIR.

MODE="${1:-inspect}"
if [[ "$MODE" != inspect && "$MODE" != deploy ]]; then
  echo 'Usage: bash adelia_release.sh inspect|deploy' >&2
  exit 2
fi
: "${ADELIA_SERVICE:?Set the exact Adelia systemd service name}"
: "${ADELIA_DB_PATH:?Set the exact SQLite path used by the service}"
: "${ADELIA_HEALTH_URL:?Set the local Adelia /api/health URL}"
ADELIA_REF="${ADELIA_REF:-release/adelia-unified-rc}"
ADELIA_BACKUP_DIR="${ADELIA_BACKUP_DIR:-$HOME/adelia-release-backups}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

case "$ADELIA_SERVICE" in *[!a-zA-Z0-9_.@-]*|'') echo 'Invalid service name' >&2; exit 2;; esac
case "$ADELIA_HEALTH_URL" in http://127.0.0.1:*/api/health|http://localhost:*/api/health) ;; *) echo 'Use a local /api/health URL' >&2; exit 2;; esac
[[ -f "$ADELIA_DB_PATH" && -r "$ADELIA_DB_PATH" ]] || { echo 'Database is not readable' >&2; exit 2; }
systemctl cat "$ADELIA_SERVICE" >/dev/null
[[ -z "$(git status --porcelain)" ]] || { echo 'Working tree is not clean; stopping' >&2; exit 2; }
current="$(git rev-parse HEAD)"
printf 'Repository: %s\nCurrent commit: %s\nService: %s (%s)\nDatabase: %s\n' "$ROOT" "$current" "$ADELIA_SERVICE" "$(systemctl is-active "$ADELIA_SERVICE" || true)" "$ADELIA_DB_PATH"
curl --fail --silent --show-error --max-time 8 "$ADELIA_HEALTH_URL"
printf '\n'
if [[ "$MODE" == inspect ]]; then
  printf 'Read-only preflight complete. No files or services changed.\n'
  exit 0
fi

[[ "${ADELIA_DEPLOY_CONFIRM:-}" == YES ]] || { echo 'Set ADELIA_DEPLOY_CONFIRM=YES for deploy' >&2; exit 2; }
[[ "${ADELIA_WEB_SERVICE_VERIFIED:-}" == YES ]] || { echo 'Verify that the selected service owns the web API, then set ADELIA_WEB_SERVICE_VERIFIED=YES' >&2; exit 2; }
git fetch --no-tags origin "$ADELIA_REF"
target="$(git rev-parse FETCH_HEAD^{commit})"
git merge-base --is-ancestor "$current" "$target" || { echo 'Target is not a fast-forward of this checkout' >&2; exit 2; }
[[ "$current" != "$target" ]] || { echo 'Already at target commit'; exit 0; }
printf 'Target commit: %s\n' "$target"

# SQLite online backup includes committed WAL transactions. Never copy only the .db file.
umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="$ADELIA_BACKUP_DIR/$stamp"
mkdir -p "$backup"
printf '%s\n' "$current" > "$backup/previous-commit.txt"
printf '%s\n' "$target" > "$backup/target-commit.txt"
python3 - "$ADELIA_DB_PATH" "$backup/adelia.sqlite3" <<'PY'
import sqlite3, sys
from pathlib import Path
source, destination = Path(sys.argv[1]), Path(sys.argv[2])
with sqlite3.connect(f'file:{source}?mode=ro', uri=True, timeout=30) as src:
    with sqlite3.connect(destination) as dst:
        src.backup(dst)
destination.chmod(0o600)
with sqlite3.connect(f'file:{destination}?mode=ro', uri=True) as db:
    assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
print(f'Verified SQLite backup: {destination}')
PY

echo "Backup: $backup"
git merge --ff-only "$target"
if ! sudo systemctl restart "$ADELIA_SERVICE"; then
  echo 'Service restart failed; restoring previous code' >&2
  git reset --hard "$current"
  sudo systemctl restart "$ADELIA_SERVICE" || true
  exit 1
fi

healthy=0
for attempt in 1 2 3 4 5; do
  if curl --fail --silent --show-error --max-time 8 "$ADELIA_HEALTH_URL" >/dev/null; then healthy=1; break; fi
  sleep 2
done
if [[ "$healthy" != 1 ]]; then
  echo 'Health check failed; restoring previous code. Database backup is retained.' >&2
  git reset --hard "$current"
  sudo systemctl restart "$ADELIA_SERVICE" || true
  exit 1
fi
printf 'Adelia running at %s. Backup: %s\n' "$target" "$backup"
