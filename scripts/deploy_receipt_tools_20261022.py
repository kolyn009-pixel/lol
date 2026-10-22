"""Deploy backdated receipt review and local OCR without changing payment crediting rules."""
import ast
import difflib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE='e1bcfcaf3c1fab94c69839f70bb7ca7cfca873bf'
PATCHED=['web_backend/api_v7.py']
ADDED=['web_backend/receipt_review_tools.py','web_backend/receipt_tools_api.py',
 'web/teacher_receipt_review_tools.js','web/teacher_receipt_review_tools.css']
VERSION='20261022-receipt-tools1'



def delta(live, old, new, label):
    if live == new: return live
    a=old.splitlines(keepends=True);b=new.splitlines(keepends=True)
    for group in difflib.SequenceMatcher(None,a,b,autojunk=False).get_grouped_opcodes(2):
        before=''.join(a[group[0][1]:group[-1][2]])
        after=''.join(b[group[0][3]:group[-1][4]])
        if after in live: continue
        if not before or live.count(before)!=1:
            raise RuntimeError('Unrecognized live code; no files changed: '+label)
        live=live.replace(before,after,1)
    return live


def html_assets(text, scripts):
    for name in scripts:
        url='/app/'+name+'?v='+VERSION
        # Replace only existing references to the asset, preserving every other edit.
        pattern=r'(?P<quote>[\"\'])(?:/app/|/|\./)?'+re.escape(name)+r'(?:\?[^\"\']*)?(?P=quote)'
        text,count=re.subn(pattern,lambda m:m['quote']+url+m['quote'],text)
        if not count:
            if '</head>' not in text: raise RuntimeError('No HTML head for '+name)
            text=text.replace('</head>','<script defer src="'+url+'"></script></head>',1)
    return text


