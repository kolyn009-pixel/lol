"""Apply reviewed reschedule hunks, retaining unrelated production edits.

Default is preflight only. Never edits credentials, lesson data or personal events.
Google cleanup runs through the existing bot reconciliation after restart.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from datetime import datetime, timezone
NEW='core/lesson_reschedule_details.py'

def patch_text(live, hunks, label):
    for index,hunk in enumerate(hunks):
        old,new=hunk['old'],hunk['new']
        old_count,new_count=live.count(old),live.count(new)
        if old_count==1 and new_count==0:
            live=live.replace(old,new,1)
        elif old_count==0 and new_count==1:
            pass
        else:
            raise RuntimeError(f'Local changes need review; no files changed: {label}, hunk {index+1}')
    compile(live,label,'exec')
    return live

def atomic(path,data,stat=None):
    fd,name=tempfile.mkstemp(prefix='.reschedule-next-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(name,stat.st_mode & 0o777 if stat else 0o644)
        if stat:os.chown(name,stat.st_uid,stat.st_gid)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def health(services,root):
    for _ in range(15):
        for service in services:
            subprocess.run(['systemctl','is-active','--quiet',service],check=True,timeout=5)
            cwd=subprocess.check_output(['systemctl','show',service,'-p','WorkingDirectory','--value'],text=True,timeout=5).strip()
            if Path(cwd).resolve()!=root:raise RuntimeError('Service release changed: '+service)
        try:
            raw=subprocess.check_output(['curl','--noproxy','*','-fsS','--max-time','2','http://127.0.0.1:8876/api/health'],stderr=subprocess.DEVNULL,timeout=3)
            if json.loads(raw).get('ok') is True:return
        except (subprocess.SubprocessError,ValueError):pass
        time.sleep(1)
    raise RuntimeError('Web health check failed')

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/adelia-current');p.add_argument('--apply',action='store_true');a=p.parse_args()
    source=Path(__file__).resolve().parents[1];link=Path(a.root);root=link.resolve(strict=True)
    if root==source:raise RuntimeError('Use an isolated source checkout')
    lock=open('/run/adelia-learning-deploy.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    delta=json.loads((source/'scripts/reschedule_calendar_delta.json').read_text())
    original={};candidate={};stats={}
    for name,hunks in delta.items():
        path=root/name
        if path.is_symlink():raise RuntimeError('Unexpected symlink: '+name)
        original[name]=path.read_bytes();stats[name]=path.stat()
        candidate[name]=patch_text(original[name].decode(),hunks,name).encode()
    path=root/NEW;new=(source/NEW).read_bytes();compile(new,NEW,'exec')
    if path.is_symlink():raise RuntimeError('Unexpected symlink: '+NEW)
    if path.exists() and path.read_bytes()!=new:raise RuntimeError('Local module needs review: '+NEW)
    original[NEW]=path.read_bytes() if path.exists() else None
    stats[NEW]=path.stat() if path.exists() else None;candidate[NEW]=new
    changed=[n for n in candidate if candidate[n]!=original[n]]
    print(json.dumps({'mode':'apply' if a.apply else 'check','changed_files':changed}))
    if not a.apply:return
    if not changed:print('RESCHEDULE_CALENDAR_ALREADY_INSTALLED');return
    if os.geteuid()!=0:raise RuntimeError('Apply requires root')
    services=[]
    for service in ('tutorbot-web.service','tutorbot.service','tutorbot-vk.service'):
        active=subprocess.run(['systemctl','is-active','--quiet',service],timeout=5).returncode==0
        if not active:
            if service!='tutorbot-vk.service':raise RuntimeError('Required service is not active: '+service)
            continue
        cwd=subprocess.check_output(['systemctl','show',service,'-p','WorkingDirectory','--value'],text=True,timeout=5).strip()
        if not cwd or Path(cwd).resolve()!=root:raise RuntimeError('Different service release: '+service)
        services.append(service)
    backup=Path('/opt/tutorbot/backups')/('reschedule-calendar-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True,mode=0o700)
    for name in changed:
        if original[name] is not None:
            path=backup/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(original[name])
    (backup/'manifest.json').write_text(json.dumps({'root':str(root),'files':changed,
        'new_files':[n for n in changed if original[n] is None],
        'sha256':{n:hashlib.sha256(candidate[n]).hexdigest() for n in changed}},indent=2))
    try:
        if link.resolve()!=root:raise RuntimeError('Active release changed')
        subprocess.run(['systemctl','stop',*services],check=True,timeout=60)
        for name in changed:atomic(root/name,candidate[name],stats[name])
        subprocess.run(['systemctl','start',*services],check=True,timeout=60)
        health(services,root)
    except BaseException:
        subprocess.run(['systemctl','stop',*services],timeout=60,check=False)
        for name in changed:
            if original[name] is None:(root/name).unlink(missing_ok=True)
            else:atomic(root/name,original[name],stats[name])
        subprocess.run(['systemctl','start',*services],timeout=60,check=False)
        print('INSTALL_FAILED; original files restored. Backup:',backup)
        raise
    print('RESCHEDULE_CALENDAR_INSTALLED\nBackup: '+str(backup))
    print('Linked obsolete Calendar events are reconciled automatically by the bot; check provider logs for errors.')
if __name__=='__main__':main()
