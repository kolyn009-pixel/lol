#!/bin/sh
set -eu
APP_DIR="${1:-/opt/tutorbot}"
cd "$APP_DIR"
PYTHON="$APP_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3

echo "=== CURRENT ==="
printf "branch: %s\n" "$(git branch --show-current)"
printf "head:   %s\n" "$(git rev-parse HEAD)"
printf "dirty:  %s\n" "$(git status --porcelain | wc -l | tr -d ' ')"

echo "=== RELEASE REF ==="
git fetch origin release/adelia-unified-rc >/dev/null 2>&1 || true
printf "release: %s\n" "$(git rev-parse origin/release/adelia-unified-rc)"

echo "=== COMPILE ==="
"$PYTHON" -m compileall -q core integrations handlers final_features web_backend vk_adapter scripts

echo "=== IMPORTS ==="
"$PYTHON" - <<'PY'
mods=['core.payment_sync_runtime','core.schedule_sync','handlers.calendar_runtime','integrations.google_calendar','integrations.lesson_sync','final_features.jobs','web_backend.api_v6','web_backend.finance_receipts','web_backend.student_auth']
for name in mods:
    __import__(name)
    print('OK',name)
PY

echo "=== INTEGRATIONS ==="
"$PYTHON" scripts/integration_selftest.py

echo "=== WORKER FILES ==="
test -f web_backend/receipt_archive_worker.py
test -f web_backend/adelia-receipt-archive.service
echo "OK receipt archive files"

echo "=== RESULT ==="
echo "READ_ONLY_RELEASE_CHECK_PASSED"
echo "No checkout, reset, restart, migration or database write was performed by this script."
