"""One Adelia mark for HTML, role manifests and public favicon aliases."""
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import os
import re
import struct

VERSION='20261022-unified2'
PREFIX='/app/assets/icons/adelia-mark-'
def icon_url(size):return PREFIX+str(size)+'.png?v='+VERSION
ICON_TAGS=(
 '<link rel="icon" type="image/png" sizes="32x32" href="'+icon_url(32)+'">'
 '<link rel="icon" type="image/png" sizes="192x192" href="'+icon_url(192)+'">'
 '<link rel="shortcut icon" type="image/x-icon" href="/app/assets/icons/adelia-mark.ico?v='+VERSION+'">'
 '<link rel="apple-touch-icon" sizes="180x180" href="'+icon_url(180)+'">'
)

class HeadParser(HTMLParser):
 def __init__(self,source):
  super().__init__(convert_charrefs=False)
  self.source=source;self.lines=source.splitlines(keepends=True);self.edits=[];self.in_head=False;self.head_end=None;self.html_start=None;self.body_start=None;self.brand_stack=[];self.brand_images=[]
 def source_index(self):
  line,column=self.getpos();return sum(map(len,self.lines[:line-1]))+column
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  classes=set(str(attrs.get('class') or '').lower().split())
  is_brand=(self.brand_stack[-1][1] if self.brand_stack else False) or bool(classes & {'brand','logo','site-brand','site-logo','brand-logo','navbar-brand'})
  if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.brand_stack.append((tag,is_brand))
  if tag=='html':self.html_start=self.source_index()+len(self.get_starttag_text())
  if tag in {'body','main','header','section','div'} and not self.in_head and self.body_start is None:self.body_start=self.source_index()
  if tag=='head':self.in_head=True
  if tag=='link' and self.in_head:
   rel=set(str(attrs.get('rel') or '').lower().split())
   if rel & {'icon','apple-touch-icon','apple-touch-icon-precomposed','mask-icon'}:
    start=self.source_index();self.edits.append((start,start+len(self.get_starttag_text()),''))
  if tag=='img':
   src=str(attrs.get('src') or '')
   if is_brand or re.search(r'(?:^|/)(?:adelia-(?:icon-\d+|favicon-\d+|apple-touch-icon-\d+|logo)[^/?]*)(?:\?|$)',src):
    self.brand_images.append(src)
    raw=self.get_starttag_text()
    new=re.sub(r'''(?i)(\ssrc\s*=\s*)(?:"[^"]*"|'[^']*'|[^\s>]+)''',lambda m:m[1]+'"'+icon_url(180)+'"',raw,count=1)
    if not re.search(r'(?i)\ssrc\s*=',new):new=re.sub(r'(/?>)$',lambda m:' src="'+icon_url(180)+'"'+m[1],new)
    new=re.sub(r'''(?i)(\sdata-src\s*=\s*)(?:"[^"]*"|'[^']*'|[^\s>]+)''',lambda m:m[1]+'"'+icon_url(180)+'"',new)
    new=re.sub(r'(?i)\s+srcset\s*=\s*([\'"]).*?\1','',new)
    start=self.source_index();self.edits.append((start,start+len(raw),new))
  if tag=='source' and is_brand:
   raw=self.get_starttag_text();start=self.source_index();self.edits.append((start,start+len(raw),''))
 def handle_endtag(self,tag):
  if tag=='head':self.head_end=self.source_index();self.in_head=False
  for i in range(len(self.brand_stack)-1,-1,-1):
   if self.brand_stack[i][0]==tag:del self.brand_stack[i:];break

def transform_html(source):
 parser=HeadParser(source);parser.feed(source)
 if parser.head_end is None and parser.html_start is not None and parser.body_start is not None:
  # The desktop publisher emits valid HTML with an implicit head.
  source=source[:parser.html_start]+'<head>'+source[parser.html_start:parser.body_start]+'</head>'+source[parser.body_start:]
  parser=HeadParser(source);parser.feed(source)
 if parser.head_end is None:raise ValueError('HTML head not found')
 edits=parser.edits+[(parser.head_end,parser.head_end,ICON_TAGS)]
 for start,end,value in sorted(edits,reverse=True):source=source[:start]+value+source[end:]
 return source

def transform_manifest(source):
 value=json.loads(source)
 value['icons']=[{'src':icon_url(192),'sizes':'192x192','type':'image/png','purpose':'any'},
                 {'src':icon_url(512),'sizes':'512x512','type':'image/png','purpose':'any'},
                 {'src':icon_url(512),'sizes':'512x512','type':'image/png','purpose':'maskable'}]
 return json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n'

