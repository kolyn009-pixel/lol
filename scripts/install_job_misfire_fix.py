#!/usr/bin/env python3
"""Apply only reviewed recurring job lateness limits; never replace whole live handlers."""
import argparse,datetime,fcntl,json,os,shutil,subprocess,tempfile,time
from pathlib import Path

def patched(text,hunks):
    for h in hunks:
        if text.count(h['new'])==1:continue
        if text.count(h['old'])!=1:raise RuntimeError('Guard context differs; no files changed')
        text=text.replace(h['old'],h['new'],1)
    return text

def write(path,data):
    stat=path.stat();fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.job-misfire-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,stat.st_mode);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/adelia-current');p.add_argument('--apply',action='store_true');a=p.parse_args()
    root=Path(a.root).resolve(strict=True);source=Path(__file__).resolve().parents[1]
    if root==source:raise RuntimeError('Use isolated source checkout')
    lock=open('/run/adelia-job-misfire.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    old={};new={}
    for name,hunks in json.loads((source/'scripts/job_misfire_hunks.json').read_text()).items():
        live=(root/name).read_bytes();result=patched(live.decode(),hunks).encode();compile(result,name,'exec')
        if result!=live:old[name]=live;new[name]=result
    print(json.dumps({'mode':'apply' if a.apply else 'check','changed_files':list(new)}),flush=True)
    if not new:print('JOB_MISFIRE_FIX_ALREADY_INSTALLED');return
    if not a.apply:return
    if os.geteuid()!=0:raise RuntimeError('Apply requires root')
    service='tutorbot.service'
    if subprocess.check_output(['systemctl','is-active',service],text=True).strip()!='active':raise RuntimeError('Telegram service is not active; no files changed')
    pid=int(subprocess.check_output(['systemctl','show',service,'-p','MainPID','--value'],text=True).strip())
    if Path('/proc/'+str(pid)+'/cwd').resolve()!=root:raise RuntimeError('Service uses another release; no files changed')
    backup=Path('/opt/tutorbot/backups')/('job-misfire-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True)
    for name,data in old.items():
        dst=backup/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,dst)
    try:
        for name,data in new.items():write(root/name,data)
        subprocess.run(['systemctl','restart',service],check=True)
        for _ in range(3):
            time.sleep(1)
            subprocess.run(['systemctl','is-active','--quiet',service],check=True)
    except BaseException:
        for name,data in old.items():write(root/name,data)
        subprocess.run(['systemctl','restart',service],check=False)
        print('JOB_MISFIRE_FIX_ROLLED_BACK',flush=True);raise
    print('JOB_MISFIRE_FIX_INSTALLED\nBackup: '+str(backup),flush=True)
if __name__=='__main__':main()
