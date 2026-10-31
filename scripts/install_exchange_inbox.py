#!/usr/bin/env python3
import argparse,datetime,fcntl,hashlib,json,os,re,subprocess,tempfile,time
from pathlib import Path

def patch(text,hunks):
    for h in hunks:
        if h['new'] in text:continue
        if text.count(h['old'])!=1:raise RuntimeError('Exchange UI hook differs; no files changed')
        text=text.replace(h['old'],h['new'],1)
    return text

def html(text):
    tag='<script defer src="/app/student_exchange_inbox.js?v=20261030-exchange1"></script>'
    if 'student_exchange_inbox.js' in text:return text
    match=re.search(r'<script\b[^>]*src=[\"\'][^\"\']*student_self_service\.js[^\"\']*[\"\'][^>]*>\s*</script>',text)
    if not match:
        if '</body>' not in text:raise RuntimeError('Student page structure differs; no files changed')
        return text.replace('</body>',tag+'</body>',1)
    text=text[:match.start()]+tag+text[match.start():]
    return re.sub(r'(/app/student_self_service\.js)(?:\?[^\"\']*)?',lambda m:m[1]+'?v=20261030-exchange1',text)

def write(path,data):
    mode=path.stat().st_mode if path.exists() else 0o644
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,mode);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    a=argparse.ArgumentParser();a.add_argument('--root',default='/opt/adelia-current');a.add_argument('--apply',action='store_true');a=a.parse_args();root=Path(a.root).resolve();src=Path(__file__).resolve().parents[1]
    lock=open('/run/adelia-exchange-inbox.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    old={};new={}
    name='web/student_exchange_inbox.js';old[name]=(root/name).read_bytes() if (root/name).exists() else None;new[name]=(src/name).read_bytes()
    if old[name] is not None and old[name]!=new[name]:raise RuntimeError('Unknown exchange inbox edits; no files changed')
    for name,h in json.loads((src/'scripts/exchange_inbox_hunks.json').read_text()).items():old[name]=(root/name).read_bytes();new[name]=patch(old[name].decode(),h).encode()
    name='web/index.html';old[name]=(root/name).read_bytes();new[name]=html(old[name].decode()).encode()
    changed=[n for n in new if new[n]!=old[n]];print(json.dumps({'mode':'apply' if a.apply else 'check','changed_files':changed}),flush=True)
    if not changed:print('EXCHANGE_INBOX_ALREADY_INSTALLED');return
    if not a.apply:return
    if os.geteuid()!=0:raise RuntimeError('Root required')
    service='tutorbot-web.service';pid=int(subprocess.check_output(['systemctl','show',service,'-p','MainPID','--value'],text=True))
    if Path('/proc/'+str(pid)+'/cwd').resolve()!=root:raise RuntimeError('Service uses another release')
    backup=Path('/opt/tutorbot/backups')/('exchange-inbox-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));backup.mkdir(parents=True)
    for n in changed:
        if old[n] is not None:p=backup/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(old[n])
    (backup/'manifest.json').write_text(json.dumps({'new_files':[n for n in changed if old[n] is None]}))
    try:
        for n in changed:write(root/n,new[n])
        for n in ['web/student_exchange_inbox.js','web/student_self_service.js']:
            served=subprocess.check_output(['curl','--noproxy','*','--resolve','adeliatutor.ru:443:127.0.0.1','-fsS','--max-time','10','https://adeliatutor.ru/app/'+Path(n).name+'?v=20261030-exchange1'])
            if served!=new[n]:raise RuntimeError('Published asset differs: '+n)
    except BaseException:
        for n in changed:
            if old[n] is None:(root/n).unlink(missing_ok=True)
            else:write(root/n,old[n])
        print('EXCHANGE_INBOX_ROLLED_BACK',flush=True);raise
    print('EXCHANGE_INBOX_INSTALLED\nBackup: '+str(backup),flush=True)
if __name__=='__main__':main()
