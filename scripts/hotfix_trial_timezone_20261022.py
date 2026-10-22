"""Guarded availability fix; preflight on a private DB copy, restart web only."""
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import json

OLD_DT="def _dt(v):return v if isinstance(v,datetime) else datetime.fromisoformat(str(v))"
NEW_DT='''def _dt(v):
 """Normalize scheduled instants to the canonical schedule wall-clock.

 Legacy naive values already use this timezone. Convert explicit offsets
 before removing tzinfo; simply stripping an offset would shift busy slots.
 """
 from core.lesson_time import lesson_timezone
 value=v if isinstance(v,datetime) else datetime.fromisoformat(str(v))
 return value if value.tzinfo is None else value.astimezone(lesson_timezone()).replace(tzinfo=None)'''
OLD_SQL='''f"WHERE start_time < ? AND end_time > ? AND lesson_status IN ({marks})",
    (end.isoformat(),start.isoformat(),*sorted(BLOCKING_LESSON_STATUSES))'''
NEW_SQL='''f"WHERE lesson_status IN ({marks})",
    tuple(sorted(BLOCKING_LESSON_STATUSES))'''
OLD_RETURN="  return {'lessons':lessons,'trials':trials,'regular':regular}"
NEW_RETURN='''  # ISO strings with different offsets cannot be compared lexicographically.
  # Filter the active rows in Python using the same normalization as collisions.
  for r in lessons:
   r['start_time']=_dt(r['start_time']).isoformat()
   r['end_time']=_dt(r['end_time']).isoformat()
  lessons=[r for r in lessons if overlaps(start,end,r['start_time'],r['end_time'])]
  for r in trials:
   r['selected_slot_start']=_dt(r['selected_slot_start']).isoformat()
   if r.get('selected_slot_end'):r['selected_slot_end']=_dt(r['selected_slot_end']).isoformat()
  return {'lessons':lessons,'trials':trials,'regular':regular}'''


def patch(source):
 for old,new in [(OLD_DT,NEW_DT),(OLD_SQL,NEW_SQL),(OLD_RETURN,NEW_RETURN)]:
  if new in source:
   if source.count(new)!=1:raise RuntimeError('Ambiguous patched source')
  elif source.count(old)==1:source=source.replace(old,new)
  else:raise RuntimeError('Unexpected availability source; no files changed')
 compile(source,'web_backend/availability_guard.py','exec')
 return source


def install():
 if os.geteuid()!=0:raise SystemExit('Run as root on the Ubuntu server')
 with open('/run/adelia-learning-deploy.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  release=Path('/opt/adelia-current').resolve(strict=True)
  if release.parent!=Path('/opt/adelia-releases'):raise RuntimeError('Unexpected release path')
  pid=int(subprocess.check_output(['systemctl','show','tutorbot-web','-p','MainPID','--value'],text=True).strip())
  if pid<1 or Path(f'/proc/{pid}/cwd').resolve()!=release:raise RuntimeError('Web process does not match active release')
  target=release/'web_backend/availability_guard.py'
  if target.is_symlink() or target.resolve().parent!=release/'web_backend':raise RuntimeError('Unexpected handler path')
  original=target.read_bytes();updated=patch(original.decode()).encode()
  if original==updated:
   print('TRIAL_TIMEZONE_ALREADY_INSTALLED');return
  backups=Path('/opt/tutorbot/backups');backups.mkdir(exist_ok=True)
  backup=Path(tempfile.mkdtemp(prefix='trial-timezone-20261022-',dir=backups));os.chmod(backup,0o700)
  shutil.copy2(target,backup/'availability_guard.py')
  candidate=backup/'candidate.py';candidate.write_bytes(updated)
  # Reuse the web process's environment without printing any credentials.
  env=dict(os.environ)
  for entry in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
   if b'=' in entry:
    k,v=entry.split(b'=',1);env[os.fsdecode(k)]=os.fsdecode(v)
  if Path(env.get('ADELIA_DB_PATH','/opt/tutorbot/tutor.db')).resolve()!=Path('/opt/tutorbot/tutor.db'):
   raise RuntimeError('Unexpected production database path')
  dbcopy=backup/'preflight.db'
  with sqlite3.connect('file:/opt/tutorbot/tutor.db?mode=ro',uri=True) as src:
   with sqlite3.connect(dbcopy) as dst:src.backup(dst)
  env['ADELIA_DB_PATH']=str(dbcopy);env['PYTHONDONTWRITEBYTECODE']='1'
  smoke='''import importlib.util,json,sys
import database
database.DB_NAME=sys.argv[2]
spec=importlib.util.spec_from_file_location('web_backend.availability_guard',sys.argv[1])
guard=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=guard
spec.loader.exec_module(guard)
from web_backend.public_trial_slots import feed
for zone in ('Europe/Moscow','Europe/Samara','Asia/Yekaterinburg'):
 result=feed(zone,days=14,duration_minutes=60)
 assert isinstance(result.get('items'),list)
print('REAL_DB_COPY_SLOT_FEED=OK')
'''
  subprocess.run(['/opt/tutorbot/venv/bin/python','-c',smoke,str(candidate),str(dbcopy)],cwd=release,env=env,check=True,timeout=90)

  def replace(data):
   fd,name=tempfile.mkstemp(prefix='.availability-hotfix-',dir=target.parent)
   try:
    with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    shutil.copystat(target,name);st=target.stat();os.chown(name,st.st_uid,st.st_gid);os.replace(name,target)
   finally:
    if os.path.exists(name):os.unlink(name)

  try:
   replace(updated)
   subprocess.run(['systemctl','restart','tutorbot-web'],check=True,timeout=60)
   last_error=None
   for _ in range(20):
    try:
     with urllib.request.urlopen('http://127.0.0.1:8876/api/public/trial/slots?timezone=Europe%2FMoscow&days=14&duration_minutes=60',timeout=10) as response:
      result=json.load(response)
     if not isinstance(result.get('items'),list):raise RuntimeError('Invalid public slot response')
     subprocess.run(['systemctl','is-active','--quiet','tutorbot-web'],check=True)
     break
    except Exception as exc:last_error=exc;time.sleep(1)
   else:raise RuntimeError('Public slot API did not recover') from last_error
  except BaseException:
   replace(original);subprocess.run(['systemctl','restart','tutorbot-web'],check=False,timeout=60)
   print('HOTFIX_FAILED; original source restored. Backup:',backup);raise
  print('TRIAL_TIMEZONE_HOTFIX_OK')
  print('Public slot API: HTTP 200')
  print('Backup:',backup)


if __name__=='__main__':install()
