#!/bin/sh
set -eu

APP_DIR="${1:-/opt/tutorbot}"
BRANCH="release/adelia-unified-rc"
PYTHON="$APP_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3
TMP="${TMPDIR:-/tmp}/adelia-final-rc-gate-$$"
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT INT TERM

cd "$APP_DIR"

echo "=== 1. FETCH RC ==="
git fetch origin "$BRANCH" >/dev/null
RC_HEAD="$(git rev-parse "origin/$BRANCH")"
printf "RC_HEAD=%s\n" "$RC_HEAD"

echo "=== 2. ISOLATED RC ARCHIVE ==="
mkdir -p "$TMP/rc"
git archive "$RC_HEAD" | tar -x -C "$TMP/rc"
printf "RC_DIR=%s\n" "$TMP/rc"

echo "=== 3. COMPILE ==="
cd "$TMP/rc"
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -m compileall -q core integrations handlers final_features web_backend vk_adapter scripts

echo "=== 4. IMPORT CHANGED CORE ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP/rc" "$PYTHON" - <<'PY'
mods=[
 'core.payment_wait_control',
 'core.schedule_sync',
 'final_features.slot_change',
 'web_backend.teacher_day_off_state',
 'web_backend.teacher_schedule_settings',
 'web_backend.student_self_service',
 'web_backend.teacher_lesson_actions',
 'web_backend.push_events',
 'web_backend.student_regular_booking',
 'web_backend.atomic_student_booking',
 'web_backend.api_v6',
]
for name in mods:
    __import__(name)
    print('IMPORT_OK',name)
PY

echo "=== 5. PRODUCT/PWA/DESKTOP STATIC GATE ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP/rc" "$PYTHON" scripts/adelia_product_gate.py

echo "=== 5A. PUSH NOTIFICATION SELFTEST ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP/rc" "$PYTHON" scripts/push_notification_selftest.py

echo "=== 6. REQUIRED RELEASE ASSETS ==="
for f in \
  web/teacher.html \
  web/teacher_day_off_preview.js \
  web/teacher_clean_runtime.js \
  web/service-worker.js \
  web/teacher-service-worker.js \
  web/parent/service-worker.js \
  scripts/push_notification_selftest.py \
  web_backend/teacher_lesson_actions.py \
  web_backend/teacher_day_off_state.py \
  web_backend/teacher_schedule_settings.py \
  web_backend/student_self_service.py \
  core/payment_wait_control.py \
  final_features/slot_change.py \
  scripts/recover_ivan_regular_schedules.py \
  desktop/package.json \
  desktop/preload.js; do
  test -s "$f" || { echo "MISSING_OR_EMPTY $f"; exit 20; }
  echo "ASSET_OK $f"
done

echo "=== 7. COPY PRODUCTION DB ONLY ==="
PROD_DB="$APP_DIR/tutor.db"
test -f "$PROD_DB" || { echo "MISSING production DB: $PROD_DB"; exit 21; }
cp -a "$PROD_DB" "$TMP/ivan-test.db"
chmod 600 "$TMP/ivan-test.db"
printf "TEST_DB=%s\n" "$TMP/ivan-test.db"

echo "=== 8. ISOLATED SCHEMA + IVAN RECOVERY ==="
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$TMP/rc" ADELIA_TEST_DB="$TMP/ivan-test.db" "$PYTHON" - <<'PY'
import os
import database

path=os.environ['ADELIA_TEST_DB']
database.DB_NAME=path

from web_backend import teacher_day_off_state
from core import payment_wait_control
from final_features import slot_change

teacher_day_off_state.ensure_schema()
payment_wait_control.ensure_schema()
slot_change.ensure_schema()
print('ISOLATED_SCHEMA_OK')

from core import schedule_sync

def fake_sync(ids):
    ids=[int(x) for x in ids]
    print('SYNC_STUB',ids)
    return {'synced_lesson_ids':ids,'failed':[]}

schedule_sync.sync_lessons_blocking=fake_sync

from scripts import recover_ivan_regular_schedules as ivan
ivan.database.DB_NAME=path

print('IVAN_DRY_RUN_BEGIN')
ivan.run(apply=False)
print('IVAN_APPLY_1_BEGIN')
ivan.run(apply=True)
print('IVAN_APPLY_2_BEGIN')
ivan.run(apply=True)

conn=database.connect()
try:
    rows=conn.execute(
        "SELECT id,active,start_date,end_date,created_lessons_count FROM regular_schedules WHERE id IN (9,10,11) ORDER BY id"
    ).fetchall()
    assert len(rows)==3, rows
    for row in rows:
        assert int(row['active'] or 0)==1, dict(row)
        assert str(row['start_date']) >= ivan.DEFAULT_START_DATE, dict(row)
        assert str(row['end_date']) == ivan.TARGET_END_DATE, dict(row)
    dupes=conn.execute(
        """SELECT start_time,COUNT(*) n FROM lessons WHERE user_id=? AND lesson_status NOT IN ('CANCELLED','REJECTED') GROUP BY start_time HAVING COUNT(*)>1""",
        (ivan.EXPECTED_USER_ID,),
    ).fetchall()
    assert not dupes, [dict(x) for x in dupes]
finally:
    conn.close()
print('IVAN_ISOLATED_GATE_OK')
PY

echo "=== 9. FRONTEND REGRESSION MARKERS ==="
"$PYTHON" - <<'PY'
from pathlib import Path
checks={
 'web/teacher_day_off_preview.js':['lastPreviewKey','lessonTime','previewKey(payload)','dayOffSaveBtn'],
 'web/teacher_clean_runtime.js':['AWAITING_PAYMENT'],
 'web_backend/teacher_lesson_actions.py':['confirm_payment_wait','remind_payment','finalize_move'],
 'final_features/slot_change.py':['apply_requester_before_start','already_applied','reschedule_apply_state_changed'],
 'web_backend/student_self_service.py':['teacher_day_off_state.is_marked'],
 'web_backend/teacher_schedule_settings.py':['teacher_day_off_state.mark_lessons'],
 'core/payment_wait_control.py':['BEGIN IMMEDIATE','already_confirmed'],
}
for path,markers in checks.items():
    text=Path(path).read_text(encoding='utf-8')
    for marker in markers:
        assert marker in text,(path,marker)
    print('MARKERS_OK',path)
PY

echo "=== RESULT ==="
echo "FINAL_RC_GATE_PASSED"
printf "RC_HEAD=%s\n" "$RC_HEAD"
echo "Production code, services, pointer and production database were not modified."
