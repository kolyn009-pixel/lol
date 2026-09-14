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
mods=[
 'core.payment_sync_runtime','core.payment_reminder_routing','core.schedule_sync',
 'handlers.calendar_runtime','integrations.google_calendar','integrations.lesson_sync',
 'final_features.jobs','vk_adapter.notification_sync','web_backend.api_v6',
 'web_backend.finance_receipts','web_backend.student_auth','web_backend.atomic_student_booking',
 'web_backend.student_regular_booking','web_backend.teacher_request_center',
 'web_backend.trial_approval_atomic'
]
for name in mods:
    __import__(name)
    print('OK',name)
PY

echo "=== ROUTING SELFTEST ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP" "$PYTHON" scripts/payment_reminder_routing_selftest.py

echo "=== BOOKING SELFTEST ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP" "$PYTHON" scripts/booking_release_selftest.py

echo "=== PWA MANIFESTS ==="
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - <<'PY'
import json
for path, expected in [
    ('web/manifest.webmanifest','/app/'),
    ('web/teacher-manifest.webmanifest','/teacher/'),
]:
    with open(path,'r',encoding='utf-8') as fh:
        data=json.load(fh)
    assert data.get('display') == 'standalone', (path,'display')
    assert data.get('start_url') == expected, (path,'start_url',data.get('start_url'))
    assert data.get('icons'), (path,'icons')
    print('OK',path,data.get('start_url'))
PY

echo "=== REQUIRED RC FILES ==="
for f in \
  web_backend/receipt_archive_worker.py \
  web_backend/adelia-receipt-archive.service \
  scripts/integration_selftest.py \
  scripts/load_probe.py \
  scripts/payment_reminder_routing_selftest.py \
  scripts/booking_release_selftest.py \
  core/payment_sync_runtime.py \
  core/payment_reminder_routing.py \
  web_backend/atomic_student_booking.py \
  web_backend/student_regular_booking.py \
  web_backend/trial_approval_atomic.py \
  desktop/bundled_ui.js \
  desktop/bundled_ui_manifest.js \
  desktop/sync_role_assets.js \
  web/manifest.webmanifest \
  web/teacher-manifest.webmanifest \
  web/service-worker.js \
  web/student_booking_ui.js \
  web/teacher_request_center.js \
  web/assets/icons/adelia-icon.svg; do
  test -f "$f" || { echo "MISSING $f"; exit 20; }
  echo "OK $f"
done

echo "=== LIVE CREDENTIAL PROBE USING RC CODE ==="
cd "$APP_DIR"

# Validate the real production Google grant without allowing RC code to
# refresh/write the production token. google_calendar.py persists refreshed
# credentials to GOOGLE_CALENDAR_TOKEN_FILE, so the release gate operates on
# a private temporary copy.
PROD_GOOGLE_TOKEN="${GOOGLE_CALENDAR_TOKEN_FILE:-$APP_DIR/token.json}"
PROD_GOOGLE_CREDENTIALS="${GOOGLE_CALENDAR_CREDENTIALS_FILE:-$APP_DIR/credentials.json}"
PROD_GOOGLE_CALENDAR_ID="${GOOGLE_CALENDAR_ID:-primary}"
CHECK_GOOGLE_TOKEN="$TMP/.production-google-token.json"

test -f "$PROD_GOOGLE_TOKEN" || {
  echo "MISSING production Google token: $PROD_GOOGLE_TOKEN"
  exit 21
}

cp "$PROD_GOOGLE_TOKEN" "$CHECK_GOOGLE_TOKEN"
chmod 600 "$CHECK_GOOGLE_TOKEN"

PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$TMP" \
GOOGLE_CALENDAR_TOKEN_FILE="$CHECK_GOOGLE_TOKEN" \
GOOGLE_CALENDAR_CREDENTIALS_FILE="$PROD_GOOGLE_CREDENTIALS" \
GOOGLE_CALENDAR_ID="$PROD_GOOGLE_CALENDAR_ID" \
"$PYTHON" "$TMP/scripts/integration_selftest.py"

echo "=== RESULT ==="
echo "READ_ONLY_RELEASE_CHECK_PASSED"
echo "Production branch, working tree, services and database were not switched or migrated."