def atomic(path, data, old=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.adelia-groups-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.chmod(name,(old.st_mode & 0o777) if old else 0o644)
        if old:os.chown(name,old.st_uid,old.st_gid)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def install(commit):
    if os.geteuid()!=0: raise SystemExit('Run on the server as root')
    if not re.fullmatch('[0-9a-f]{40}',commit): raise SystemExit('A full pinned commit is required')
    with open('/run/adelia-learning-deploy.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        release=Path('/opt/adelia-current').resolve()
        if release.parent!=Path('/opt/adelia-releases'):raise RuntimeError('Unexpected active release')
        pid=int(subprocess.check_output(['systemctl','show','tutorbot-web','-p','MainPID','--value'],text=True).strip())
        if pid<=0 or Path(f'/proc/{pid}/cwd').resolve()!=release:raise RuntimeError('Web service release mismatch')
        env=dict(os.environ)
        for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
            if b'=' in item:
                key,value=item.split(b'=',1);env[os.fsdecode(key)]=os.fsdecode(value)
        db=Path(env.get('ADELIA_DB_PATH','/opt/tutorbot/tutor.db')).resolve()
        if db!=Path('/opt/tutorbot/tutor.db'):raise RuntimeError('Unexpected production database')
        def git(ref,path):return subprocess.check_output(['git','-C','/opt/tutorbot','show',ref+':'+path])
        updates={p:git(commit,p) for p in ADDED}
        for p in PATCHED:
            updates[p]=delta((release/p).read_text(),git(BASE,p).decode(),git(commit,p).decode(),p).encode()
        html={'web/teacher.html':['teacher_receipt_review_tools.js']}
        for p,scripts in html.items():
            text=html_assets((release/p).read_text(),scripts)
            if 'teacher_receipt_review_tools.css' not in text:text=text.replace('</head>','<link rel="stylesheet" href="/app/teacher_receipt_review_tools.css?v='+VERSION+'"></head>',1)
            updates[p]=text.encode()
        for p,data in updates.items():
            path=release/p
            if path.is_symlink() or path.parent.resolve()!=path.parent:raise RuntimeError('Unexpected code symlink: '+p)
            if p.endswith('.py'):ast.parse(data,filename=p)
        Path('/opt/tutorbot/backups').mkdir(parents=True,exist_ok=True)
        backup=Path(tempfile.mkdtemp(prefix='receipt-tools-20261022-',dir='/opt/tutorbot/backups'));os.chmod(backup,0o700)
        original={}
        for p in updates:
            source=release/p;original[p]=source.stat() if source.exists() else None
            if source.exists():
                saved=backup/'original'/p;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,saved)
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as src:
            with sqlite3.connect(backup/'database.db') as dest:src.backup(dest)
        overlay=backup/'candidate';(overlay/'web_backend').mkdir(parents=True)
        (overlay/'web_backend/__init__.py').write_text('__path__='+repr([str(overlay/'web_backend'),str(release/'web_backend')]))
        for p in updates:
            if p.startswith('web_backend/') and p.endswith('.py'):(overlay/p).write_bytes(updates[p])
        smoke='''import sys,threading,urllib.request,urllib.error
sys.path[:0]=[sys.argv[1],sys.argv[2]]
from web_backend import api_v7,receipt_review_tools
from http.server import ThreadingHTTPServer
receipt_review_tools.ensure_schema()
server=ThreadingHTTPServer(('127.0.0.1',0),api_v7.Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
for path,expected in [('/api/teacher/finance/receipt/details?payment_id=1',401),('/api/teacher/group/chat?group_id=1',401)]:
 try: response=urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+path,timeout=8);status=response.status
 except urllib.error.HTTPError as error:status=error.code
 assert status==expected,(path,status)
server.shutdown();server.server_close()
print('REAL_DB_COPY_AND_API_PREFLIGHT=OK')
'''
        preflight_env={**env,'ADELIA_DB_PATH':str(backup/'database.db'),'PYTHONDONTWRITEBYTECODE':'1'}
        subprocess.run(['/opt/tutorbot/venv/bin/python','-c',smoke,str(overlay),str(release)],cwd=release,env=preflight_env,check=True,timeout=60)
        # Exercise the server's actual payment implementation on a fresh temp DB.
        # The test disables review notifications and never opens the live DB.
        tests=overlay/'scripts';tests.mkdir()
        selftest=tests/'receipt_tools_selftest.py';selftest.write_bytes(git(commit,'scripts/receipt_tools_selftest.py'))
        subprocess.run(['/opt/tutorbot/venv/bin/python',str(selftest)],cwd=release,
          env={**preflight_env,'PYTHONPATH':str(overlay)+os.pathsep+str(release)},check=True,timeout=60)
        # Exact file rollback; additive invitation tables can safely remain.
        manifest={'release':str(release),'files':{p:bool(stat) for p,stat in original.items()}}
        (backup/'files.json').write_text(json.dumps(manifest))
        rollback='''#!/bin/bash
set -euo pipefail
python3 - "$0" <<'PY'
import json,sys,shutil,os,tempfile
from pathlib import Path
b=Path(sys.argv[1]).parent;m=json.loads((b/'files.json').read_text());root=Path(m['release'])
for rel,existed in m['files'].items():
 p=root/rel
 if existed:
  fd,tmp=tempfile.mkstemp(dir=p.parent);os.close(fd);shutil.copy2(b/'original'/rel,tmp);s=(b/'original'/rel).stat();os.chown(tmp,s.st_uid,s.st_gid);os.replace(tmp,p)
 else:p.unlink(missing_ok=True)
PY
systemctl restart tutorbot-web
'''
        (backup/'rollback.sh').write_text(rollback);os.chmod(backup/'rollback.sh',0o700)
        changed=[]
        try:
            for p,data in updates.items():atomic(release/p,data,original[p]);changed.append(p)
            migrate="import sys;sys.path[:0]=[sys.argv[1],sys.argv[2]];from web_backend import receipt_review_tools;receipt_review_tools.ensure_schema()"
            subprocess.run(['/opt/tutorbot/venv/bin/python','-c',migrate,str(overlay),str(release)],cwd=release,env=env,check=True,timeout=30)
            subprocess.run(['systemctl','restart','tutorbot-web'],check=True,timeout=60)
            def code(path):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8876'+path,timeout=5) as r:return r.status
                except urllib.error.HTTPError as e:return e.code
            for attempt in range(20):
                try:
                    if code('/api/health')==200 and code('/api/teacher/group/chat?group_id=1')==401:break
                except (OSError,urllib.error.URLError):pass
                time.sleep(1)
            else:raise RuntimeError('Web API failed health checks')
            for p in [*html,'web/teacher_receipt_review_tools.js','web/teacher_receipt_review_tools.css']:
                route='/app/'+p.removeprefix('web/')
                served=subprocess.check_output(['curl','--resolve','adeliatutor.ru:443:127.0.0.1','--max-time','12','-fsS','https://adeliatutor.ru'+route+'?v='+VERSION],timeout=15)
                if served!=updates[p]:raise RuntimeError('Served asset mismatch: '+route)
        except BaseException:
            for p in reversed(changed):
                if original[p]:atomic(release/p,(backup/'original'/p).read_bytes(),original[p])
                else:(release/p).unlink(missing_ok=True)
            subprocess.run(['systemctl','restart','tutorbot-web'],check=False,timeout=60)
            print('RECEIPT_TOOLS_FAILED; original files restored. Backup:',backup);raise
        print('RECEIPT_TOOLS_OK')
        print('Factual payment dates and local receipt inspection: enabled')
        print('Local OCR:', 'ready' if shutil.which('tesseract') and shutil.which('pdftotext') else 'install tesseract-ocr tesseract-ocr-rus poppler-utils')
        print('Code:',commit)
        print('Backup:',backup)
        print('Rollback: bash',backup/'rollback.sh')


if __name__=='__main__':install(sys.argv[1])
