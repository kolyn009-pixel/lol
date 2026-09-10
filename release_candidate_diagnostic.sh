#!/usr/bin/env bash
set -u

ROOT="${ROOT:-/opt/tutorbot}"
PY="${PY:-$ROOT/venv/bin/python}"
PROD_DB="${PROD_DB:-$ROOT/tutor.db}"
ENV_FILE="${ENV_FILE:-/etc/tutorbot/adelia.env}"
TMP="$(mktemp -d /tmp/adelia-rc-XXXXXX)"
TEST_DB="$TMP/tutor_test.db"
FAIL=0
trap 'rm -rf "$TMP"' EXIT

ok(){ printf 'OK   %s\n' "$1"; }
warn(){ printf 'WARN %s\n' "$1"; }
fail(){ printf 'FAIL %s\n' "$1"; FAIL=1; }

printf '=== ADELIA RELEASE CANDIDATE DIAGNOSTIC ===\n'
printf 'root=%s\n' "$ROOT"
printf 'tmp=%s\n\n' "$TMP"

if [ -d "$ROOT/.git" ]; then
  cd "$ROOT" || exit 2
  printf '%s\n' '--- GIT ---'
  git status --short || true
  printf 'branch='; git branch --show-current || true
  printf 'head='; git rev-parse --short HEAD || true
else
  fail 'git checkout not found'
fi

printf '%s\n' '--- PYTHON / COMPILE ---'
if [ -x "$PY" ]; then
  "$PY" --version || fail 'python version'
  "$PY" "$ROOT/preflight_check.py" && ok 'preflight_check.py' || fail 'preflight_check.py'
else
  fail 'venv python missing'
fi

printf '%s\n' '--- DATABASE COPY ---'
if [ -f "$PROD_DB" ]; then
  cp -p "$PROD_DB" "$TEST_DB" && ok 'production DB copied to sandbox' || fail 'DB copy'
else
  fail 'production DB missing'
fi

printf '%s\n' '--- SANDBOX SCHEMA / IMPORTS ---'
if [ -f "$TEST_DB" ] && [ -x "$PY" ]; then
  TUTORBOT_TEST_DB="$TEST_DB" TUTORBOT_TEST_DATA_DIR="$TMP" "$PY" - <<'PY'
import os
import database
database.set_test_mode(True)
mods = [
    ('events', 'web_backend.event_campaign', 'ensure_schema'),
    ('social-profile', 'web_backend.student_social_profile', 'ensure_schema'),
    ('group-portal', 'web_backend.group_portal', 'ensure_schema'),
    ('group-access', 'web_backend.group_lesson_access', 'ensure_schema'),
    ('attendance', 'web_backend.attendance_tracking', 'ensure_schema'),
    ('homework-watchdog', 'web_backend.homework_watchdog', 'ensure_schema'),
    ('receipt-archive', 'web_backend.receipt_cloud_archive', 'ensure_table'),
]
failed=[]
for label,module_name,fn in mods:
    try:
        mod=__import__(module_name, fromlist=[fn])
        getattr(mod,fn)()
        print('OK  ',label)
    except Exception as exc:
        failed.append((label,type(exc).__name__,str(exc)))
        print('FAIL',label,type(exc).__name__,str(exc)[:180])
try:
    import web_backend.api_v5
    import vk_adapter.runtime
    import web_backend.homework_delivery_worker
    import web_backend.receipt_archive_worker
    print('OK   runtime imports')
except Exception as exc:
    failed.append(('runtime-imports',type(exc).__name__,str(exc)))
    print('FAIL runtime imports',type(exc).__name__,str(exc)[:180])
conn=database.connect()
try:
    result=conn.execute('PRAGMA integrity_check').fetchone()[0]
    print('OK   sqlite integrity_check' if result=='ok' else 'FAIL sqlite integrity_check: '+str(result))
    if result!='ok':failed.append(('sqlite-integrity','Error',str(result)))
finally:
    conn.close()
if failed:raise SystemExit(7)
PY
  [ $? -eq 0 ] && ok 'sandbox schema/import pass' || fail 'sandbox schema/import pass'
fi

printf '%s\n' '--- ENV PRESENCE (VALUES NEVER PRINTED) ---'
check_env(){
  name="$1"
  if [ -f "$ENV_FILE" ] && grep -q "^${name}=." "$ENV_FILE"; then ok "$name present"; else warn "$name missing"; fi
}
check_env ADELIA_OTP_SECRET
check_env YANDEX_TELEMOST_OAUTH_TOKEN
check_env YANDEX_TELEMOST_ENABLED
check_env YANDEX_DISK_OAUTH_TOKEN
check_env BOT_TOKEN
check_env VK_TOKEN
check_env VK_GROUP_ID

printf '%s\n' '--- SYSTEMD UNIT STATIC VERIFY ---'
if command -v systemd-analyze >/dev/null 2>&1; then
  units="$ROOT/web_backend/adelia-web.service $ROOT/web_backend/adelia-homework-delivery.service $ROOT/web_backend/adelia-receipt-archive.service $ROOT/vk_adapter/tutorbot-vk.service"
  # shellcheck disable=SC2086
  systemd-analyze verify $units >/tmp/adelia-systemd-verify.$$ 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then ok 'systemd units'; else fail 'systemd units'; cat /tmp/adelia-systemd-verify.$$; fi
  rm -f /tmp/adelia-systemd-verify.$$
else
  warn 'systemd-analyze unavailable'
fi

printf '%s\n' '--- CURRENT SERVICES (READ ONLY) ---'
for unit in tutorbot.service tutorbot-vk.service tutorbot-web.service adelia-web.service adelia-homework-delivery.service adelia-receipt-archive.service; do
  state="$(systemctl is-active "$unit" 2>/dev/null || true)"
  printf '%-40s %s\n' "$unit" "${state:-unknown}"
done

printf '%s\n' '--- YANDEX CREDENTIAL READ-ONLY PROBES ---'
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi
if [ -n "${YANDEX_DISK_OAUTH_TOKEN:-}" ]; then
  code="$(curl -sS -o "$TMP/disk.json" -w '%{http_code}' -H "Authorization: OAuth $YANDEX_DISK_OAUTH_TOKEN" 'https://cloud-api.yandex.net/v1/disk?fields=user,total_space,used_space' || true)"
  [ "$code" = 200 ] && ok 'Yandex Disk OAuth read access' || fail "Yandex Disk OAuth HTTP $code"
else
  warn 'Yandex Disk probe skipped: token absent'
fi
if [ -n "${YANDEX_TELEMOST_OAUTH_TOKEN:-}" ]; then
  ok 'Telemost OAuth token present; creation probe intentionally skipped to avoid creating a conference'
else
  warn 'Telemost OAuth token absent'
fi

printf '%s\n' '--- RESULT ---'
if [ "$FAIL" -eq 0 ]; then
  printf 'ADELIA RC DIAGNOSTIC: PASS\n'
  exit 0
fi
printf 'ADELIA RC DIAGNOSTIC: FAIL\n'
exit 1
