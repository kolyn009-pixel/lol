#!/usr/bin/env bash
set -euo pipefail

CONF="${1:-/etc/nginx/sites-enabled/adeliatutor.ru}"
BACKUP_DIR="${ADELIA_NGINX_BACKUP_DIR:-/root/nginx-backups}"
STAMP="$(date +%Y%m%d_%H%M%S)"

test -f "$CONF"
mkdir -p "$BACKUP_DIR"
cp "$CONF" "$BACKUP_DIR/adeliatutor.ru.$STAMP"

python3 - "$CONF" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
start = s.find("    # Teacher cabinet canonical shortcut")
if start < 0:
    raise SystemExit("teacher canonical marker not found")
app_marker = s.find("    # Adelia student / parent application", start)
if app_marker < 0:
    raise SystemExit("student application marker not found")
block = """    # Teacher cabinet canonical shortcut
    location = /teacher {
        return 302 /app/teacher.html;
    }

    location = /teacher/ {
        return 302 /app/teacher.html;
    }

"""
p.write_text(s[:start] + block + s[app_marker:])
PY

nginx -t
systemctl reload nginx

for path in /teacher /teacher/; do
  location="$(curl -fsSI "https://adeliatutor.ru$path" | awk 'BEGIN{IGNORECASE=1} /^Location:/{gsub("\r",""); print $2; exit}')"
  test "$location" = "https://adeliatutor.ru/app/teacher.html" || test "$location" = "/app/teacher.html"
  echo "$path -> $location"
done

live_hash="$(curl -fsSL https://adeliatutor.ru/teacher/ | sha256sum | awk '{print $1}')"
release_hash="$(sha256sum /opt/adelia-current/web/teacher.html | awk '{print $1}')"
test "$live_hash" = "$release_hash"
echo "TEACHER_CANONICAL_ROUTE=OK"
