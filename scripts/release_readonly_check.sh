#!/bin/sh
set -eu
APP_DIR="${1:-/opt/tutorbot}"
cd "$APP_DIR"
PYTHON="$APP_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3
TMP="${TMPDIR:-/tmp}/adelia-release-check-$$"
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT INT TERM

echo "=== PRODUCTION STATE ==="
printf "branch: %s\n" "$(git branch --show-current)"
printf "head:   %s\n" "$(git rev-parse HEAD)"
printf "dirty:  %s\n" "$(git status --porcelain | wc -l | tr -d ' ')"

echo "=== RELEASE REF ==="
git fetch origin release/adelia-unified-rc >/dev/null
RELEASE_HEAD="$(git rev-parse origin/release/adelia-unified-rc)"
printf "release: %s\n" "$RELEASE_HEAD"

echo "=== ISOLATED ARCHIVE ==="
mkdir -p "$TMP"
git archive "$RELEASE_HEAD" | tar -x -C "$TMP"
cd "$TMP"
printf "check dir: %s\n" "$TMP"

echo "=== COMPILE RC ==="
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m compileall -q core integrations handlers final_features web_backend vk_adapter scripts

echo "=== IMPORT RC ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP" "$PYTHON" - <<'PY'
mods=['core.payment_sync_runtime','core.payment_reminder_routing','core.schedule_sync','handlers.calendar_runtime','integrations.google_calendar','integrations.lesson_sync','final_features.jobs','vk_adapter.notification_sync','web_backend.api_v6','web_backend.finance_receipts','web_backend.student_auth']
for name in mods:
    __import__(name)
    print('OK',name)
PY

echo "=== ROUTING SELFTEST ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP" "$PYTHON" scripts/payment_reminder_routing_selftest.py

echo "=== REQUIRED RC FILES ==="
for f in web_backend/receipt_archive_worker.py web_backend/adelia-receipt-archive.service scripts/integration_selftest.py scripts/load_probe.py scripts/payment_reminder_routing_selftest.py core/payment_sync_runtime.py core/payment_reminder_routing.py desktop/bundled_ui.js desktop/role_assets_manifest.js desktop/sync_role_assets.js web/manifest.webmanifest web/teacher-manifest.webmanifest web/service-worker.js web/assets/icons/adelia-icon.svg; do
  test -f "$f" || { echo "MISSING $f"; exit 20; }
  echo "OK $f"
done

echo "=== LIVE CREDENTIAL PROBE ==="
cd "$APP_DIR"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" scripts/integration_selftest.py

echo "=== RESULT ==="
echo "READ_ONLY_RELEASE_CHECK_PASSED"
echo "Production branch, working tree, services and database were not switched or migrated."
