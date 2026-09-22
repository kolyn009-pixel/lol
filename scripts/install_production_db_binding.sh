#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${ADELIA_DB_PATH:-/opt/tutorbot/tutor.db}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

SERVICES=(
  tutorbot.service
  tutorbot-vk.service
  tutorbot-web.service
  adelia-homework-delivery.service
  adelia-receipt-archive.service
  adelia-telemost-precreate.service
)

[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root" >&2; exit 2; }
[ -f "$DB_PATH" ] || { echo "ERROR: canonical DB missing: $DB_PATH" >&2; exit 3; }

python3 - "$DB_PATH" <<'PY'
import sqlite3, sys
p=sys.argv[1]
c=sqlite3.connect(f"file:{p}?mode=ro", uri=True)
try:
    result=c.execute("PRAGMA integrity_check").fetchone()[0]
    if str(result).lower()!="ok":
        raise SystemExit(f"ERROR: integrity_check={result}")
    required={"users","bot_settings","regular_schedules","working_hours"}
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing=sorted(required-tables)
    if missing:
        raise SystemExit("ERROR: canonical DB missing tables: "+",".join(missing))
    print("CANONICAL_DB_CHECK=OK")
finally:
    c.close()
PY

for service in "${SERVICES[@]}"; do
  mkdir -p "$SYSTEMD_DIR/$service.d"
  cat > "$SYSTEMD_DIR/$service.d/20-adelia-database.conf" <<EOF
[Service]
Environment=ADELIA_DB_PATH=$DB_PATH
EOF
  echo "BOUND $service -> $DB_PATH"
done

systemctl daemon-reload

echo "ADELIA_DB_BINDING_INSTALLED=YES"
echo "ADELIA_DB_PATH=$DB_PATH"
echo "NOTE=services_not_restarted"
