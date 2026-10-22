"""Install the group interface only; no database changes or service restarts."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

VERSION='20261022-group-design1'


def page(source):
    pattern=r'(["\'])/app/teacher_group_settings\.js(?:\?[^"\']*)?\1'
    source,count=re.subn(pattern,'"/app/teacher_group_settings.js?v='+VERSION+'"',source)
    if count!=1:raise RuntimeError('Expected one group settings script; no files changed')
    tag='<link id="adeliaGroupSettingsStyle" rel="stylesheet" href="/app/teacher_group_settings.css?v='+VERSION+'">'
    if 'id="adeliaGroupSettingsStyle"' in source:
        source=re.sub(r'<link\b[^>]*id="adeliaGroupSettingsStyle"[^>]*>',tag,source)
    else:
        if source.count('</head>')!=1:raise RuntimeError('Unexpected teacher page head')
        source=source.replace('</head>',tag+'</head>',1)
    return source


def atomic(path,data,stat=None):
    fd,tmp=tempfile.mkstemp(prefix='.adelia-group-design-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(data)
        os.chmod(tmp,stat.st_mode&0o777 if stat else 0o644)
        if stat:os.chown(tmp,stat.st_uid,stat.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def install(commit):
    if os.geteuid()!=0:raise SystemExit('Run on the server as root')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise SystemExit('A full pinned commit is required')
    with open('/run/adelia-learning-deploy.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        release=Path('/opt/adelia-current').resolve()
        if release.parent!=Path('/opt/adelia-releases'):raise RuntimeError('Unexpected active release')
        web=release/'web'
        if not (web/'teacher_group_settings.js').is_file():raise RuntimeError('Install group settings and invitations first')
        def git(ref,p):return subprocess.check_output(['git','-C','/opt/tutorbot','show',ref+':'+p])
        updates={p:git(commit,'web/'+p) for p in ['teacher_group_settings.js','teacher_group_settings.css']}
        live=(web/'teacher_group_settings.js').read_bytes()
        known=[updates['teacher_group_settings.js']]
        for ref in ['8e3c74effd0656307430e9b2fb48482b398fb86a','abb78a17b084e8b6400e27e4da56e13cda93f515']:
            known.append(git(ref,'web/teacher_group_settings.js'))
        if live not in known:raise RuntimeError('Group settings script has unknown edits; original files preserved')
        updates['teacher.html']=page((web/'teacher.html').read_text()).encode()
        for p in updates:
            path=web/p
            if path.is_symlink() or path.parent.resolve()!=path.parent:raise RuntimeError('Unexpected asset symlink: '+p)
        root=Path('/opt/tutorbot/backups');root.mkdir(exist_ok=True)
        backup=Path(tempfile.mkdtemp(prefix='group-design-20261022-',dir=root));os.chmod(backup,0o700)
        original={}
        for p in updates:
            original[p]=(web/p).stat() if (web/p).exists() else None
            if original[p]:shutil.copy2(web/p,backup/p)
        (backup/'files.json').write_text(json.dumps({'web':str(web),'files':{p:bool(s) for p,s in original.items()}}))
        (backup/'rollback.sh').write_text('''#!/bin/bash
set -euo pipefail
python3 - "$0" <<'PY'
import json,sys,os,shutil,tempfile
from pathlib import Path
b=Path(sys.argv[1]).parent;m=json.loads((b/'files.json').read_text());web=Path(m['web'])
for name,existed in m['files'].items():
 p=web/name
 if existed:
  fd,tmp=tempfile.mkstemp(dir=web);os.close(fd);shutil.copy2(b/name,tmp);s=(b/name).stat();os.chown(tmp,s.st_uid,s.st_gid);os.replace(tmp,p)
 else:p.unlink(missing_ok=True)
print('GROUP_DESIGN_ROLLBACK_OK')
PY
''');os.chmod(backup/'rollback.sh',0o700)
        written=[]
        try:
            for p,data in updates.items():atomic(web/p,data,original[p]);written.append(p)
            for p,data in updates.items():
                response=subprocess.check_output(['curl','--resolve','adeliatutor.ru:443:127.0.0.1','--max-time','12','-fsS','https://adeliatutor.ru/app/'+p+'?v='+VERSION],timeout=15)
                if response!=data:raise RuntimeError('Served file mismatch: '+p)
        except BaseException:
            for p in reversed(written):
                if original[p]:atomic(web/p,(backup/p).read_bytes(),original[p])
                else:(web/p).unlink(missing_ok=True)
            print('GROUP_DESIGN_FAILED; original files restored. Backup:',backup);raise
        print('GROUP_DESIGN_OK')
        print('Tabs: settings, schedule, members, invitation')
        print('Backup:',backup)
        print('Rollback: bash',backup/'rollback.sh')


if __name__=='__main__':install(sys.argv[1])
