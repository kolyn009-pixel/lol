#!/usr/bin/env bash
# Pin the tested application code; preserve live release edits with three-way merges.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'Run inside the Ubuntu server as root.' >&2; exit 1; }
[[ ${1:-} == deploy || ${1:-} == prepare ]] || { echo 'Usage: bash deploy_learning_20261012.sh prepare|deploy'; exit 2; }
MODE=$1
REPO=/opt/tutorbot
CURRENT=/opt/adelia-current
BASE=01ce8fde7fa5de83609d0a1796c65f71e36ef04b
TARGET=5df2445deeaf215d8c6923ff3a0fdd7fc0b06321
BRANCH=feat/adelia-learning-upgrades-20261012
DB=/opt/tutorbot/tutor.db
HEALTH=http://127.0.0.1:8876/api/health
UNITS=(tutorbot tutorbot-web tutorbot-vk adelia-homework-delivery adelia-receipt-archive adelia-telemost-precreate)
exec 9>/run/adelia-learning-deploy.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 2; }
[[ -L $CURRENT ]] || { echo 'Expected release symlink is missing.' >&2; exit 2; }
OLD=$(readlink -f "$CURRENT")
[[ $OLD == /opt/adelia-releases/$BASE ]] || { echo "Unexpected live release: $OLD. Nothing switched." >&2; exit 2; }
[[ -f $DB ]] || { echo 'Canonical database is missing.' >&2; exit 2; }
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP=$(mktemp -d "/opt/tutorbot/backups/learning-${STAMP}-XXXXXX")
NEW=$(mktemp -d "/opt/adelia-releases/${TARGET}-XXXXXX")
chmod 700 "$BACKUP"
chmod 755 "$NEW"
SWITCHED=0
STOPPED=0

rollback_on_error() {
  local result=$?
  trap - ERR
  set +e
  if [[ $STOPPED == 1 ]]; then
    systemctl stop "${UNITS[@]}"
  fi
  if [[ $SWITCHED == 1 ]]; then
    ln -s "$OLD" "$BACKUP/current.rollback"
    mv -Tf "$BACKUP/current.rollback" "$CURRENT"
  fi
  if [[ $STOPPED == 1 ]]; then
    if systemctl start "${UNITS[@]}"; then
      echo 'ROLLBACK_SERVICES=STARTED' >&2
    else
      echo 'ROLLBACK_SERVICES=FAILED; check systemctl status.' >&2
    fi
  fi
  echo "DEPLOY_FAILED. Previous release: $OLD. Backup: $BACKUP" >&2
  echo 'Database was not replaced. Additive feature tables may remain after rollback.' >&2
  exit "$result"
}
trap rollback_on_error ERR

printf 'Active release: %s\nTarget code: %s\nBackup: %s\n' "$OLD" "$TARGET" "$BACKUP"
curl -fsS --max-time 8 "$HEALTH" > "$BACKUP/health-before.json"
nginx -t
git -C "$REPO" diff --binary > "$BACKUP/checkout-local-changes.patch"
git -C "$REPO" status --porcelain > "$BACKUP/checkout-status.txt"
printf '%s\n' "$OLD" > "$BACKUP/previous-release.txt"
printf '%s\n' "$NEW" > "$BACKUP/new-release.txt"

# Read only the required runtime paths. No tokens or complete environment are printed.
python3 - "$OLD" "$DB" "$BACKUP/runtime.json" <<'PY'
import json,os,subprocess,sys
old,db,dest=sys.argv[1:];rows=[]
for unit in ['tutorbot','tutorbot-web','tutorbot-vk','adelia-homework-delivery','adelia-receipt-archive','adelia-telemost-precreate']:
    pid=int(subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip() or '0')
    if not pid:raise SystemExit(f'{unit} is not running; nothing switched')
    cwd=os.readlink(f'/proc/{pid}/cwd')
    if cwd!=old:raise SystemExit(f'{unit} uses a different release; nothing switched')
    env=dict(x.decode(errors='replace').split('=',1) for x in open(f'/proc/{pid}/environ','rb').read().split(b'\0') if b'=' in x)
    actual=os.path.realpath(env.get('ADELIA_DB_PATH') or os.path.join(cwd,'tutor.db'))
    if actual!=os.path.realpath(db):raise SystemExit(f'{unit} uses another database; nothing switched')
    args=[x.decode() for x in open(f'/proc/{pid}/cmdline','rb').read().split(b'\0') if x]
    if any(x.startswith(old+'/') and x.endswith('.py') for x in args[1:]):raise SystemExit(f'{unit} pins a script to the old release; inspect ExecStart before deploying')
    row={'unit':unit,'python':args[0]};rows.append(row)
    if unit=='tutorbot-web' and env.get('ADELIA_WEB_PORT','8765')!='8876':raise SystemExit('Web port changed; nothing switched')
json.dump(rows,open(dest,'w'))
print('RUNTIME_PATHS=OK')
PY

