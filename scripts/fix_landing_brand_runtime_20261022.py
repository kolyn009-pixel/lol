"""Repair the legacy logo rewrite in the served homepage JavaScript."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

VERSION='20261022-brand-runtime1'
OLD='''function ensureBrandAssets(){const icon='/app/assets/icons/adelia-icon.svg';document.querySelectorAll('link[rel~="icon"],link[rel="apple-touch-icon"]').forEach(x=>x.href=icon);document.querySelectorAll('header .brand img,footer .brand img').forEach(x=>{x.src=icon;x.removeAttribute('srcset')})}'''


def patch_script(source,helper):
    helper=helper.strip()
    if helper in source:return source
    if source.count(OLD)==1:return source.replace(OLD,helper,1)
    if 'ensureBrandAssets' in source:raise RuntimeError('Unrecognized branding function; original files preserved')
    return helper+'\nensureBrandAssets();\n'+source


def patch_html(source):
    pattern=r'(["\'])(/landing\.js)(?:\?[^"\']*)?\1'
    source,count=re.subn(pattern,lambda m:m[1]+m[2]+'?v='+VERSION+m[1],source)
    if count!=1:raise RuntimeError('Expected one homepage script; original files preserved')
    return source


def atomic(path,data,stat):
    fd,tmp=tempfile.mkstemp(prefix='.adelia-brand-runtime-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.chmod(tmp,stat.st_mode&0o777);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def install(commit):
    if os.geteuid()!=0:raise SystemExit('Run on the server as root')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise SystemExit('A pinned commit is required')
    with open('/run/adelia-learning-deploy.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        public=Path('/var/www/adeliatutor.ru');release=Path('/opt/adelia-current').resolve()
        if public.resolve()!=public or release.parent!=Path('/opt/adelia-releases'):raise RuntimeError('Unexpected site roots')
        roots=[public,release/'web',Path('/opt/tutorbot/web')]
        def target(p):
            physical=p.resolve(strict=True)
            if not any(physical.is_relative_to(root) for root in roots):raise RuntimeError('Unexpected linked target: '+str(p))
            if not physical.is_file():raise RuntimeError('Expected a regular file: '+str(p))
            return physical
        helper=subprocess.check_output(['git','-C','/opt/tutorbot','show',commit+':web/landing_brand.js'],text=True)
        js=target(public/'landing.js');html=target(public/'index.html')
        updates={js:patch_script(js.read_text(),helper).encode(),html:patch_html(html.read_text()).encode()}
        def get(path):return subprocess.check_output(['curl','--resolve','adeliatutor.ru:443:127.0.0.1','--max-time','12','-fsS','https://adeliatutor.ru'+path],timeout=15)
        for size in (32,180,192):
            png=get('/app/assets/icons/adelia-mark-'+str(size)+'.png?v=20261022-unified2')
            if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png)<24 or int.from_bytes(png[16:20],'big')!=size:raise RuntimeError('Canonical PNG is unavailable: '+str(size))
        root=Path('/opt/tutorbot/backups');root.mkdir(exist_ok=True)
        backup=Path(tempfile.mkdtemp(prefix='landing-brand-runtime-20261022-',dir=root));os.chmod(backup,0o700)
        original={};manifest=[]
        for i,p in enumerate(updates):
            original[p]=p.stat();shutil.copy2(p,backup/str(i));manifest.append({'path':str(p),'saved':str(i)})
        (backup/'files.json').write_text(json.dumps(manifest))
        (backup/'rollback.sh').write_text('''#!/bin/bash
set -euo pipefail
python3 - "$0" <<'PY'
import json,os,shutil,sys,tempfile
from pathlib import Path
b=Path(sys.argv[1]).parent
for item in json.loads((b/'files.json').read_text()):
 p=Path(item['path']);saved=b/item['saved'];fd,tmp=tempfile.mkstemp(dir=p.parent);os.close(fd);shutil.copy2(saved,tmp);s=saved.stat();os.chown(tmp,s.st_uid,s.st_gid);os.replace(tmp,p)
print('LANDING_BRAND_RUNTIME_ROLLBACK_OK')
PY
''');os.chmod(backup/'rollback.sh',0o700)
        written=[]
        try:
            for p,data in updates.items():atomic(p,data,original[p]);written.append(p)
            if get('/landing.js?v='+VERSION)!=updates[js]:raise RuntimeError('Served homepage script mismatch')
            if get('/')!=updates[html]:raise RuntimeError('Served homepage HTML mismatch')
        except BaseException:
            for p in reversed(written):atomic(p,(backup/str(list(updates).index(p))).read_bytes(),original[p])
            print('LANDING_BRAND_RUNTIME_FAILED; original files restored. Backup:',backup);raise
        print('LANDING_BRAND_RUNTIME_OK')
        print('Legacy SVG rewrite replaced with canonical PNG and ICO URLs')
        print('Backup:',backup)
        print('Rollback: bash',backup/'rollback.sh')


if __name__=='__main__':install(sys.argv[1])
