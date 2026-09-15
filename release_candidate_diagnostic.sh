#!/usr/bin/env bash
set -u

PROD_ROOT="${PROD_ROOT:-/opt/tutorbot}"
PY="${PY:-$PROD_ROOT/venv/bin/python}"
PROD_DB="${PROD_DB:-$PROD_ROOT/tutor.db}"
ENV_FILE="${ENV_FILE:-/etc/tutorbot/adelia.env}"
RC_BRANCH="${RC_BRANCH:-release/adelia-unified-rc}"
TMP="$(mktemp -d /tmp/adelia-rc-XXXXXX)"
RC_ROOT="$TMP/code"
TEST_DB="$TMP/tutor_test.db"
FAIL=0
WORKTREE_ADDED=0

cleanup(){
  if [ "$WORKTREE_ADDED" -eq 1 ] && [ -d "$PROD_ROOT/.git" ]; then
    git -C "$PROD_ROOT" worktree remove --force "$RC_ROOT" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

ok(){ printf 'OK   %s\n' "$1"; }
warn(){ printf 'WARN %s\n' "$1"; }
fail(){ printf 'FAIL %s\n' "$1"; FAIL=1; }

printf '=== ADELIA RELEASE CANDIDATE DIAGNOSTIC v4 ===\n'
printf 'production_root=%s\n' "$PROD_ROOT"
printf 'release_branch=%s\n' "$RC_BRANCH"
printf 'tmp=%s\n\n' "$TMP"

printf '%s\n' '--- PRODUCTION CHECKOUT (READ ONLY) ---'
if [ -d "$PROD_ROOT/.git" ]; then
  printf 'branch='; git -C "$PROD_ROOT" branch --show-current || true
  printf 'head='; git -C "$PROD_ROOT" rev-parse --short HEAD || true
  dirty="$(git -C "$PROD_ROOT" status --porcelain | wc -l | tr -d ' ')"
  printf 'dirty_entries=%s\n' "$dirty"
  [ "$dirty" -gt 0 ] && warn 'production checkout is dirty; working tree will NOT be modified' || ok 'production checkout clean'
else
  fail 'production git checkout not found'
fi

printf '%s\n' '--- ISOLATED RELEASE WORKTREE ---'
if [ -d "$PROD_ROOT/.git" ]; then
  git -C "$PROD_ROOT" fetch origin "$RC_BRANCH" >/dev/null 2>&1 || fail 'git fetch release branch'
  if git -C "$PROD_ROOT" rev-parse --verify "origin/$RC_BRANCH" >/dev/null 2>&1; then
    git -C "$PROD_ROOT" worktree add --detach "$RC_ROOT" "origin/$RC_BRANCH" >/dev/null 2>&1 && WORKTREE_ADDED=1 || fail 'create isolated worktree'
  else
    fail 'remote release branch missing'
  fi
fi
if [ "$WORKTREE_ADDED" -eq 1 ]; then
  printf 'rc_head='; git -C "$RC_ROOT" rev-parse HEAD || true
  ok 'isolated release worktree created'
fi

printf '%s\n' '--- PYTHON / COMPILE ---'
if [ -x "$PY" ] && [ "$WORKTREE_ADDED" -eq 1 ]; then
  "$PY" --version || fail 'python version'
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" "$PY" -m compileall -q core final_features handlers integrations scripts vk_adapter web_backend) && ok 'release compileall' || fail 'release compileall'
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" "$PY" preflight_check.py) && ok 'release preflight_check.py' || fail 'release preflight_check.py'
else
  fail 'venv python or release worktree missing'
fi

printf '%s\n' '--- DATABASE COPY ---'
if [ -f "$PROD_DB" ]; then
  cp -p "$PROD_DB" "$TEST_DB" && ok 'production DB copied to sandbox' || fail 'DB copy'
else
  fail 'production DB missing'
fi

printf '%s\n' '--- SANDBOX SCHEMA / IMPORTS / SLOT SPEED ---'
if [ -f "$TEST_DB" ] && [ -x "$PY" ] && [ "$WORKTREE_ADDED" -eq 1 ]; then
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" TUTORBOT_TEST_DB="$TEST_DB" TUTORBOT_TEST_DATA_DIR="$TMP" "$PY" - <<'PY'
import time, statistics
import database
database.set_test_mode(True)
mods = [
    ('events', 'web_backend.event_campaign', 'ensure_schema'),
    ('social-profile', 'web_backend.student_social_profile', 'ensure_schema'),
    ('group-portal', 'web_backend.group_portal', 'ensure_schema'),
    ('group-access', 'web_backend.group_lesson_access', 'ensure_schema'),
    ('group-finance', 'web_backend.group_finance', 'ensure_schema'),
    ('attendance', 'web_backend.attendance_tracking', 'ensure_schema'),
    ('homework-watchdog', 'web_backend.homework_watchdog', 'ensure_schema'),
    ('receipt-archive', 'web_backend.receipt_cloud_archive', 'ensure_table'),
]
failed=[]
for label,module_name,fn in mods:
    try:
        mod=__import__(module_name, fromlist=[fn]); getattr(mod,fn)(); print('OK  ',label)
    except Exception as exc:
        failed.append((label,type(exc).__name__,str(exc))); print('FAIL',label,type(exc).__name__,str(exc)[:180])
try:
    for name in (
        'web_backend.api_v6','web_backend.api_v7','web_backend.student_live_entry',
        'web_backend.telemost_runtime','web_backend.parent_portal','web_backend.open_event_admin',
        'web_backend.group_finance_reservations','vk_adapter.runtime',
        'web_backend.homework_delivery_worker','web_backend.receipt_archive_worker',
        'core.schedule_sync','integrations.lesson_sync'
    ):
        __import__(name); print('OK   import',name)
except Exception as exc:
    failed.append(('runtime-imports',type(exc).__name__,str(exc))); print('FAIL runtime imports',type(exc).__name__,str(exc)[:180])
conn=database.connect()
try:
    result=conn.execute('PRAGMA integrity_check').fetchone()[0]
    print('OK   sqlite integrity_check' if result=='ok' else 'FAIL sqlite integrity_check: '+str(result))
    print('INFO sqlite journal_mode=',conn.execute('PRAGMA journal_mode').fetchone()[0])
    print('INFO sqlite busy_timeout=',conn.execute('PRAGMA busy_timeout').fetchone()[0])
    if result!='ok':failed.append(('sqlite-integrity','Error',str(result)))
finally:conn.close()
try:
    from web_backend import public_trial_slots
    times=[]
    for i in range(3):
        t=time.perf_counter(); data=public_trial_slots.feed('Europe/Moscow',14,60); dt=time.perf_counter()-t; times.append(dt)
        slots=sum(len(day.get('slots',[])) for day in data.get('items',[]))
        print(f'INFO trial_slots_{i+1}={dt:.3f}s slots={slots}')
    median=statistics.median(times); print(f'INFO trial_slots_median={median:.3f}s')
    if median>1.0:failed.append(('trial-slots-speed','Slow',f'{median:.3f}s'))
except Exception as exc:
    failed.append(('trial-slots',type(exc).__name__,str(exc))); print('FAIL trial slots',type(exc).__name__,str(exc)[:180])
if failed:raise SystemExit(7)
PY
  )
  [ $? -eq 0 ] && ok 'sandbox schema/import/performance pass' || fail 'sandbox schema/import/performance pass'
