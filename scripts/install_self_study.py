"""Reviewable, additive self-study installer. Default: validate without writing.

Run from the downloaded feature checkout, targeting a DIFFERENT live checkout.
SQLite backup is retained for recovery; rollback restores code, never live data.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import urlopen

SOURCE=Path(__file__).resolve().parents[1]
MODULES=['learning/intensive_program.py','web/self_study_intensive.js','web_backend/self_study_preferences.py','web/self_study_settings.js','web_backend/self_study_access.py','learning/beginner_languages.py','learning/entry_diagnostic.py','web_backend/self_study_entry.py','web/self-study.html','learning/language_program.py','learning/language_checkpoints.py',
         'web_backend/self_study.py','web_backend/self_study_practice.py',
         'web_backend/self_study_feedback.py','web_backend/self_study_scenes.py',
         'web_backend/self_study_api.py','web/self_study.js','web/self_study.css',
         'web/self_study_voice.js','web/self_study_scenes.js']
IMPORT='from web_backend.self_study_api import SelfStudyMixin, GET_PATHS as SELF_STUDY_GET, POST_PATHS as SELF_STUDY_POST'
GET='        if path in SELF_STUDY_GET:return self.self_study_route(path,q)'
POST='        if path in SELF_STUDY_POST:return self.self_study_route(path,write=True)'
MARKER='self_study_install.json'


def digest(data):return hashlib.sha256(data).hexdigest()


def patch_api(text):
    if 'SelfStudyMixin' in text:
        if IMPORT not in text or GET not in text or POST not in text:raise RuntimeError('Partial API integration; review required')
        return text
    anchors=['class Handler(', '        parsed=urlparse(self.path);path=parsed.path;q=parse_qs(parsed.query)',
             '        path=urlparse(self.path).path']
    if any(text.count(a)!=1 for a in anchors):raise RuntimeError('Live API differs from reviewed integration; no writes')
    text=text.replace(anchors[0],IMPORT+'\n\nclass Handler(SelfStudyMixin, ',1)
    text=text.replace(anchors[1],anchors[1]+'\n'+GET,1)
    text=text.replace(anchors[2],anchors[2]+'\n'+POST,1)
    ast.parse(text);return text


def patch_html(text):
    if text.count('</head>')!=1 or text.count('</body>')!=1:raise RuntimeError('Unrecognised teacher HTML')
    for name in ['self_study.css','self_study.js','self_study_voice.js','self_study_scenes.js','self_study_settings.js','self_study_intensive.js']:
        pattern=(r'<link\b[^>]*href=[\"\']/app/'+re.escape(name)+r'(?:\?[^\"\']*)?[\"\'][^>]*>' if name.endswith('.css') else
                 r'<script\b[^>]*src=[\"\']/app/'+re.escape(name)+r'(?:\?[^\"\']*)?[\"\'][^>]*>\s*</script>')
        text,count=re.subn(pattern,'',text)
        if count>1:raise RuntimeError('Duplicate learning asset in live HTML')
        url='/app/'+name+'?v='+digest((SOURCE/'web'/name).read_bytes())[:12]
        tag='<link rel="stylesheet" href="'+url+'">' if name.endswith('.css') else '<script defer src="'+url+'"></script>'
        end='</head>' if name.endswith('.css') else '</body>'
        text=text.replace(end,tag+end,1)
    return text


def candidates(root):
    if root==SOURCE:raise RuntimeError('Source and live checkout must differ')
    previous=json.loads((root/MARKER).read_text()) if (root/MARKER).exists() else {}
    result={}
    for name in MODULES:
        data=(SOURCE/name).read_bytes();target=root/name
        if target.exists() and target.read_bytes()!=data:
            if digest(target.read_bytes())!=previous.get('hashes',{}).get(name):
                raise RuntimeError('Existing module changed outside this installer: '+name)
        result[name]=data
    result['web_backend/api_v7.py']=patch_api((root/'web_backend/api_v7.py').read_text()).encode()
    result['web/teacher.html']=patch_html((root/'web/teacher.html').read_text()).encode()
    if (root/'web/index.html').exists():
        student_html=(root/'web/index.html').read_text()
        link='<a class="shell-action" href="/app/self-study.html">Моё обучение · языки</a>'
        if '/app/self-study.html' not in student_html:
            anchor='<h2 id="profileSheetTitle">Профиль</h2>'
            if student_html.count(anchor)!=1:raise RuntimeError('Student entry needs review')
            student_html=student_html.replace(anchor,anchor+link,1)
        result['web/index.html']=student_html.encode()
    for name,data in result.items():
        if name.endswith('.py'):ast.parse(data,filename=name)
        # Reject symlinks escaping the selected live release.
        if not (root/name).resolve().is_relative_to(root):raise RuntimeError('Target escapes live checkout: '+name)
    return result


def atomic(path,data,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='study-update-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(temp,mode);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def restart(service):subprocess.run(['systemctl','restart',service],check=True,timeout=45)


def health(base):
    if not re.fullmatch(r'http://127\.0\.0\.1:\d+',base):raise RuntimeError('Health URL must be loopback with explicit port')
    for _ in range(10):
        try:
            with urlopen(base+'/api/health',timeout=2) as r:
                if json.load(r).get('ok') is not True:raise RuntimeError('Health failed')
            try:
                urlopen(base+'/api/teacher/self-study',timeout=3)
                raise RuntimeError('Private learning endpoint did not require authentication')
            except HTTPError as exc:
                if exc.code!=401:raise RuntimeError('Private endpoint returned '+str(exc.code))
            return
        except (OSError,ValueError,RuntimeError):time.sleep(1)
    raise RuntimeError('Post-install health/authentication checks failed')


def restore(root,backup):
    manifest=json.loads((backup/'manifest.json').read_text())
    if str(root)!=manifest['root']:raise RuntimeError('Backup belongs to another release')
    # Preserve subsequent work: reject rollback if a managed file has changed.
    for name,expected in manifest['installed'].items():
        path=root/name
        if not path.exists() or digest(path.read_bytes())!=expected:raise RuntimeError('Rollback conflict: '+name)
    for name,before in manifest['before'].items():
        path=root/name
        if before is None:path.unlink(missing_ok=True)
        else:atomic(path,(backup/'files'/name).read_bytes(),before['mode'])


def install(root,database,service,base,apply=False):
    root=root.resolve();database=database.resolve()
    if not re.fullmatch(r'[a-zA-Z0-9_.@-]+',service):raise RuntimeError('Invalid service name')
    if not re.fullmatch(r'http://127\.0\.0\.1:\d+',base):raise RuntimeError('Invalid loopback URL')
    if not database.is_file():raise RuntimeError('Specify the existing production SQLite database')
    candidate=candidates(root)
    candidate[MARKER]=json.dumps({'hashes':{n:digest(v) for n,v in candidate.items()}},indent=2).encode()
    original={name:((root/name).read_bytes() if (root/name).exists() else None) for name in candidate}
    changed={n:v for n,v in candidate.items() if original[n]!=v}
    print(json.dumps({'mode':'apply' if apply else 'check','root':str(root),'changed_files':list(changed)},indent=2))
    if not apply or not changed:return None
    backup=Path(tempfile.mkdtemp(prefix='self-study-',dir=root.parent));os.chmod(backup,0o700)
    before={}
    for name in changed:
        if original[name] is None:before[name]=None
        else:
            target=backup/'files'/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(original[name]);before[name]={'mode':(root/name).stat().st_mode&0o777}
    src=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    dest=sqlite3.connect(backup/'database.sqlite')
    try:src.backup(dest)
    finally:dest.close();src.close()
    manifest={'root':str(root),'before':before,'installed':{n:digest(v) for n,v in changed.items()},'database':str(database)}
    (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
    written=[]
    try:
        for name,value in changed.items():
            if ((root/name).read_bytes() if (root/name).exists() else None)!=original[name]:raise RuntimeError('Concurrent file change: '+name)
            atomic(root/name,value,before[name]['mode'] if before[name] else 0o644);written.append(name)
        restart(service);health(base)
    except BaseException:
        for name in reversed(written):
            if original[name] is None:(root/name).unlink(missing_ok=True)
            else:atomic(root/name,original[name],before[name]['mode'])
        restart(service);raise
    print('Installed. Backup:',backup)
    print('Rollback restores code only; learning records are preserved.')
    return backup


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--database',type=Path)
    p.add_argument('--service',required=True);p.add_argument('--health-url')
    p.add_argument('--apply',action='store_true');p.add_argument('--rollback',type=Path)
    args=p.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_.@-]+',args.service):p.error('Invalid service name')
    if args.apply:
        import fcntl
        lock=open(args.root.resolve().parent/'self-study-update.lock','a')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if args.rollback:
        if not args.apply:raise SystemExit('Rollback requires --apply')
        restore(args.root.resolve(),args.rollback.resolve());restart(args.service);return
    if not args.database or not args.health_url:p.error('--database and --health-url are required')
    install(args.root,args.database,args.service,args.health_url,args.apply)


if __name__=='__main__':main()
