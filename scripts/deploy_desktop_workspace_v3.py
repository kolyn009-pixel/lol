#!/usr/bin/env python3
"""Install only desktop UI static assets. Preserve the deployed backend and DB."""
import argparse,hashlib,os,shutil,subprocess,tempfile,json
from pathlib import Path

NEW=['desktop_teacher_app.css','desktop_workspace_v3.css','desktop_workspace_v3.js','quick_chat.html','quick_chat.css','quick_chat.js']

def build_updates(root, payload):
    updates={root/'web'/name:payload('web/'+name) for name in NEW}
    # Keep server-side edits and alter only narrow, recognizable integration points.
    def current(name):return (root/'web'/name).read_text()
    def replace_once(text, before, after):
        if after in text:return text
        if text.count(before)!=1:raise RuntimeError('Unrecognized integration point; no files changed: '+before[:80])
        return text.replace(before,after,1)
    name='teacher_messages_stage10.js';text=current(name)
    text=replace_once(text,'window.teacherMessages=show;', 'window.teacherMessages=show;\nwindow.AdeliaTeacherMessenger={pause:stop};')
    updates[root/'web'/name]=text.encode()
    name='teacher_clean_runtime.js';text=current(name)
    text=replace_once(text,"function enhanceToday(){if(document.querySelector('#title')?.textContent.trim()!=='Сегодня')return;", "function enhanceToday(){if(document.querySelector('#title')?.textContent.trim()!=='Сегодня')return;if(window.adeliaDesktop?.desktop&&document.querySelector('.dashboard-lesson-card'))return;")
    updates[root/'web'/name]=text.encode()
    name='install_runtime.js';text=current(name)
    start=text.index('  async function install(){');end=text.index('\n  function mount()',start)
    text=text[:start]+"  async function install(){ location.assign('/desktop-updates/'); }\n"+text[end:]
    text=text.replace('Установить Аделию на телефон','Установить Аделию').replace('Пошаговая инструкция для iPhone и Android','Windows, Mac, iPhone и Android').replace('>Инструкция</button>','>Скачать</button>')
    text=text.replace('if(!target)return;e.preventDefault();install()', 'if(!target)return;e.preventDefault();e.stopImmediatePropagation();install()')
    updates[root/'web'/name]=text.encode()
    for name in ['teacher.html','index.html']:
        text=current(name)
        if 'data-adelia-workspace-v3' not in text:
            if text.count('</head>')!=1:raise RuntimeError('Unrecognized HTML head: '+name)
            tags='<link data-adelia-workspace-v3 rel="stylesheet" href="/app/desktop_teacher_app.css?v=20261022-workspace3"><link rel="stylesheet" href="/app/desktop_workspace_v3.css?v=20261022-workspace3"><script defer src="/app/desktop_workspace_v3.js?v=20261022-workspace3"></script>'
            text=text.replace('</head>',tags+'</head>',1)
        # Refresh the installer link script while preserving the rest of the document.
        import re
        text=re.sub(r'(install_runtime\.js)(?:\?[^\s"\'<>]*)?',r'\1?v=20261022-workspace3',text)
        updates[root/'web'/name]=text.encode()
    return updates

def atomic(path,data):
    old=path.stat() if path.exists() else None
    fd,tmp=tempfile.mkstemp(prefix='.adelia-workspace-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        os.chmod(tmp,old.st_mode&0o777 if old else 0o644)
        if old:os.chown(tmp,old.st_uid,old.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def install(root,payload,backups):
    updates=build_updates(root,payload)
    backup=Path(tempfile.mkdtemp(prefix='desktop-workspace-v3-',dir=backups));os.chmod(backup,0o700)
    existed={str(p.relative_to(root)):p.exists() for p in updates}
    for p in updates:
        if p.exists():
            dst=backup/'original'/p.relative_to(root);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
    (backup/'state.json').write_text(json.dumps({'root':str(root),'existed':existed},indent=2))
    rollback='''from pathlib import Path
import json,os,tempfile
b=Path(__file__).parent;s=json.loads((b/'state.json').read_text());r=Path(s['root'])
for rel,existed in s['existed'].items():
 p=r/rel
 if not existed:p.unlink(missing_ok=True);continue
 data=(b/'original'/rel).read_bytes();st=(b/'original'/rel).stat();fd,n=tempfile.mkstemp(dir=p.parent)
 with os.fdopen(fd,'wb') as out:out.write(data)
 os.chmod(n,st.st_mode&0o777);os.chown(n,st.st_uid,st.st_gid);os.replace(n,p)
print('DESKTOP_WORKSPACE_ROLLED_BACK')
'''
    (backup/'rollback.py').write_text(rollback)
    try:
        # Install HTML last so references never precede their new assets.
        for path,data in sorted(updates.items(),key=lambda item:item[0].suffix=='.html'):atomic(path,data)
        for path,data in updates.items():
            if path.read_bytes()!=data:raise RuntimeError('Verification failed: '+str(path))
    except BaseException:
        subprocess.run(['python3',str(backup/'rollback.py')],check=True);raise
    print('DESKTOP_WORKSPACE_STATIC_OK')
    print('Backup:',backup)
    print('Rollback: python3 '+str(backup/'rollback.py'))
    print('The Yandex login fix also requires the new native desktop release 0.3.0-beta.3.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('commit');args=parser.parse_args()
    root=Path('/opt/adelia-current').resolve(strict=True)
    if os.geteuid()!=0:raise SystemExit('Run on the server as root')
    def payload(p):return subprocess.check_output(['git','-C','/opt/tutorbot','show',args.commit+':'+p])
    install(root,payload,'/opt/tutorbot/backups')
