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
import re
import sys

p = Path(sys.argv[1])
s = p.read_text()

block = """    # Teacher cabinet canonical shortcut
    location = /teacher {
        return 302 /app/teacher.html;
    }

    location = /teacher/ {
        return 302 /app/teacher.html;
    }

"""

teacher_re = re.compile(
    r"(?ms)^\s*# Teacher cabinet canonical shortcut\s*$"
    r".*?"
    r"(?=^\s*(?:# Adelia student / parent application\s*$|location\s*=\s*/app\s*\{))"
)

if teacher_re.search(s):
    s = teacher_re.sub(block, s, count=1)
else:
    app_match = re.search(
        r"(?m)^\s*(?:# Adelia student / parent application\s*$|location\s*=\s*/app\s*\{)",
        s,
    )
    if not app_match:
        raise SystemExit("student application route not found")
    s = s[:app_match.start()] + block + s[app_match.start():]

p.write_text(s)
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
