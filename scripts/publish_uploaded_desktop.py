"""Verify all three local bundles and atomically publish each channel's set.

No nginx edits. Stable publication can bridge existing beta clients to the same
stable binaries. Default is preparation/check only; --apply switches channels.
"""
import argparse,ctypes,fcntl,hashlib,json,os,re,shutil,stat,subprocess,tempfile,zipfile
from pathlib import Path
WEB_ROOT=Path('/var/www/adeliatutor.ru/desktop-updates')
BACKUPS=Path('/opt/tutorbot/backups')
PREP_ROOT=Path('/opt/tutorbot')
LOCK_FILE='/run/adelia-desktop-publication.lock'
TARGETS={'win-x64':'Adelia-latest-windows-x64.exe','macos-x64':'Adelia-latest-macos-x64.dmg','macos-arm64':'Adelia-latest-macos-arm64.dmg'}
def digest(p,kind='sha512'):
 h=hashlib.new(kind)
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def exchange(a,b):
 lib=ctypes.CDLL(None,use_errno=True)
 if not hasattr(lib,'renameat2'):raise RuntimeError('Atomic directory exchange is unavailable')
 if lib.renameat2(-100,os.fsencode(a),-100,os.fsencode(b),2):raise OSError(ctypes.get_errno(),'Atomic exchange failed')
def get(url,head=False):
 return subprocess.check_output(['curl','--noproxy','*','--resolve','adeliatutor.ru:443:127.0.0.1','-fsS','--max-time','30']+(['-I'] if head else [])+[url])
def metadata(target,channel):return ('latest' if channel=='stable' else 'beta')+('' if target=='win-x64' else '-mac')+'.yml'
def verify_upload(upload,stage,version,sha,channel):
 checks={}
 for line in (upload/'SHA256SUMS').read_text().splitlines():
  if not line.strip():continue
  value,name=line.split(maxsplit=1);checks[name.lstrip('*')]=value
 for target,alias in TARGETS.items():
  archive=upload/(target+'.zip')
  if checks.get(archive.name)!=digest(archive,'sha256'):raise RuntimeError('Upload checksum mismatch: '+archive.name)
  dest=stage/target;dest.mkdir()
  with zipfile.ZipFile(archive) as z:
   infos=z.infolist();names=[x.filename for x in infos]
   if len(names)!=len(set(names)) or len(names)>100 or sum(x.file_size for x in infos)>3*1024**3:raise RuntimeError('Unexpected archive structure')
   for x in infos:
    if Path(x.filename).name!=x.filename or stat.S_ISLNK(x.external_attr>>16) or x.is_dir():raise RuntimeError('Invalid archive entry')
   z.extractall(dest)
  manifest=json.loads((dest/'manifest.json').read_text());release=json.loads((dest/'release.json').read_text())
  for obj in (manifest,release):
   if obj.get('schema')!=2 or obj.get('version')!=version or obj.get('git_sha')!=sha or obj.get('channel')!=channel:raise RuntimeError('Bundle identity mismatch: '+target)
  entries=manifest.get('files',[]);names=[x['name'] for x in entries]
  if len(names)!=len(set(names)) or alias not in names or metadata(target,channel) not in names:raise RuntimeError('Incomplete updater bundle: '+target)
  for item in entries:
   if Path(item['name']).name!=item['name']:raise RuntimeError('Invalid manifest path')
   f=dest/item['name']
   if not f.is_file() or f.stat().st_size!=item['size'] or digest(f)!=item['sha512']:raise RuntimeError('Artifact checksum mismatch: '+item['name'])
  print('VERIFIED:',target,flush=True)
