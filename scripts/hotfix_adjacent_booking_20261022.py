"""Fix adjacent booking, Telegram move callbacks and mixed timezone slot loading."""
import ast
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.request

PATCHES = [{"path":"database.py","name":"is_slot_reserved","old":"def is_slot_reserved(\n    start_time,\n    end_time,\n    exclude_lesson_id=None\n):\n\n    conn = connect()\n\n    sql = \"\"\"\n        SELECT id\n        FROM lessons\n\n        WHERE\n            lesson_status IN (\n                'PENDING',\n                'CONFIRMED',\n                'IN_PROGRESS'\n            )\n\n            AND start_time < ?\n\n            AND end_time > ?\n    \"\"\"\n\n    params = [\n        end_time,\n        start_time\n    ]\n\n    if exclude_lesson_id:\n\n        sql += \"\"\"\n            AND id != ?\n        \"\"\"\n\n        params.append(\n            exclude_lesson_id\n        )\n\n    sql += \"\"\"\n        LIMIT 1\n    \"\"\"\n\n    row = conn.execute(\n        sql,\n        tuple(params)\n    ).fetchone()\n\n    conn.close()\n\n    return (\n        row is not None\n    )","new":"def is_slot_reserved(start_time, end_time, exclude_lesson_id=None):\n    \"\"\"Check half-open lesson intervals after normalizing schedule timestamps.\"\"\"\n    from core.lesson_time import lesson_timezone\n    tz = lesson_timezone()\n\n    def parsed(raw):\n        value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))\n        return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)\n\n    start, end = parsed(start_time), parsed(end_time)\n    if end <= start:\n        raise ValueError(\"invalid_interval\")\n    conn = connect()\n    try:\n        sql = \"SELECT id,start_time,end_time FROM lessons WHERE lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')\"\n        params = []\n        if exclude_lesson_id is not None:\n            sql += \" AND id != ?\"\n            params.append(int(exclude_lesson_id))\n        rows = conn.execute(sql, params).fetchall()\n    finally:\n        conn.close()\n    return any(start < parsed(row[\"end_time\"]) and parsed(row[\"start_time\"]) < end for row in rows)"},{"path":"final_features/slot_change.py","name":"find_occupant","old":"def find_occupant(start_dt: datetime, end_dt: datetime, exclude_lesson_id=None, exclude_lesson_ids=None):\n    c = database.connect()\n    marks = \",\".join(\"?\" for _ in ACTIVE_STATUSES)\n    params = [*ACTIVE_STATUSES, _iso(end_dt), _iso(start_dt)]\n    sql = f\"\"\"\n      SELECT * FROM lessons\n      WHERE lesson_status IN ({marks})\n        AND start_time < ?\n        AND end_time > ?\n    \"\"\"\n    excluded=set(int(x) for x in (exclude_lesson_ids or []) if x is not None)\n    if exclude_lesson_id is not None:excluded.add(int(exclude_lesson_id))\n    if excluded:\n        placeholders=','.join('?' for _ in excluded)\n        sql += f\" AND id NOT IN ({placeholders})\"\n        params.extend(sorted(excluded))\n    sql += \" ORDER BY start_time LIMIT 1\"\n    row = c.execute(sql, params).fetchone()\n    c.close()\n    return row","new":"def find_occupant(start_dt: datetime, end_dt: datetime, exclude_lesson_id=None, exclude_lesson_ids=None):\n    \"\"\"Find an actual overlap; touching endpoints are available.\"\"\"\n    from core.lesson_time import lesson_timezone\n    tz = lesson_timezone()\n\n    def parsed(raw):\n        value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))\n        return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)\n\n    start, end = parsed(start_dt), parsed(end_dt)\n    if end <= start:\n        raise ValueError('invalid_interval')\n    excluded = {int(x) for x in (exclude_lesson_ids or []) if x is not None}\n    if exclude_lesson_id is not None:\n        excluded.add(int(exclude_lesson_id))\n    c = database.connect()\n    try:\n        marks = \",\".join(\"?\" for _ in ACTIVE_STATUSES)\n        rows = c.execute(f\"SELECT * FROM lessons WHERE lesson_status IN ({marks})\", ACTIVE_STATUSES).fetchall()\n    finally:\n        c.close()\n    hits = [r for r in rows if int(r['id']) not in excluded\n            and start < parsed(r['end_time']) and parsed(r['start_time']) < end]\n    return min(hits, key=lambda r: (parsed(r['start_time']), int(r['id']))) if hits else None"}]
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


