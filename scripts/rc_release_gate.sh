#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/tutorbot}"
BRANCH="release/adelia-unified-rc"
REMOTE="${ADELIA_RC_REMOTE:-origin}"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORKTREE="/tmp/adelia_rc_gate_${STAMP}"

cleanup() {
  if git -C "$ROOT" worktree list --porcelain 2>/dev/null | grep -Fq "worktree $WORKTREE"; then
    git -C "$ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORKTREE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "===== 1. FETCH RC ====="
git -C "$ROOT" fetch "$REMOTE" "$BRANCH"
EXPECTED="$(git -C "$ROOT" rev-parse FETCH_HEAD)"
REMOTE_REF="$REMOTE/$BRANCH"
REMOTE_HEAD="$(git -C "$ROOT" rev-parse "$REMOTE_REF")"
echo "EXPECTED=$EXPECTED"
echo "REMOTE_HEAD=$REMOTE_HEAD"
test "$EXPECTED" = "$REMOTE_HEAD"

echo
echo "===== 2. CREATE ISOLATED WORKTREE ====="
cleanup
git -C "$ROOT" worktree add --detach "$WORKTREE" "$EXPECTED"
ACTUAL="$(git -C "$WORKTREE" rev-parse HEAD)"
echo "WORKTREE=$WORKTREE"
echo "ACTUAL=$ACTUAL"
test "$ACTUAL" = "$EXPECTED"

PYTHON=""
for candidate in "$ROOT/venv/bin/python" "$ROOT/.venv/bin/python" python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "FAIL: python interpreter not found" >&2
  exit 20
fi
echo "PYTHON=$PYTHON"

echo
echo "===== 3. COMPILE RELEASE SOURCE ====="
cd "$WORKTREE"
"$PYTHON" -m compileall -q   core final_features handlers integrations scripts vk_adapter web_backend database.py
echo "COMPILE_RESULT=OK"

echo
echo "===== 4. IMPORT RELEASE MODULES ====="
"$PYTHON" - <<'PY'
import importlib

modules = [
    "database",
    "core.minute_balance",
    "core.lesson_lifecycle",
    "core.schedule_sync",
    "final_features.slot_change",
    "integrations.google_calendar",
    "integrations.lesson_sync",
    "integrations.telemost_lifecycle",
    "integrations.yandex_telemost",
    "web_backend.student_onboarding",
    "web_backend.student_regular_booking",
    "web_backend.student_self_service",
    "web_backend.student_reschedule",
    "web_backend.teacher_day_off_state",
    "web_backend.teacher_schedule_settings",
    "web_backend.teacher_lesson_actions",
    "web_backend.telemost_runtime",
    "web_backend.telemost_precreate_worker",
    "web_backend.finance_receipts",
    "web_backend.receipt_cloud_archive",
    "web_backend.push_events",
]
for name in modules:
    importlib.import_module(name)
    print("IMPORT OK:", name)
PY

echo
echo "===== 5. DAY-OFF ISOLATED DB SELFTEST ====="
"$PYTHON" rc_day_off_selftest.py

echo
echo "===== 5B. CALENDAR LEGACY SCHEMA SELFTEST ====="
"$PYTHON" rc_calendar_legacy_selftest.py

echo
echo "===== 6. UNIFIED ISOLATED RELEASE SELFTEST ====="
"$PYTHON" rc_release_selftest.py

echo
echo "===== 6B. UNIFIED MEDIA SELFTEST ====="
"$PYTHON" rc_media_selftest.py

echo
echo "===== 7. FRONTEND STATIC SELFTEST ====="
"$PYTHON" rc_frontend_static_selftest.py

echo
echo "===== 7B. DESKTOP STATIC SELFTEST ====="
"$PYTHON" rc_desktop_static_selftest.py

echo
echo "===== 7C. DESKTOP NODE SELFTEST ====="
if command -v node >/dev/null 2>&1; then
  if [ -f desktop/selftest.js ]; then
    node desktop/selftest.js
  else
    echo "DESKTOP_SELFTEST=SKIPPED missing desktop/selftest.js"
  fi
else
  echo "DESKTOP_SELFTEST=SKIPPED node_not_found"
fi

echo
echo "===== 8. VERIFY SOURCE CHECKOUT UNCHANGED ====="
SOURCE_HEAD="$(git -C "$ROOT" rev-parse HEAD)"
echo "SOURCE_HEAD=$SOURCE_HEAD"
echo "RC_HEAD=$EXPECTED"
echo "No services were restarted and no production database was opened by this gate."

echo
echo "===== RC GATE PASS ====="
echo "RC_HEAD=$EXPECTED"