fi

printf '%s\n' '--- STATIC JS / DESKTOP RELEASE SELFTEST ---'
if [ "$WORKTREE_ADDED" -eq 1 ]; then
  if command -v node >/dev/null 2>&1; then
    for file in \
      web/group_events_ui.js \
      web/teacher_lesson_flow.js \
      web/teacher_group_live12.js \
      web/teacher_event_live13.js \
      web/teacher_telemost_settings.js \
      web/parent/app.js \
      web/parent/parent_v5.js; do
      node --check "$RC_ROOT/$file" >/dev/null 2>&1 && ok "syntax $file" || fail "syntax $file"
    done
    (cd "$RC_ROOT" && node desktop/selftest.js) && ok 'desktop release selftest' || fail 'desktop release selftest'
  else
    fail 'node unavailable for static JS/desktop gate'
  fi
fi

printf '%s\n' '--- ISOLATED PRODUCT SELFTESTS ---'
if [ -x "$PY" ] && [ "$WORKTREE_ADDED" -eq 1 ]; then
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" "$PY" web_backend/stage9_selftest.py) && ok 'parent Stage 9 selftest' || fail 'parent Stage 9 selftest'
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" TUTORBOT_TEST_DB="$TEST_DB" TUTORBOT_TEST_DATA_DIR="$TMP" "$PY" web_backend/group_lessons_selftest.py) && ok 'group lessons source selftest' || fail 'group lessons source selftest'
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" TUTORBOT_TEST_DB="$TEST_DB" TUTORBOT_TEST_DATA_DIR="$TMP" "$PY" scripts/adelia_product_gate.py) && ok 'Adelia product gate' || fail 'Adelia product gate'
fi