def patch_availability(source):
 for old,new in [(OLD_DT,NEW_DT),(OLD_SQL,NEW_SQL),(OLD_RETURN,NEW_RETURN)]:
  if new in source:
   if source.count(new)!=1:raise RuntimeError('Ambiguous patched source')
  elif source.count(old)==1:source=source.replace(old,new)
  else:raise RuntimeError('Unexpected availability source; no files changed')
 compile(source,'web_backend/availability_guard.py','exec')
 return source


def patch_function(source, item):
 tree=ast.parse(source)
 node=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==item['name']),None)
 if node is None:raise RuntimeError('Missing function: '+item['name'])
 lines=source.splitlines(keepends=True)
 actual=''.join(lines[node.lineno-1:node.end_lineno]).rstrip()
 signature=lambda text:ast.dump(ast.parse(text),include_attributes=False)
 if signature(actual)==signature(item['new']):return source
 if signature(actual)!=signature(item['old']):raise RuntimeError('Unexpected function: '+item['name'])
 lines[node.lineno-1:node.end_lineno]=[item['new']+'\n']
 result=''.join(lines);compile(result,item['path'],'exec')
 return result


TEACHER_LOAD_OLD = "  async function load() {\n    const response = await fetch('/api/teacher/display-timezone', { credentials: 'same-origin', cache: 'no-store' });\n    if (response.status === 401) return;\n    if (!response.ok) throw new Error('timezone_unavailable');\n    changed((await response.json()).timezone);\n  }"
TEACHER_LOAD_NEW = "  let loading = null;\n  function load() {\n    if (loading) return loading;\n    const ctrl = new AbortController();\n    let timer;\n    const expired = new Promise((_, reject) => {\n      timer = setTimeout(() => { ctrl.abort(); reject(new Error('NETWORK_TIMEOUT')); }, 12000);\n    });\n    const request = (async () => {\n      const response = await fetch('/api/teacher/display-timezone', { credentials: 'same-origin', cache: 'no-store', signal: ctrl.signal });\n      if (response.status === 401) return;\n      if (!response.ok) throw new Error('timezone_unavailable');\n      const data = await response.json();\n      if (ctrl.signal.aborted) throw new Error('NETWORK_TIMEOUT');\n      if (!data?.timezone?.zone) throw new Error('timezone_unavailable');\n      changed(data.timezone);\n    })();\n    loading = Promise.race([request, expired]).catch(error => {\n      if (error?.name === 'AbortError') throw new Error('NETWORK_TIMEOUT');\n      throw error;\n    }).finally(() => { clearTimeout(timer); loading = null; });\n    return loading;\n  }"
TEACHER_OLD_WATCHDOG = "<script>\nwindow.addEventListener('load',()=>setTimeout(()=>{\n  const root=document.querySelector('#app');\n  if(!root||!root.querySelector(':scope > .loading'))return;\n  root.innerHTML='<section class=\"error\"><b>Кабинет не загрузился</b><p>Аделия не получила ответ от интерфейса преподавателя. Обновите страницу и попробуйте ещё раз.</p><button class=\"soft\" type=\"button\" id=\"teacherBootRetry\">Повторить</button></section>';\n  document.querySelector('#teacherBootRetry')?.addEventListener('click',()=>location.reload());\n},15000));\n</script>"
TEACHER_BOOT_GUARD = "/* Embedded before stylesheets so stalled defer scripts cannot block recovery. */\n(() => {\n  'use strict';\n  if (window.AdeliaTeacherBootGuard) return;\n  window.AdeliaTeacherBootGuard = true;\n  const failed = new Set();\n  window.addEventListener('error', event => {\n    const raw = event.target?.src || event.target?.href;\n    if (!raw) return;\n    try {\n      const url = new URL(raw, location.origin);\n      if (url.origin === location.origin) failed.add(url.pathname.split('/').pop());\n    } catch (_) {}\n  }, true);\n  setTimeout(() => {\n    const root = document.querySelector('#app');\n    if (!root || !root.querySelector(':scope > .loading')) return;\n    root.innerHTML = '<section class=\"error\" style=\"padding:24px;background:#fff;border:1px solid #ded6ed;border-radius:18px;font:16px system-ui;color:#282132\"><b>Не удалось завершить загрузку кабинета</b><p>Проверьте соединение и повторите загрузку. Если проблема повторится, передайте преподавателю результат проверки ниже.</p><p data-boot-details role=\"status\"></p><div style=\"display:flex;gap:12px;flex-wrap:wrap\"><button type=\"button\" data-boot-check>Проверить соединение</button><button type=\"button\" data-boot-reload>Обновить файлы кабинета</button></div></section>';\n    const panel = root.firstElementChild;\n    const details = panel.querySelector('[data-boot-details]');\n    details.textContent = failed.size ? 'Не загрузились файлы: ' + [...failed].join(', ') : 'Загрузка интерфейса или данных не завершилась.';\n    panel.querySelector('[data-boot-check]').onclick = async event => {\n      const button = event.currentTarget;\n      button.disabled = true;\n      const ctrl = new AbortController();\n      let timer;\n      try {\n        const request = (async () => {\n          const response = await fetch('/api/health', { cache: 'no-store', credentials: 'same-origin', signal: ctrl.signal });\n          const data = await response.json();\n          if (!response.ok || data.ok !== true) throw new Error('health_failed');\n        })();\n        await Promise.race([request, new Promise((_, reject) => { timer = setTimeout(() => { ctrl.abort(); reject(new Error('timeout')); }, 5000); })]);\n        details.textContent = 'Сервер отвечает. ' + (failed.size ? 'Не загрузились файлы: ' + [...failed].join(', ') : 'Нужно повторить загрузку кабинета.');\n      } catch (_) { details.textContent = 'Проверка соединения с сервером не прошла. Попробуйте другую сеть и повторите проверку.'; }\n      finally { clearTimeout(timer); button.disabled = false; }\n    };\n    panel.querySelector('[data-boot-reload]').onclick = async event => {\n      event.currentTarget.disabled = true;\n      try {\n        if ('caches' in window) for (const name of await caches.keys()) {\n          if (!name.startsWith('adelia-')) continue;\n          const cache = await caches.open(name);\n          for (const request of await cache.keys()) {\n            const url = new URL(request.url);\n            if (url.origin === location.origin && (/^\\/app\\/teacher(?:[_.-]|\\/)/.test(url.pathname) || url.pathname === '/teacher/')) await cache.delete(request);\n          }\n        }\n      } catch (_) {}\n      const url = new URL(location.href);\n      url.searchParams.set('boot_refresh', String(Date.now()));\n      location.replace(url.href);\n    };\n  }, 18000);\n})();"