def favicon(png):
 if png[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',png[16:24])!=(32,32):raise ValueError('Expected canonical 32px PNG')
 # ICO supports a PNG payload: preserve the exact source pixels.
 return struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',32,32,0,0,1,32,len(png),22)+png

def resolve_site_file(path,roots):
 """Preserve an alias; write its physical target only inside this site's roots."""
 resolved=path.resolve(strict=True)
 if not any(resolved.is_relative_to(root.resolve()) for root in roots):
  raise RuntimeError('Site alias points outside Adelia roots: '+str(path))
 if not resolved.is_file():raise RuntimeError('Expected a site file: '+str(path))
 return resolved

def install(commit):
 import fcntl,subprocess,tempfile,urllib.request
 if os.geteuid()!=0:raise SystemExit('Run on the Ubuntu server as root')
 if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('A full pinned commit is required')
 with open('/run/adelia-learning-deploy.lock','a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  release=Path('/opt/adelia-current').resolve(strict=True);public=Path('/var/www/adeliatutor.ru')
  if release.parent!=Path('/opt/adelia-releases') or public.resolve()!=public or not public.is_dir():raise RuntimeError('Unexpected site roots')
  subprocess.run(['nginx','-t'],check=True)
  updates={};pngs={}
  for size in (32,180,192,512):
   png=subprocess.check_output(['git','-C','/opt/tutorbot','show',commit+f':web/assets/icons/adelia-mark-{size}.png'])
   if png[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',png[16:24])!=(size,size):raise ValueError('Invalid icon asset')
   pngs[size]=png;updates[release/f'web/assets/icons/adelia-mark-{size}.png']=png
  ico=favicon(pngs[32]);updates[release/'web/assets/icons/adelia-mark.ico']=ico
  site_roots=(release/'web',public)
  for root in (release/'web',public):
   for path in root.rglob('*.html'):
    # Retired desktop releases are rollback snapshots. The live index alias
    # below resolves to the one active release that should be branded.
    if root==public and path.relative_to(public).parts[:2]==('desktop-updates','releases'):continue
    path=resolve_site_file(path,site_roots)
    # Only full HTML documents belong to this transformation.
    source=path.read_text()
    if re.search(r'<(?:head|html)\b',source,re.I):updates[path]=transform_html(source).encode()
   for path in root.rglob('*.webmanifest'):
    path=resolve_site_file(path,site_roots)
    updates[path]=transform_manifest(path.read_text()).encode()
  # Compatibility for old bookmarks and browsers which request favicon.ico themselves.
  for name,payload in {'favicon.ico':ico,'apple-touch-icon.png':pngs[180],
    'adelia-favicon-32.png':pngs[32],'adelia-apple-touch-icon-180.png':pngs[180]}.items():updates[public/name]=payload
  backup=Path(tempfile.mkdtemp(prefix='unified-brand-20261022-',dir='/opt/tutorbot/backups'));os.chmod(backup,0o700)
  originals={};metadata={}
  for i,(path,data) in enumerate(updates.items()):
   if path.is_symlink() or path.parent.resolve()!=path.parent:raise RuntimeError('Unexpected asset link')
   original=path.read_bytes() if path.exists() else None;originals[path]=original
   metadata[path]=path.stat() if path.exists() else None
   if original is not None:(backup/str(i)).write_bytes(original)
  (backup/'files.json').write_text(json.dumps([{'path':str(p),'backup':str(i) if originals[p] is not None else None} for i,p in enumerate(updates)],indent=2))
  def replace(path,data,restore=False):
   path.parent.mkdir(parents=True,exist_ok=True)
   fd,name=tempfile.mkstemp(prefix='.adelia-brand-',dir=path.parent)
   try:
    with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    st=metadata[path];mode=(st.st_mode & 0o777) if st else 0o644
    if not restore and path.suffix in {'.png','.ico'}:mode=0o644
    os.chmod(name,mode)
    if st:os.chown(name,st.st_uid,st.st_gid)
    os.replace(name,path)
   finally:
    if os.path.exists(name):os.unlink(name)
  written=[];directories=[]
  try:
   for directory in (release/'web/assets',release/'web/assets/icons'):
    old_mode=directory.stat().st_mode & 0o777 if directory.exists() else None
    directories.append((directory,old_mode));directory.mkdir(parents=True,exist_ok=True)
    os.chmod(directory,(old_mode if old_mode is not None else 0o700)|0o555)
   for path,data in updates.items():
    st=metadata[path];wrong_mode=path.suffix in {'.png','.ico'} and st is not None and (st.st_mode & 0o777)!=0o644
    if originals[path]!=data or wrong_mode:replace(path,data);written.append(path)
   for route in ('/','/app/','/app/teacher.html','/app/parent/','/start/','/onboarding/'):
    served=subprocess.check_output(['curl','--resolve','adeliatutor.ru:443:127.0.0.1','--max-time','15','-fsS','https://adeliatutor.ru'+route],timeout=20).decode()
    if icon_url(32) not in served or icon_url(180) not in served:raise RuntimeError('Page serves a different icon: '+route)
    parsed=HeadParser(served);parsed.feed(served)
    if any(url!=icon_url(180) for url in parsed.brand_images):raise RuntimeError('Header logo was not updated: '+route)
   for size in (32,180,192,512):
    served=subprocess.check_output(['curl','--resolve','adeliatutor.ru:443:127.0.0.1','--max-time','15','-fsS','https://adeliatutor.ru'+icon_url(size)],timeout=20)
    if served!=pngs[size]:raise RuntimeError('Icon response mismatch')
  except BaseException:
   for path in reversed(written):
    if originals[path] is None:path.unlink(missing_ok=True)
    else:replace(path,originals[path],restore=True)
   for directory,old_mode in reversed(directories):
    if old_mode is not None:os.chmod(directory,old_mode)
    elif directory.exists():directory.rmdir()
   print('Brand update failed; original files restored. Backup:',backup);raise
  print('UNIFIED_ADELIA_ICON_OK')
  print('Pages and icon responses: OK')
  print('Backup:',backup)

if __name__=='__main__':
 import sys
 install(sys.argv[1])