def bridge_beta(stable,bridge):
 for target in TARGETS:
  source=stable/target;dest=bridge/target;dest.mkdir(parents=True)
  for f in source.iterdir():
   if f.name not in ('manifest.json','release.json'):os.link(f,dest/f.name)
  feed=dest/metadata(target,'beta');shutil.copy2(source/metadata(target,'stable'),feed)
  m=json.loads((source/'manifest.json').read_text());m['channel']='beta';m['stable_bridge']=True
  m['files'].append({'name':feed.name,'size':feed.stat().st_size,'sha512':digest(feed)})
  (dest/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
  release=json.loads((source/'release.json').read_text());release.update(channel='beta',stable_bridge=True)
  (dest/'release.json').write_text(json.dumps(release,ensure_ascii=False,indent=2))
def switch(live,target):
 tmp=live.with_name('.'+live.name+'-next-'+str(os.getpid()));tmp.symlink_to(target)
 old=os.path.lexists(live);legacy=old and live.is_dir() and not live.is_symlink();oldlink=os.readlink(live) if old and live.is_symlink() else None
 if old and not legacy and oldlink is None:tmp.unlink();raise RuntimeError('Unexpected channel path: '+str(live))
 if legacy:exchange(tmp,live)
 else:os.replace(tmp,live)
 return {'live':live,'oldlink':oldlink,'legacy':legacy,'saved':tmp}
def restore(state):
 live=state['live']
 if state['legacy']:exchange(state['saved'],live)
 elif state['oldlink'] is not None:
  tmp=live.with_name('.restore-'+live.name+'-'+str(os.getpid()));tmp.symlink_to(state['oldlink']);os.replace(tmp,live)
 else:live.unlink(missing_ok=True)
def publish(stage,version,sha,channel,bridge):
 WEB_ROOT.mkdir(parents=True,exist_ok=True);BACKUPS.mkdir(parents=True,exist_ok=True)
 target=WEB_ROOT/'releases'/channel/(version+'--'+sha[:12]);target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():raise RuntimeError('Release already exists; inspect before replacing: '+str(target))
 shutil.copytree(stage,target)
 paths={channel:target}
 if bridge:
  beta=WEB_ROOT/'releases'/'beta'/(version+'--'+sha[:12]+'-stable-bridge')
  if beta.exists():raise RuntimeError('Beta bridge already exists')
  beta.mkdir(parents=True);bridge_beta(target,beta);paths['beta']=beta
 for folder in paths.values():
  for d,_,files in os.walk(folder):
   os.chmod(d,0o755)
   for name in files:os.chmod(Path(d)/name,0o644)
 backup=Path(tempfile.mkdtemp(prefix='desktop-before-',dir=BACKUPS));channels=[];aliases=[]
 try:
  for name,path in paths.items():channels.append(switch(WEB_ROOT/name,path))
  for name,alias in TARGETS.items():
   dst=WEB_ROOT/alias;saved=backup/alias;exists=os.path.lexists(dst)
   if dst.is_dir():raise RuntimeError('Alias is a directory: '+alias)
   if exists:shutil.copy2(dst,saved,follow_symlinks=False)
   aliases.append((dst,saved,exists));tmp=WEB_ROOT/('.alias-'+str(os.getpid()));tmp.symlink_to(channel+'/'+name+'/'+alias);os.replace(tmp,dst)
  for name,folder in paths.items():
   for target_name,alias in TARGETS.items():
    base='https://adeliatutor.ru/desktop-updates/'+name+'/'+target_name+'/'
    for file in ('manifest.json','release.json'):
     data=json.loads(get(base+file))
     if data.get('version')!=version or data.get('git_sha')!=sha or data.get('channel')!=name:raise RuntimeError('Wrong served identity: '+base+file)
    feed=get(base+metadata(target_name,name))
    if feed!=(folder/target_name/metadata(target_name,name)).read_bytes():raise RuntimeError('Served updater feed differs from verified bundle')
    for url in (base+alias,'https://adeliatutor.ru/desktop-updates/'+alias):
     headers=get(url,True).decode().lower();size=(folder/target_name/alias).stat().st_size
     if 'text/html' in headers or 'content-length: '+str(size) not in headers:raise RuntimeError('Installer HTTP mismatch: '+url)
    print('HTTP_OK:',name,target_name,flush=True)
 except BaseException:
  for dst,saved,exists in reversed(aliases):
   dst.unlink(missing_ok=True)
   if exists:
    tmp=WEB_ROOT/('.restore-'+dst.name);shutil.copy2(saved,tmp,follow_symlinks=False);os.replace(tmp,dst)
  for state in reversed(channels):restore(state)
  print('PUBLICATION_ROLLED_BACK',flush=True);raise
 (backup/'publication.json').write_text(json.dumps({'version':version,'git_sha':sha,'channels':[{k:str(v) for k,v in s.items()} for s in channels]},indent=2))
 print('DESKTOP_PUBLICATION_OK\nVersion: '+version+'\nBackup: '+str(backup))
def main():
 p=argparse.ArgumentParser();p.add_argument('--git-sha',required=True);p.add_argument('--uploaded',type=Path);p.add_argument('--apply',action='store_true');p.add_argument('--bridge-beta',action='store_true');a=p.parse_args()
 if not re.fullmatch('[0-9a-f]{40}',a.git_sha):raise RuntimeError('Full expected source SHA is required')
 version=json.loads((Path(__file__).resolve().parents[1]/'desktop/package.json').read_text())['version'];channel='beta' if '-beta.' in version else 'stable'
 if a.bridge_beta and channel!='stable':raise RuntimeError('Only a stable release can bridge beta clients')
 upload=a.uploaded or Path('/root/adelia-upload')/(version+'-'+a.git_sha[:12])
 if os.geteuid()!=0:raise RuntimeError('Run as root')
 lock=open(LOCK_FILE,'a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 with tempfile.TemporaryDirectory(prefix='desktop-verified-',dir=PREP_ROOT) as name:
  stage=Path(name);verify_upload(upload,stage,version,a.git_sha,channel)
  if not a.apply:print('ALL_DESKTOP_BUNDLES_VERIFIED; no published channels changed');return
  publish(stage,version,a.git_sha,channel,a.bridge_beta)
if __name__=='__main__':main()
