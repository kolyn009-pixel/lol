"""Publish the three reviewed desktop ZIP bundles without editing nginx."""
import argparse,ctypes,hashlib,json,os,shutil,stat,subprocess,tempfile,zipfile
from pathlib import Path
SHA='19bf90ef5b9210c2188ac46ae057ccdeaf89169f'
VERSION='0.3.0-beta.7'
TARGETS={'win-x64':'Adelia-latest-windows-x64.exe','macos-x64':'Adelia-latest-macos-x64.dmg','macos-arm64':'Adelia-latest-macos-arm64.dmg'}

def digest(p,kind):
 h=hashlib.new(kind)
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def exchange(a,b):
 lib=ctypes.CDLL(None,use_errno=True)
 if not hasattr(lib,'renameat2'):raise RuntimeError('Atomic directory exchange unavailable; no legacy feed changed')
 if lib.renameat2(-100,os.fsencode(a),-100,os.fsencode(b),2):raise OSError(ctypes.get_errno(),'Atomic exchange failed')

def get(url,head=False):
 return subprocess.check_output(['curl','--noproxy','*','--resolve','adeliatutor.ru:443:127.0.0.1','-fsS','--max-time','30']+(['-I'] if head else [])+[url])

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 if os.geteuid()!=0:raise SystemExit('Run as root')
 import fcntl
 lock=open('/run/adelia-desktop-publication.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 uploaded=Path('/root/adelia-upload/0.3.0-beta.7-19bf90ef5b92')
 root=Path('/var/www/adeliatutor.ru/desktop-updates')
 checks={}
 for line in (uploaded/'SHA256SUMS').read_text().splitlines():
  value,name=line.split(maxsplit=1);checks[name.lstrip('*')]=value
 for target in TARGETS:
  name=target+'.zip'
  if name not in checks or digest(uploaded/name,'sha256')!=checks[name]:raise RuntimeError('Upload checksum mismatch: '+name)
 # All preparation precedes channel publication.
 stage=Path(tempfile.mkdtemp(prefix='adelia-desktop-verified-',dir='/opt/tutorbot'))
 for target,alias in TARGETS.items():
  dest=stage/target;dest.mkdir()
  with zipfile.ZipFile(uploaded/(target+'.zip')) as z:
   names=z.namelist()
   if len(names)!=len(set(names)) or len(names)>100 or sum(x.file_size for x in z.infolist())>3*1024**3:raise RuntimeError('Unexpected archive structure')
   for x in z.infolist():
    if Path(x.filename).name!=x.filename or stat.S_ISLNK(x.external_attr>>16):raise RuntimeError('Unexpected archive entry')
   z.extractall(dest)
  m=json.loads((dest/'manifest.json').read_text(encoding='utf-8'));r=json.loads((dest/'release.json').read_text(encoding='utf-8'))
  for d in (m,r):
   if d.get('git_sha')!=SHA or d.get('version')!=VERSION or d.get('channel')!='beta':raise RuntimeError('Bundle identity mismatch: '+target)
  files=m.get('files',[]);names={x['name'] for x in files}
  if alias not in names or ('beta.yml' if target=='win-x64' else 'beta-mac.yml') not in names:raise RuntimeError('Update feed incomplete')
  for x in files:
   if Path(x['name']).name!=x['name']:raise RuntimeError('Invalid manifest filename')
   f=dest/x['name']
   if not f.is_file() or f.stat().st_size!=x['size'] or digest(f,'sha512')!=x['sha512']:raise RuntimeError('Artifact checksum mismatch: '+str(f))
  print('VERIFIED:',target,flush=True)
 if not args.apply:print('Prepared:',stage);return
 root.mkdir(parents=True,exist_ok=True)
 releases=root/'releases'/'beta';releases.mkdir(parents=True,exist_ok=True)
 release=releases/(VERSION+'--'+SHA[:12])
 if release.exists():raise RuntimeError('Release already exists; inspect before publishing again: '+str(release))
 shutil.copytree(stage,release)
 (release/'release-set.json').write_text(json.dumps({'channel':'beta','version':VERSION,'git_sha':SHA,'targets':list(TARGETS)}))
 for d,_,files in os.walk(release):
  os.chmod(d,0o755)
  for name in files:os.chmod(Path(d)/name,0o644)
 (Path('/opt/tutorbot')/'backups').mkdir(exist_ok=True)
 backup=Path(tempfile.mkdtemp(prefix='adelia-desktop-before-',dir='/opt/tutorbot/backups'))
 live=root/'beta';next_link=root/('.beta-next-'+str(os.getpid()));next_link.symlink_to(release)
 old=os.path.lexists(live);legacy=old and live.is_dir() and not live.is_symlink()
 oldlink=os.readlink(live) if old and live.is_symlink() else None
 if old and not legacy and oldlink is None:raise RuntimeError('Unexpected live channel type')
 aliases=[];switched=False
 try:
  if legacy:exchange(next_link,live)
  else:os.replace(next_link,live)
  switched=True
  for target,alias in TARGETS.items():
   dst=root/alias;saved=backup/alias
   if dst.is_dir():raise RuntimeError('Alias is a directory: '+alias)
   exists=os.path.lexists(dst)
   if exists:shutil.copy2(dst,saved,follow_symlinks=False)
   aliases.append((dst,saved,exists))
   tmp=root/('.alias-'+str(os.getpid()));tmp.symlink_to('beta/'+target+'/'+alias);os.replace(tmp,dst)
  for target,alias in TARGETS.items():
   base='https://adeliatutor.ru/desktop-updates/beta/'+target+'/'
   data=json.loads(get(base+'release.json'))
   feed=get(base+('beta.yml' if target=='win-x64' else 'beta-mac.yml'))
   if not feed.strip() or b'<html' in feed.lower():raise RuntimeError('Invalid update feed')
   if data.get('git_sha')!=SHA or data.get('version')!=VERSION:raise RuntimeError('Wrong served release: '+target)
   for url in (base+alias,'https://adeliatutor.ru/desktop-updates/'+alias):
    headers=get(url,True).decode().lower()
    size=(release/target/alias).stat().st_size
    if 'text/html' in headers or 'content-length: '+str(size) not in headers:raise RuntimeError('Installer HTTP verification failed: '+url)
   print('HTTP_OK:',target,flush=True)
 except Exception:
  for dst,saved,exists in reversed(aliases):
   dst.unlink(missing_ok=True)
   if exists:
    tmp=root/('.restore-'+str(os.getpid()));shutil.copy2(saved,tmp,follow_symlinks=False);os.replace(tmp,dst)
  if switched:
   if legacy:exchange(next_link,live)
   elif oldlink is not None:
    tmp=root/('.rollback-'+str(os.getpid()));tmp.symlink_to(oldlink);os.replace(tmp,live)
   else:live.unlink(missing_ok=True)
  print('PUBLICATION_ROLLED_BACK',flush=True);raise
 if legacy:print('Previous channel preserved:',next_link)
 (backup/'publication.json').write_text(json.dumps({'release':str(release),'previous_symlink':oldlink,'legacy_directory':str(next_link) if legacy else None}))
 print('DESKTOP_PUBLICATION_OK');print('Version:',VERSION);print('Backup:',backup)
 print('Release:',release)
if __name__=='__main__':main()