backup_db() {
  python3 - "$DB" "$1" <<'PY'
import sqlite3,sys,os
src,dest=sys.argv[1:]
with sqlite3.connect('file:'+src+'?mode=ro',uri=True,timeout=30) as source:
    with sqlite3.connect(dest) as target:source.backup(target)
with sqlite3.connect('file:'+dest+'?mode=ro',uri=True) as target:
    if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise SystemExit('Backup integrity failed')
os.chmod(dest,0o600)
print('SQLITE_BACKUP=OK')
PY
}
backup_db "$BACKUP/preflight.sqlite3"
git -C "$REPO" fetch --no-tags origin "$BRANCH"
git -C "$REPO" cat-file -e "$TARGET^{commit}"
git -C "$REPO" merge-base --is-ancestor "$TARGET" FETCH_HEAD
git -C "$REPO" merge-base --is-ancestor "$BASE" "$TARGET"

# Copy the actual working release, including its server-specific files and symlinks.
cp -a "$OLD/." "$NEW/"
chmod 755 "$NEW"
python3 - "$REPO" "$BASE" "$TARGET" "$NEW" "$BACKUP" <<'PY'
import os,pathlib,subprocess,sys
repo,base,target,new,backup=sys.argv[1:];new=pathlib.Path(new);backup=pathlib.Path(backup)
def git(*args):return subprocess.check_output(['git','-C',repo,*args])
paths=git('diff','--name-only','-z',base,target).split(b'\0');merged=[]
for raw in paths:
    if not raw:continue
    name=raw.decode();relative=pathlib.PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts:raise SystemExit('Unsafe patch path')
    dst=new/name
    # Never follow a changed code-file symlink into the live release or shared data.
    if any(p.is_symlink() for p in [dst,*dst.parents] if p!=new and new in p.parents):raise SystemExit('Code symlink needs review: '+name)
    before=subprocess.run(['git','-C',repo,'show',base+':'+name],capture_output=True)
    after=subprocess.run(['git','-C',repo,'show',target+':'+name],capture_output=True)
    actual=dst.read_bytes() if dst.exists() else None
    if after.returncode:
        if before.returncode or actual!=before.stdout:raise SystemExit('Deletion conflicts with live file: '+name)
        dst.unlink();continue
    if actual==after.stdout:continue
    if before.returncode:
        if actual is not None:raise SystemExit('New file conflicts with live file: '+name)
        content=after.stdout
    elif actual is None:raise SystemExit('Live file is missing: '+name)
    elif actual==before.stdout:content=after.stdout
    else:
        current=backup/'merge-current';ancestor=backup/'merge-base';incoming=backup/'merge-target'
        current.write_bytes(actual);ancestor.write_bytes(before.stdout);incoming.write_bytes(after.stdout)
        result=subprocess.run(['git','merge-file','-p',str(current),str(ancestor),str(incoming)],capture_output=True)
        if result.returncode:raise SystemExit('MERGE_CONFLICT: '+name+'; no service was stopped')
        content=result.stdout;merged.append(name)
    dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(content)
    if before.returncode:os.chmod(dst,0o755 if name.endswith('.sh') else 0o644)
print('PATCH=OK; preserved merges:',', '.join(merged) or 'none needed')
(backup/'merged-files.txt').write_text('\n'.join(merged))
PY

# Use the existing service interpreter/dependencies. Preflight never opens the live DB.
PYTHON=$(python3 - "$BACKUP/runtime.json" <<'PY'
import json,sys
print(next(x['python'] for x in json.load(open(sys.argv[1])) if x['unit']=='tutorbot-web'))
PY
)
[[ -x $PYTHON ]] || { echo "Interpreter is unavailable: $PYTHON" >&2; false; }
cat > "$BACKUP/run-service-python.py" <<'PY'
import os,subprocess,sys
db,python=sys.argv[1:3]
pid=int(subprocess.check_output(['systemctl','show','tutorbot-web','-p','MainPID','--value'],text=True).strip() or '0')
env=os.environ.copy()
if pid:
    service=dict(x.decode(errors='replace').split('=',1) for x in open(f'/proc/{pid}/environ','rb').read().split(b'\0') if b'=' in x)
    env.update(service)
    # Retained privately for the migration while the web process is stopped.
    import json,pathlib
    cache=pathlib.Path(__file__).with_name('service-env.json')
    cache.write_text(json.dumps(service));cache.chmod(0o600)
else:
    import json,pathlib
    cache=pathlib.Path(__file__).with_name('service-env.json')
    if not cache.exists():raise SystemExit('Service environment is unavailable')
    env.update(json.loads(cache.read_text()))
env['ADELIA_DB_PATH']=db
env['PYTHONPATH']=os.getcwd()
env['PYTHONDONTWRITEBYTECODE']='1'
raise SystemExit(subprocess.run([python,*sys.argv[3:]],env=env).returncode)
PY
service_python() {
  local check_db=$1
  shift
  python3 "$BACKUP/run-service-python.py" "$check_db" "$PYTHON" "$@"
}
python3 - "$NEW/tutor.db" "$BACKUP/preflight.sqlite3" <<'PY'
import os,sys
p,db=sys.argv[1:]
if os.path.lexists(p):os.unlink(p)
os.symlink(db,p)
PY
cd "$NEW"
service_python "$BACKUP/preflight.sqlite3" - <<'PY'
import ast,pathlib
for name in ['web_backend/learning_hub.py','web_backend/learning_hub_api.py','web_backend/api_v7.py','web_backend/library.py','handlers/student_onboarding_runtime.py']:
    ast.parse(pathlib.Path(name).read_text(),filename=name)
