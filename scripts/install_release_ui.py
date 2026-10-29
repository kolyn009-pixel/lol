"""Install shared release UI without replacing production cabinet HTML."""
import argparse,ast,fcntl,hashlib,json,os,re,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
FILES=['web/release_ui.css','web/release_ui.js']
HTML=['web/teacher.html','web/index.html','web/parent/index.html']
RECORD='release_ui_install.json'

def html(text):
    if text.count('</head>')!=1:raise RuntimeError('HTML head needs review')
    for name in ('release_ui.css','release_ui.js'):
        if '/app/'+name in text:continue
        tag='<link rel="stylesheet" href="/app/release_ui.css?v=20261029-release1">' if name.endswith('.css') else '<script defer src="/app/release_ui.js?v=20261029-release1"></script>'
        text=text.replace('</head>',tag+'</head>',1)
    return text

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
        original[name]=live;candidate[name]=value
    for name in HTML:
        if name=='web/parent/index.html' and not (root/name).exists():continue
        original[name]=(root/name).read_bytes();candidate[name]=html(original[name].decode()).encode()
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
        for name in FILES:
            served=subprocess.check_output(['curl','--noproxy','*','--resolve','adeliatutor.ru:443:127.0.0.1','-fsS','--max-time','10','https://adeliatutor.ru/app/'+Path(name).name+'?v=20261029-release1'],timeout=12)
            if served!=candidate[name]:raise RuntimeError('Static asset verification failed: '+name)
    except Exception:
        for n in reversed(changed):
            if original[n] is None:(root/n).unlink(missing_ok=True)
            else:(root/n).write_bytes(original[n])
        subprocess.run(['systemctl','restart','tutorbot-web.service'],timeout=60)
        raise
    print('RELEASE_UI_INSTALLED\nBackup: '+str(backup))

if __name__=='__main__':main()