QUARTER_REPLACEMENTS = {"bot.py":[["SLOT_STEP_MINUTES = 30","SLOT_STEP_MINUTES = 15"]],"database.py":[["    step_minutes=30,","    step_minutes=15,"]],"web_backend/public_trial_slots.py":[["STEP_MINUTES = 30","STEP_MINUTES = 15"]],"web_backend/student_booking.py":[["STEP_MINUTES = 30","STEP_MINUTES = 15"]],"web_backend/onboarding_schedule_options.py":[["STEP_MINUTES = 30","STEP_MINUTES = 15"]],"final_features/slot_change.py":[["    for _ in range(9):","    for _ in range(17):"],["        candidate += timedelta(minutes=30)","        candidate += timedelta(minutes=15)"]],"web/student_self_service.js":[["step=\"1800\"","step=\"900\""]],"web/lesson/lesson_reschedule_plus.js":[["step=\"1800\"","step=\"900\""],["с шагом 30 минут","с шагом 15 минут"]],"web/lesson/index.html":[["student_self_service.js?v=20260915-lesson-rsvp","student_self_service.js?v=20261022-quarter1"],["lesson_reschedule_plus.js?v=20260917-move1","lesson_reschedule_plus.js?v=20261022-quarter1"]]}

def prepare(release):
 updated={}
 for item in PATCHES:
  target=release/item['path']
  if target.is_symlink() or not target.is_file():raise RuntimeError('Unexpected source path')
  source=target.read_text()
  updated[item['path']]=patch_function(source,item).encode()
 target=release/'web_backend/availability_guard.py'
 updated['web_backend/availability_guard.py']=patch_availability(target.read_text()).encode()
 target=release/'final_features/handlers.py'
 source=target.read_text()
 for field in ('day_s','start_s'):
  old=f"_,_,lid_s,{field}=d.split('|',3)"
  new=f"_,lid_s,{field}=d.split('|',2)"
  if source.count(new)==1 and old not in source:continue
  if source.count(old)!=1 or new in source:raise RuntimeError('Unexpected Telegram callback source')
  source=source.replace(old,new)
 compile(source,str(target),'exec')
 updated['final_features/handlers.py']=source.encode()
 target=release/'web/teacher_time.js'
 source=target.read_text()
 if TEACHER_LOAD_NEW not in source:
  if source.count(TEACHER_LOAD_OLD)!=1:raise RuntimeError('Unexpected teacher timezone loader')
  source=source.replace(TEACHER_LOAD_OLD,TEACHER_LOAD_NEW)
 updated['web/teacher_time.js']=source.encode()
 target=release/'web/teacher.html'
 source=target.read_text()
 if 'data-adelia-boot-guard="20261022"' not in source:
  if source.count(TEACHER_OLD_WATCHDOG)!=1:raise RuntimeError('Unexpected teacher boot guard')
  source=source.replace(TEACHER_OLD_WATCHDOG,'')
  marker='<meta charset="utf-8">'
  if source.count(marker)!=1:raise RuntimeError('Unexpected teacher HTML header')
  source=source.replace(marker,marker+'<script data-adelia-boot-guard="20261022">'+TEACHER_BOOT_GUARD+'</script>')
 import re
 source,count=re.subn(r'teacher_time\.js\?v=[^"]+','teacher_time.js?v=20261022-boot1',source)
 if count!=1:raise RuntimeError('Unexpected teacher time asset reference')
 updated['web/teacher.html']=source.encode()
 for relative,pairs in QUARTER_REPLACEMENTS.items():
  source=updated[relative].decode() if relative in updated else (release/relative).read_text()
  for old,new in pairs:
   if source.count(new)==1 and old not in source:continue
   if source.count(old)!=1 or new in source:raise RuntimeError('Unexpected 15-minute slot source: '+relative)
   source=source.replace(old,new)
  if relative.endswith('.py'):compile(source,relative,'exec')
  updated[relative]=source.encode()
 return updated