from web_backend import api_v7,learning_hub
learning_hub.ensure_tables()
print('REAL_API_IMPORT_AND_TEST_DB_MIGRATION=OK')
PY
"$PYTHON" scripts/learning_hub_selftest.py
"$PYTHON" scripts/student_onboarding_start_selftest.py
if command -v node >/dev/null; then
  node scripts/group_chat_selftest.cjs
  node scripts/student_chat_draft_selftest.cjs
  node scripts/onboarding_confirmation_selftest.cjs
  node --check web/learning_hub.js
else
  echo 'Node absent on server; JavaScript checks already passed during development.'
fi
python3 - "$NEW/tutor.db" "$DB" <<'PY'
import os,sys
p,db=sys.argv[1:];os.unlink(p);os.symlink(db,p)
PY
python3 - "$NEW/.adelia_release" "$TARGET" <<'PY'
import os,pathlib,sys
p=pathlib.Path(sys.argv[1])
if p.is_symlink():p.unlink()
p.write_text(sys.argv[2]+'\n')
PY

# A manual code rollback preserves the shared database and later user transactions.
cat > "$BACKUP/rollback.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
umask 077
exec 9>/run/adelia-learning-deploy.lock
flock -n 9 || { echo 'Another deployment is running.'; exit 2; }
folder=$(cd -- "$(dirname -- "$0")" && pwd)
old=$(cat "$folder/previous-release.txt")
new=$(cat "$folder/new-release.txt")
[[ $(readlink -f /opt/adelia-current) == "$new" ]] || { echo 'Current release changed; refusing to overwrite a newer deployment.'; exit 2; }
units=(tutorbot tutorbot-web tutorbot-vk adelia-homework-delivery adelia-receipt-archive adelia-telemost-precreate)
systemctl stop "${units[@]}"
ln -s "$old" "$folder/current.manual-rollback"
mv -Tf "$folder/current.manual-rollback" /opt/adelia-current
systemctl start "${units[@]}"
echo 'Previous code restored. Shared database retained.'
SH
chmod 700 "$BACKUP/rollback.sh"
printf 'PREFLIGHT=OK\nCandidate: %s\nRollback: bash %s/rollback.sh\n' "$NEW" "$BACKUP"
if [[ $MODE == prepare ]]; then
  echo 'PREPARE_ONLY: no services stopped and no live symlink changed.'
  exit 0
fi

[[ $(readlink -f "$CURRENT") == "$OLD" ]] || { echo 'Live release changed during preparation.' >&2; false; }
STOPPED=1
systemctl stop "${UNITS[@]}"
backup_db "$BACKUP/before-switch.sqlite3"
service_python "$DB" - <<'PY'
from web_backend.learning_hub import ensure_tables
ensure_tables()
print('ADDITIVE_LEARNING_TABLES=OK')
PY
ln -s "$NEW" "$BACKUP/current.next"
mv -Tf "$BACKUP/current.next" "$CURRENT"
SWITCHED=1
systemctl start "${UNITS[@]}"
healthy=0
for attempt in {1..15}; do
  if curl -fsS --max-time 3 "$HEALTH" > "$BACKUP/health-after.json"; then healthy=1; break; fi
  sleep 2
done
[[ $healthy == 1 ]] || { echo 'Health check failed.' >&2; false; }
for unit in "${UNITS[@]}"; do systemctl is-active --quiet "$unit"; done
python3 - "$NEW" <<'PY'
import os,subprocess,sys
for unit in ['tutorbot','tutorbot-web','tutorbot-vk','adelia-homework-delivery','adelia-receipt-archive','adelia-telemost-precreate']:
    pid=int(subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip())
    if os.readlink(f'/proc/{pid}/cwd')!=sys.argv[1]:raise SystemExit(unit+' did not switch release')
print('ALL_SERVICE_RELEASES=OK')
PY
code=$(curl -sS --max-time 8 -o "$BACKUP/learning-route.json" -w '%{http_code}' http://127.0.0.1:8876/api/student/learning)
[[ $code == 401 ]] || { echo "New protected route failed: HTTP $code" >&2; false; }
curl -fsS --max-time 10 --resolve adeliatutor.ru:443:127.0.0.1 https://adeliatutor.ru/app/learning_hub.js > "$BACKUP/served-learning.js"
cmp "$NEW/web/learning_hub.js" "$BACKUP/served-learning.js"
curl -fsS --max-time 10 --resolve adeliatutor.ru:443:127.0.0.1 https://adeliatutor.ru/api/health > "$BACKUP/nginx-health.json"
printf 'DEPLOY_OK\nCode: %s\nRelease: %s\nDatabase: %s\nBackup: %s\nRollback: bash %s/rollback.sh\n' "$TARGET" "$NEW" "$DB" "$BACKUP" "$BACKUP"