printf '%s\n' '--- RELEASE LIFECYCLE / PRIVACY ASSERTIONS ---'
if [ -x "$PY" ] && [ "$WORKTREE_ADDED" -eq 1 ]; then
  (cd "$RC_ROOT" && "$PY" - <<'PY'
from pathlib import Path
checks={
 'web_backend/event_campaign.py': ["status='IN_PROGRESS'", 'telemost_join_url'],
 'web_backend/group_lesson_access.py': ['financial_attention', 'blocked_unpaid_user_ids', "rsvp_status"],
 'web_backend/telemost_runtime.py': ["telemost_join_url=NULL", 'access_granted=0'],
 'web/teacher_lesson_flow.js': ["openLessonTool('meeting'", "openLessonTool('board'", 'endLessonWorkspace()'],
 'web/teacher_group_live12.js': ["openLessonTool('meeting'", "openLessonTool('board'", 'endLessonWorkspace()'],
 'web/teacher_event_live13.js': ["openLessonTool('meeting'", "openLessonTool('board'", 'endLessonWorkspace()', 'suppressLegacyLifecycle'],
}
for path,markers in checks.items():
    text=Path(path).read_text(encoding='utf-8')
    for marker in markers:
        assert marker in text,(path,marker)
    print('OK',path)
# Student event feed must not select provider join credentials into its public item row.
feed=Path('web_backend/event_campaign.py').read_text(encoding='utf-8')
feed_query=feed.split('def feed(user_id):',1)[1].split('def _log(',1)[0]
assert 'telemost_join_url' not in feed_query and 'telemost_conference_id' not in feed_query, 'student event feed leaks Telemost provider fields'
print('OK event feed Telemost privacy')
# Persistent whole-DOM observers are forbidden in the modern live/settings surfaces.
for path in ('web/group_events_ui.js','web/teacher_lesson_flow.js','web/teacher_group_live12.js','web/teacher_event_live13.js','web/teacher_telemost_settings.js'):
    text=Path(path).read_text(encoding='utf-8')
    assert 'MutationObserver' not in text,path
    print('OK no MutationObserver',path)
print('LIFECYCLE_PRIVACY_ASSERTIONS_PASSED')
PY
  ) && ok 'lifecycle/privacy static assertions' || fail 'lifecycle/privacy static assertions'
fi

printf '%s\n' '--- ENV DISCOVERY (VALUES NEVER PRINTED) ---'
check_env_file(){
  name="$1"
  if [ -f "$ENV_FILE" ] && grep -q "^${name}=." "$ENV_FILE"; then ok "$name in adelia.env"; return; fi
  if systemctl show tutorbot.service tutorbot-vk.service adelia-web.service adelia-receipt-archive.service --property=Environment 2>/dev/null | grep -q "${name}="; then ok "$name present in installed service environment"; return; fi
  warn "$name not found in adelia.env/service definitions"
}
check_env_file ADELIA_OTP_SECRET
check_env_file YANDEX_TELEMOST_OAUTH_TOKEN
check_env_file YANDEX_TELEMOST_ENABLED
check_env_file YANDEX_DISK_OAUTH_TOKEN
check_env_file BOT_TOKEN
check_env_file VK_TOKEN
check_env_file VK_GROUP_ID

