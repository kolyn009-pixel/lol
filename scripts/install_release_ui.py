"""Install shared release UI without replacing production cabinet HTML."""
import argparse,ast,fcntl,hashlib,json,os,re,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
FILES=['web/release_ui.css','web/release_ui.js','web/teacher_mobile_app.css','web/teacher_mobile_app.js','web/lesson_calendar.css','web/lesson_calendar.js','web_backend/lesson_calendar.py','web/teacher_quick_payment.js','web/teacher_group_finance.js','web_backend/group_finance_admin.py']
HTML=['web/teacher.html','web/index.html','web/parent/index.html']
RECORD='release_ui_install.json'

def html(text):
    if text.count('</head>')!=1:raise RuntimeError('HTML head needs review')
    names=['release_ui.css','release_ui.js']
    if 'teacher-shell' in text:names+=['teacher_mobile_app.css','teacher_mobile_app.js','lesson_calendar.css','lesson_calendar.js','teacher_quick_payment.js','teacher_group_finance.js','teacher_group_settings.js']
    for name in names:
        if '/app/'+name in text:
            text=re.sub(r'(/app/'+re.escape(name)+r')(?:\?[^\"\']*)?',lambda m:m[1]+'?v=20261031-groupfinance1',text)
            continue
        tag=('<link rel="stylesheet" href="/app/'+name+'?v=20261031-groupfinance1">') if name.endswith('.css') else ('<script defer src="/app/'+name+'?v=20261031-groupfinance1"></script>')
        text=text.replace('</head>',tag+'</head>',1)
    if 'teacher-shell' in text:
        text=re.sub(r'(<meta\s+name=[\"\']theme-color[\"\']\s+content=[\"\'])[^\"\']*',lambda m:m[1]+'#f5f5fa',text)
    text=re.sub(r'(/app/teacher_schedule_settings\.js)(?:\?[^\"\']*)?',lambda m:m[1]+'?v=20261031-groupfinance1',text)
    text=re.sub(r'(teacher-manifest\.webmanifest)(?:\?[^\"\']*)?',lambda m:m[1]+'?v=20261031-groupfinance1',text)
    return text

def manifest(text):
    value=json.loads(text)
    value['scope']='/app/'
    value['start_url']='/app/teacher.html'
    value['display']='standalone'
    value['display_override']=['standalone']
    value['theme_color']=value['background_color']='#f5f5fa'
    for shortcut in value.get('shortcuts',[]):
        old=str(shortcut.get('url') or '')
        shortcut['url']='/app/teacher.html'+('#'+old.split('#',1)[1] if '#' in old else '')
    return json.dumps(value,ensure_ascii=False,indent=2)+'\n'

def health():
    for _ in range(20):
        try:
            d=subprocess.check_output(['curl','--noproxy','*','-fsS','--max-time','3','http://127.0.0.1:8876/api/health'],stderr=subprocess.DEVNULL,timeout=4)
            if json.loads(d).get('ok') is True:return
        except (ValueError,subprocess.SubprocessError):pass
        time.sleep(1)
    raise RuntimeError('Web health check failed')

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/adelia-current');p.add_argument('--apply',action='store_true');a=p.parse_args()
    root=Path(a.root).resolve(strict=True);source=Path(__file__).resolve().parents[1]
    if root==source:raise RuntimeError('Use an isolated checkout')
    lock=open('/run/adelia-release-ui.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    prior=json.loads((root/RECORD).read_text()) if (root/RECORD).exists() else {};original={};candidate={}
    for name in FILES:
        value=(source/name).read_bytes();live=(root/name).read_bytes() if (root/name).exists() else None
        if live is not None and live!=value and prior.get(name)!=hashlib.sha256(live).hexdigest():raise RuntimeError('Local UI edits need review: '+name)
        if name.endswith('.py'):compile(value,name,'exec')
        original[name]=live;candidate[name]=value
    for name in HTML:
        if name=='web/parent/index.html' and not (root/name).exists():continue
        original[name]=(root/name).read_bytes();candidate[name]=html(original[name].decode()).encode()
    name='web/teacher-manifest.webmanifest'
    original[name]=(root/name).read_bytes()
    candidate[name]=manifest(original[name].decode()).encode()
    for name,hunks in {**json.loads((source/'scripts/lesson_calendar_hooks.json').read_text()),**json.loads((source/'scripts/group_finance_hooks.json').read_text())}.items():
        original[name]=(root/name).read_bytes()
        text=original[name].decode()
        for h in hunks:
            if text.count(h['old'])==1 and h['new'] not in text:text=text.replace(h['old'],h['new'],1)
            elif h['old'] not in text and text.count(h['new'])==1:pass
            else:raise RuntimeError('Calendar hook needs review; no files changed: '+name)
        if name.endswith('.py'):compile(text,name,'exec')
        candidate[name]=text.encode()
    original[RECORD]=(root/RECORD).read_bytes() if (root/RECORD).exists() else None
    candidate[RECORD]=json.dumps({n:hashlib.sha256(candidate[n]).hexdigest() for n in FILES},indent=2).encode()
    changed=[n for n in candidate if candidate[n]!=original[n]]
    print(json.dumps({'mode':'apply' if a.apply else 'check','changed_files':changed}))
    if not a.apply or not changed:return
    if os.geteuid()!=0:raise RuntimeError('Apply requires root')
    cwd=subprocess.check_output(['systemctl','show','tutorbot-web.service','-p','WorkingDirectory','--value'],text=True).strip()
    if not cwd or Path(cwd).resolve()!=root:raise RuntimeError('Web service uses a different release')
    backup=Path('/opt/tutorbot/backups')/('release-ui-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));backup.mkdir(parents=True)
    for n in changed:
        if original[n] is not None:
            f=backup/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(original[n])
    (backup/'manifest.json').write_text(json.dumps({'root':str(root),'files':changed,'new_files':[n for n in changed if original[n] is None]}))
    try:
        for n in changed:
            f=root/n;f.parent.mkdir(parents=True,exist_ok=True);tmp=f.with_name(f.name+'.ui-next');tmp.write_bytes(candidate[n]);os.chmod(tmp,0o644);os.replace(tmp,f)
        subprocess.run(['systemctl','restart','tutorbot-web.service'],check=True,timeout=60);health()
        for name in [n for n in FILES if n.startswith('web/')]+['web/teacher-manifest.webmanifest']:
            served=subprocess.check_output(['curl','--noproxy','*','--resolve','adeliatutor.ru:443:127.0.0.1','-fsS','--max-time','10','https://adeliatutor.ru/app/'+Path(name).name+'?v=20261031-groupfinance1'],timeout=12)
            if served!=candidate[name]:raise RuntimeError('Static asset verification failed: '+name)
    except Exception:
        for n in reversed(changed):
            if original[n] is None:(root/n).unlink(missing_ok=True)
            else:(root/n).write_bytes(original[n])
        subprocess.run(['systemctl','restart','tutorbot-web.service'],timeout=60)
        raise
    print('RELEASE_UI_INSTALLED\nBackup: '+str(backup))

if __name__=='__main__':main()