def install():
 if os.geteuid()!=0:raise SystemExit('Run on the Ubuntu server as root')
 with open('/run/adelia-learning-deploy.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  release=Path('/opt/adelia-current').resolve(strict=True)
  if release.parent!=Path('/opt/adelia-releases'):raise RuntimeError('Unexpected release path')
  units=['tutorbot-web','tutorbot','tutorbot-vk']
  web_pid=None
  for unit in units:
   pid=int(subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip())
   if pid<1 or Path(f'/proc/{pid}/cwd').resolve()!=release:raise RuntimeError('Unexpected runtime: '+unit)
   if unit=='tutorbot-web':web_pid=pid
  updated=prepare(release)
  originals={}
  for relative in updated:
   path=release/relative
   if path.is_symlink() or path.resolve().parent!=(release/relative).parent:raise RuntimeError('Unexpected source link')
   originals[relative]=path.read_bytes()
  changed=[p for p in updated if updated[p]!=originals[p]]
  backups=Path('/opt/tutorbot/backups');backups.mkdir(exist_ok=True)
  backup=Path(tempfile.mkdtemp(prefix='adjacent-booking-20261022-',dir=backups));os.chmod(backup,0o700)
  candidates=backup/'candidate';candidates.mkdir()
  for relative,data in updated.items():
   saved=backup/'original'/relative;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(release/relative,saved)
   candidate=candidates/relative;candidate.parent.mkdir(parents=True,exist_ok=True);candidate.write_bytes(data)
  env=dict(os.environ)
  for item in Path(f'/proc/{web_pid}/environ').read_bytes().split(b'\0'):
   if b'=' in item:
    key,value=item.split(b'=',1);env[os.fsdecode(key)]=os.fsdecode(value)
  db=Path(env.get('ADELIA_DB_PATH','/opt/tutorbot/tutor.db')).resolve()
  if db!=Path('/opt/tutorbot/tutor.db'):raise RuntimeError('Unexpected database path')
  dbcopy=backup/'preflight.db'
  with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as src:
   with sqlite3.connect(dbcopy) as dst:src.backup(dst)
  env['ADELIA_DB_PATH']=str(dbcopy);env['PYTHONDONTWRITEBYTECODE']='1'
  smoke='''import ast,importlib.util,sys
from pathlib import Path
import database
root=Path(sys.argv[1]);database.DB_NAME=sys.argv[2]
tree=ast.parse((root/'database.py').read_text())
for name in ('is_slot_reserved','get_regular_recurring_slots'):
 node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
 exec(compile(ast.Module(body=[node],type_ignores=[]),'database.py','exec'),database.__dict__)
spec=importlib.util.spec_from_file_location('web_backend.availability_guard',root/'web_backend/availability_guard.py')
guard=importlib.util.module_from_spec(spec);sys.modules[spec.name]=guard;spec.loader.exec_module(guard)
spec=importlib.util.spec_from_file_location('web_backend.public_trial_slots',root/'web_backend/public_trial_slots.py')
slots=importlib.util.module_from_spec(spec);sys.modules[spec.name]=slots;spec.loader.exec_module(slots)
feed=slots.feed
assert slots.STEP_MINUTES==15
for relative,name in [('bot.py','SLOT_STEP_MINUTES'),('web_backend/student_booking.py','STEP_MINUTES'),('web_backend/onboarding_schedule_options.py','STEP_MINUTES')]:
 nodes=ast.parse((root/relative).read_text()).body
 assignment=next(n for n in nodes if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
 assert ast.literal_eval(assignment.value)==15
for zone in ('Europe/Moscow','Europe/Samara','Asia/Yekaterinburg'):
 result=feed(zone,days=14,duration_minutes=60)
 assert isinstance(result.get('items'),list)
assert isinstance(database.is_slot_reserved('2099-01-01T18:30','2099-01-01T19:30'),bool)
print('REAL_DB_COPY_PREFLIGHT=OK')
'''
  subprocess.run(['/opt/tutorbot/venv/bin/python','-c',smoke,str(candidates),str(dbcopy)],cwd=release,env=env,check=True,timeout=90)

  def replace(relative,data):
   target=release/relative
   fd,name=tempfile.mkstemp(prefix='.adjacent-hotfix-',dir=target.parent)
   try:
    with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    shutil.copystat(target,name);st=target.stat();os.chown(name,st.st_uid,st.st_gid);os.replace(name,target)
   finally:
    if os.path.exists(name):os.unlink(name)

  try:
   for relative in changed:replace(relative,updated[relative])
   # Restart even after a prior interrupted installation to reload all workers.
   subprocess.run(['systemctl','restart',*units],check=True,timeout=90)
   for _ in range(20):
    try:
     with urllib.request.urlopen('http://127.0.0.1:8876/api/public/trial/slots?timezone=Europe%2FMoscow&days=14&duration_minutes=60',timeout=10) as response:result=json.load(response)
     if not isinstance(result.get('items'),list):raise RuntimeError('Invalid public slot response')
     for unit in units:subprocess.run(['systemctl','is-active','--quiet',unit],check=True)
     break
    except Exception:time.sleep(1)
   else:raise RuntimeError('Public slot API or services did not recover')
   for relative in ('web/teacher.html','web/teacher_time.js','web/lesson/index.html','web/lesson/lesson_reschedule_plus.js','web/student_self_service.js'):
    route='/app/'+relative.removeprefix('web/')+'?v=20261022-quarter1'
    served=subprocess.check_output(['curl','--resolve','adeliatutor.ru:443:127.0.0.1','--max-time','15','-fsS','https://adeliatutor.ru'+route],timeout=20)
    if served!=updated[relative]:raise RuntimeError('Nginx did not serve the updated teacher asset: '+relative)
  except BaseException:
   for relative in changed:replace(relative,originals[relative])
   subprocess.run(['systemctl','restart',*units],check=False,timeout=90)
   print('HOTFIX_FAILED; original files restored. Backup:',backup);raise
  print('ADJACENT_BOOKING_HOTFIX_OK')
  print('Public slot API: HTTP 200')
  print('Teacher boot assets: OK')
  print('Quarter-hour start grid: 15 minutes')
  print('Backup:',backup)


if __name__=='__main__':install()