printf '%s\n' '--- RELEASE SYSTEMD UNIT STATIC VERIFY ---'
if command -v systemd-analyze >/dev/null 2>&1 && [ "$WORKTREE_ADDED" -eq 1 ]; then
  units="$RC_ROOT/web_backend/adelia-web.service $RC_ROOT/web_backend/adelia-homework-delivery.service $RC_ROOT/web_backend/adelia-receipt-archive.service $RC_ROOT/web_backend/adelia-telemost-precreate.service $RC_ROOT/vk_adapter/tutorbot-vk.service"
  systemd-analyze verify $units >"$TMP/systemd-verify.txt" 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then ok 'release systemd units'; else fail 'release systemd units'; cat "$TMP/systemd-verify.txt"; fi
else
  warn 'systemd-analyze unavailable or worktree missing'
fi

printf '%s\n' '--- CURRENT SERVICES (READ ONLY) ---'
for unit in tutorbot.service tutorbot-vk.service tutorbot-web.service adelia-web.service adelia-homework-delivery.service adelia-receipt-archive.service adelia-telemost-precreate.service; do
  state="$(systemctl is-active "$unit" 2>/dev/null || true)"
  enabled="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
  printf '%-40s active=%-10s enabled=%s\n' "$unit" "${state:-unknown}" "${enabled:-unknown}"
done

printf '%s\n' '--- RECEIPT ARCHIVE READ-ONLY STATUS ---'
if [ -f "$TEST_DB" ] && [ -x "$PY" ] && [ "$WORKTREE_ADDED" -eq 1 ]; then
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" TUTORBOT_TEST_DB="$TEST_DB" TUTORBOT_TEST_DATA_DIR="$TMP" "$PY" - <<'PY'
import database
database.set_test_mode(True)
from web_backend import receipt_cloud_archive
print('configured=',receipt_cloud_archive.configured())
print('queue_stats=',receipt_cloud_archive.queue_stats())
PY
  ) || fail 'receipt archive status'
fi

printf '%s\n' '--- GOOGLE CALENDAR / TELEMOST READ-ONLY PROBE ---'
if [ "$WORKTREE_ADDED" -eq 1 ]; then
  [ -f "$PROD_ROOT/token.json" ] && cp -p "$PROD_ROOT/token.json" "$RC_ROOT/token.json"
  [ -f "$PROD_ROOT/credentials.json" ] && cp -p "$PROD_ROOT/credentials.json" "$RC_ROOT/credentials.json"
  (cd "$RC_ROOT" && PYTHONPATH="$RC_ROOT" "$PY" scripts/integration_selftest.py)
  rc=$?
  [ $rc -eq 0 ] && ok 'Google/Telemost integration readiness' || fail "Google/Telemost integration readiness rc=$rc"
fi

printf '%s\n' '--- YANDEX DISK READ-ONLY PROBE ---'
DISK_TOKEN=""
if [ -f "$ENV_FILE" ]; then DISK_TOKEN="$(sed -n 's/^YANDEX_DISK_OAUTH_TOKEN=//p' "$ENV_FILE" | tail -n 1)"; fi
if [ -n "$DISK_TOKEN" ]; then
  code="$(curl -sS -o "$TMP/disk.json" -w '%{http_code}' -H "Authorization: OAuth $DISK_TOKEN" 'https://cloud-api.yandex.net/v1/disk?fields=user,total_space,used_space' || true)"
  [ "$code" = 200 ] && ok 'Yandex Disk OAuth read access' || fail "Yandex Disk OAuth HTTP $code"
else
  warn 'Yandex Disk probe skipped: dedicated disk token absent'
fi
unset DISK_TOKEN

printf '%s\n' '--- RESULT ---'
if [ "$FAIL" -eq 0 ]; then
  printf 'ADELIA RC DIAGNOSTIC: PASS\n'
  exit 0
fi
printf 'ADELIA RC DIAGNOSTIC: FAIL\n'
exit 1
