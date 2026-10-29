"""Add the olympiad module without replacing production HTML/API customizations.

Run from an isolated checkout on the server. Default mode is a read-only plan.
An apply backs up every modified file and rolls back on failed health checks.
"""
import argparse
import ast
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

FILES=['web_backend/olympiad_journey.py','web_backend/olympiad_store.py','web_backend/olympiad_sources.py',
       'web_backend/olympiad_api.py','web_backend/olympiad_worker.py',
       'data/olympiads_2026_2027.json','web/olympiads.js','web/olympiads.css']
RECORD='olympiads_install.json'
MARKER='# ADELIA OLYMPIAD ROUTES 20261029'


def hook_api(text):
    if MARKER in text:
        required=['OlympiadMixin','OLYMPIAD_GET','OLYMPIAD_POST',
                  'if path in OLYMPIAD_GET:return self.olympiad_get(path,q)',
                  'if path in OLYMPIAD_POST:return self.olympiad_post(path)']
        if not all(s in text for s in required):raise RuntimeError('Existing olympiad hook needs review')
        return text
    tree=ast.parse(text)
    cls=next((n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LearningHubMixin'),None)
    if not cls:raise RuntimeError('LearningHubMixin missing; no changes')
    functions={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
    if not {'learning_get','learning_post'}<=functions.keys():raise RuntimeError('Learning routes missing')
    if not {'GET_PATHS','POST_PATHS'}<=set(re.findall(r'^(\w+)\s*=',text,re.M)):
        raise RuntimeError('Learning route sets missing')
    lines=text.splitlines(keepends=True)
    for name,statement in sorted([
      ('learning_get','if path in OLYMPIAD_GET:return self.olympiad_get(path,q)'),
      ('learning_post','if path in OLYMPIAD_POST:return self.olympiad_post(path)')],
      key=lambda item:functions[item[0]].lineno,reverse=True):
        fn=functions[name]
        if fn.end_lineno==fn.lineno:raise RuntimeError('One-line learning handler unsupported')
        lines.insert(fn.lineno,' '*(fn.col_offset+4)+statement+'\n')
    text=''.join(lines)
    pattern=r'^class LearningHubMixin(?:\(([^\n]*)\))?:'
    match=re.search(pattern,text,re.M)
    if not match:raise RuntimeError('Learning class header needs review')
    bases='OlympiadMixin'+(','+match[1] if match[1] else '')
    text=text[:match.start()]+'class LearningHubMixin('+bases+'):'+text[match.end():]
    at=text.index('class LearningHubMixin(')
    block=(MARKER+'\nfrom web_backend.olympiad_api import OlympiadMixin, GET_PATHS as OLYMPIAD_GET, POST_PATHS as OLYMPIAD_POST\n'
           'GET_PATHS |= OLYMPIAD_GET\nPOST_PATHS |= OLYMPIAD_POST\n\n')
    text=text[:at]+block+text[at:]
    ast.parse(text)
    return text


def hook_html(text):
    if text.count('</head>')!=1:raise RuntimeError('HTML head needs review')
    for name,tag in [('olympiads.css','link'),('olympiads.js','script')]:
        if '/app/'+name in text:
            # Invalidate the browser cache while preserving the existing HTML tag.
            pattern=r'(/app/'+re.escape(name)+r')(?:\?[^\"\']*)?'
            text=re.sub(pattern,lambda m:m[1]+'?v=20261029-olympiads3',text)
            continue
        asset=('<link rel="stylesheet" href="/app/olympiads.css?v=20261029-olympiads3">'
               if tag=='link' else '<script defer src="/app/olympiads.js?v=20261029-olympiads3"></script>')
        text=text.replace('</head>',asset+'</head>',1)
    return text


def digest(data):return hashlib.sha256(data).hexdigest()

def health(url):
    for _ in range(20):
        try:
            result=subprocess.check_output(['curl','--noproxy','*','-fsS','--max-time','3',url.rstrip('/')+'/api/health'],stderr=subprocess.DEVNULL,timeout=4)
            if json.loads(result).get('ok') is True:return
        except (subprocess.SubprocessError,ValueError):pass
        time.sleep(1)
    raise RuntimeError('Web health check failed')


def monitoring_units(args,python):
    files=subprocess.check_output(['systemctl','show',args.service,'-p','EnvironmentFiles','--value'],text=True)
    env=[]
    for name,optional in re.findall(r'(/[^\s]+) \(ignore_errors=(yes|no)\)',files):
        if any(ch in name for ch in '\n\r"'):raise RuntimeError('Unsupported environment file name')
        env.append('EnvironmentFile='+('-' if optional=='yes' else '')+name)
    if not env:raise RuntimeError('Cannot locate web environment files; monitoring not installed')
    for value in (args.root,args.database,python):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+',value):raise RuntimeError('Unsupported service path')
    service='\n'.join([
      '# ADELIA OLYMPIADS MANAGED 20261029','[Unit]','Description=Adelia olympiad calendar and reminders',
      'After=network-online.target','Wants=network-online.target','[Service]','Type=oneshot',
      'WorkingDirectory='+args.root,*env,'Environment=ADELIA_DB_PATH='+args.database,
      'ExecStart='+python+' -m web_backend.olympiad_worker','TimeoutStartSec=1800',
      'UMask=0077','NoNewPrivileges=true','PrivateTmp=true',''])
    timer='\n'.join(['# ADELIA OLYMPIADS MANAGED 20261029','[Unit]',
      'Description=Check Adelia olympiad reminders hourly','[Timer]',
      'OnCalendar=hourly','OnBootSec=3min','Persistent=true','RandomizedDelaySec=120',
      'Unit=adelia-olympiads.service','[Install]','WantedBy=timers.target',''])
    return {Path('/etc/systemd/system/adelia-olympiads.service'):service.encode(),
            Path('/etc/systemd/system/adelia-olympiads.timer'):timer.encode()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default='/opt/adelia-current')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--service',default='tutorbot-web.service')
    parser.add_argument('--health-url',default='http://127.0.0.1:8876')
    parser.add_argument('--python')
    parser.add_argument('--database',default='/opt/tutorbot/tutor.db')
    parser.add_argument('--monitoring',action='store_true')
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[1];root=Path(args.root).resolve(strict=True)
    if source==root:raise RuntimeError('Use an isolated source checkout, not the active release')
    if not (root/'web/teacher.html').is_file() or not (root/'web_backend/learning_hub_api.py').is_file():
        raise RuntimeError('Active release layout missing')
    lock=open('/run/adelia-olympiads-install.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    originals={};candidate={}
    prior=json.loads((root/RECORD).read_text()) if (root/RECORD).exists() else {}
    for name in FILES:
        value=(source/name).read_bytes()
        live=(root/name).read_bytes() if (root/name).exists() else None
        if live is not None and live!=value and prior.get('hashes',{}).get(name)!=digest(live):
            raise RuntimeError('Local edits need review; no files changed: '+name)
        originals[name]=live;candidate[name]=value
    for name,hook in [('web_backend/learning_hub_api.py',hook_api),('web/teacher.html',hook_html),('web/index.html',hook_html)]:
        originals[name]=(root/name).read_bytes();candidate[name]=hook(originals[name].decode()).encode()
    for name,value in candidate.items():
        if name.endswith('.py'):ast.parse(value.decode(),filename=name)
    originals[RECORD]=(root/RECORD).read_bytes() if (root/RECORD).exists() else None
    candidate[RECORD]=(json.dumps({'version':1,'hashes':{k:digest(v) for k,v in candidate.items() if k in FILES}},indent=2)+'\n').encode()
    changed=[name for name,value in candidate.items() if value!=originals[name]]
    print(json.dumps({'mode':'apply' if args.apply else 'check','root':str(root),'changed_files':changed},ensure_ascii=False))
    if not args.apply or (not changed and not args.monitoring):return
    if os.geteuid()!=0:raise RuntimeError('Apply requires root')
    cwd=subprocess.check_output(['systemctl','show',args.service,'-p','WorkingDirectory','--value'],text=True).strip()
    if not cwd or Path(cwd).resolve()!=root:raise RuntimeError('Web service is using a different release; no files changed')
    if not Path(args.database).is_file():raise RuntimeError('Database path missing; no files changed')
    pid=subprocess.check_output(['systemctl','show',args.service,'-p','MainPID','--value'],text=True).strip()
    proc_env=Path('/proc/'+pid+'/environ').read_bytes().split(b'\0')
    configured=next((x.split(b'=',1)[1].decode() for x in proc_env if x.startswith(b'ADELIA_DB_PATH=')),str(root/'tutor.db'))
    if Path(configured).resolve()!=Path(args.database).resolve():raise RuntimeError('Web database differs from requested database; no files changed')
    command=subprocess.check_output(['systemctl','show',args.service,'-p','ExecStart','--value'],text=True)
    match=re.search(r'path=(/[^ ;]+)',command)
    python=args.python or (match[1] if match and Path(match[1]).name.startswith('python') else None)
    if not python or not Path(python).is_file():raise RuntimeError('Cannot identify web Python; use --python with its exact executable')
    units=monitoring_units(args,python) if args.monitoring else {}
    original_units={p:p.read_bytes() if p.exists() else None for p in units}
    for path,value in original_units.items():
        if value is not None and value!=units[path]:raise RuntimeError('Monitoring unit differs; no files changed: '+str(path))
    timer_enabled=subprocess.run(['systemctl','is-enabled','--quiet','adelia-olympiads.timer']).returncode==0 if units else False
    backup=Path('/opt/tutorbot/backups')/('olympiads-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True)
    for name in changed:
        if originals[name] is not None:
            dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(originals[name])
    (backup/'manifest.json').write_text(json.dumps({'root':str(root),'files':changed,'new_files':[n for n in changed if originals[n] is None]},indent=2))
    try:
        for name in changed:
            dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True)
            temp=dest.with_name(dest.name+'.olympiad-next');temp.write_bytes(candidate[name]);os.chmod(temp,0o644);os.replace(temp,dest)
        # Additive module tables only; lesson, payment and existing plan rows stay intact.
        subprocess.run([python,'-c','from web_backend.olympiad_sources import seed; seed()'],cwd=root,
                       env={**os.environ,'ADELIA_DB_PATH':args.database},check=True,timeout=60)
        subprocess.run(['systemctl','restart',args.service],check=True,timeout=60)
        health(args.health_url)
        # Assert the new endpoints are routed and deny unauthenticated access.
        for role in ('teacher','student'):
            code=subprocess.check_output(['curl','--noproxy','*','-s','-o','/dev/null','-w','%{http_code}',args.health_url.rstrip('/')+'/api/'+role+'/olympiads'],text=True,timeout=10)
            if code!='401':raise RuntimeError('Olympiad route check failed: '+role+' '+code)
        if units:
            for path,value in units.items():path.write_bytes(value)
            subprocess.run(['systemctl','daemon-reload'],check=True,timeout=30)
            subprocess.run(['systemctl','enable','--now','adelia-olympiads.timer'],check=True,timeout=30)
            subprocess.run(['systemctl','is-active','--quiet','adelia-olympiads.timer'],check=True,timeout=10)
    except Exception:
        if units:
            if not timer_enabled:subprocess.run(['systemctl','disable','--now','adelia-olympiads.timer'],timeout=30)
            for path,value in original_units.items():
                if value is None:path.unlink(missing_ok=True)
                else:path.write_bytes(value)
            subprocess.run(['systemctl','daemon-reload'],timeout=30)
        for name in reversed(changed):
            path=root/name
            if originals[name] is None:path.unlink(missing_ok=True)
            else:path.write_bytes(originals[name])
        subprocess.run(['systemctl','restart',args.service],timeout=60)
        raise
    print('OLYMPIADS_INSTALLED\nBackup: '+str(backup))
    print('OLYMPIAD_MONITORING_ENABLED' if units else 'Monitoring not enabled: rerun with --monitoring; see docs/olympiads.md.')

if __name__=='__main__':main()
