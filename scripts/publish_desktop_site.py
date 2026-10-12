#!/usr/bin/env python3
"""Verify all desktop bundles, atomically publish them, and retain a rollback."""
import argparse,hashlib,json,os,re,shutil,stat,subprocess,tempfile,time,uuid,zipfile
from pathlib import Path,PurePosixPath
from datetime import datetime,timezone

VERSION='0.3.0-beta.2'
SHA='f12793b30e7cd6ee3494fd3ec90634bb060023fb'
TARGETS={
    'win-x64':('Adelia-latest-windows-x64.exe','beta.yml'),
    'macos-arm64':('Adelia-latest-macos-arm64.dmg','beta-mac.yml'),
    'macos-x64':('Adelia-latest-macos-x64.dmg','beta-mac.yml'),
}
SUFFIXES={'.exe','.dmg','.zip','.blockmap','.yml'}
SITE_ROOT=Path('/var/www/adeliatutor.ru/desktop-updates')
SITE_CONFIG=Path('/etc/nginx/sites-enabled/adeliatutor.ru')
BACKUP_DIR='/root'

def safe_name(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',name):
        raise ValueError('Unsafe bundle filename')
    return name

def extract_bundle(archive,destination,target):
    destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        entries=[i for i in z.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/')]
        manifests=[i for i in entries if PurePosixPath(i.filename).name=='manifest.json']
        if len(manifests)!=1:raise ValueError(f'{target}: exactly one manifest.json is required')
        info=manifests[0]
        if info.file_size>1024*1024:raise ValueError('Manifest is too large')
        parent=PurePosixPath(info.filename).parent
        if parent.is_absolute() or '..' in parent.parts:raise ValueError('Unsafe ZIP directory')
        lookup={}
        for entry in entries:
            p=PurePosixPath(entry.filename)
            if p.parent!=parent:continue
            if p.name in lookup:raise ValueError('Duplicate ZIP entry: '+p.name)
            if stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Symlink in bundle: '+p.name)
            lookup[p.name]=entry
        manifest=json.loads(z.read(info))
        if manifest.get('schema')!=2 or manifest.get('channel')!='beta' or manifest.get('version')!=VERSION or manifest.get('git_sha')!=SHA:
            raise ValueError(f'{target}: unexpected release identity')
        release_entry=lookup.get('release.json')
        if not release_entry or release_entry.file_size>1024*1024:raise ValueError('release.json missing or too large')
        release=json.loads(z.read(release_entry))
        if any(release.get(k)!=manifest.get(k) for k in ['channel','version','git_sha']):raise ValueError('Release metadata mismatch')
        files=manifest.get('files')
        if not isinstance(files,list) or not files or len(files)>100:raise ValueError('Invalid file manifest')
        names=set()
        for item in files:
            name=safe_name(item['name'])
            if name in names or Path(name).suffix.lower() not in SUFFIXES:raise ValueError('Unexpected file: '+name)
            names.add(name)
            entry=lookup.get(name);size=int(item['size']);digest=item['sha512']
            if not entry or size!=entry.file_size or not 0<size<=1024**3 or not re.fullmatch('[a-f0-9]{128}',digest):raise ValueError('Invalid file metadata: '+name)
            h=hashlib.sha512()
            with z.open(entry) as src,(destination/name).open('xb') as dst:
                for chunk in iter(lambda:src.read(1024*1024),b''):
                    h.update(chunk);dst.write(chunk)
            if h.hexdigest()!=digest:raise ValueError('Checksum mismatch: '+name)
            (destination/name).chmod(0o644)
        if not set(TARGETS[target])<=names:raise ValueError(f'{target}: installer or updater metadata missing')
        if target.startswith('macos-') and not any(n.endswith('.zip') for n in names):raise ValueError('macOS updater ZIP missing')
        for name,data in [('manifest.json',manifest),('release.json',release)]:
            (destination/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(destination/name).chmod(0o644)
    destination.chmod(0o755)
    return manifest

def atomic_file(path,content,mode=0o644):
    fd,tmp=tempfile.mkstemp(prefix='.desktop-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:out.write(content);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,mode)
        if path.exists():
            old=path.stat();os.chown(tmp,old.st_uid,old.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def atomic_link(path,target):
    tmp=path.parent/('.desktop-link-'+uuid.uuid4().hex)
    try:os.symlink(str(target),tmp);os.replace(tmp,path)
    finally:
        if os.path.lexists(tmp):os.unlink(tmp)

def snapshot(path,backup,index):
    row={'path':str(path)}
    if path.is_symlink():row.update(kind='link',target=os.readlink(path))
    elif path.is_file():
        saved=backup/f'previous-{index}';shutil.copy2(path,saved);saved.chmod(0o600)
        row.update(kind='file',saved=str(saved),mode=stat.S_IMODE(path.stat().st_mode))
    elif not path.exists():row.update(kind='absent')
    else:raise ValueError('Refusing to replace a directory: '+str(path))
    return row

def restore(row):
    path=Path(row['path'])
    if row['kind']=='link':atomic_link(path,row['target'])
    elif row['kind']=='file':atomic_file(path,Path(row['saved']).read_bytes(),row['mode'])
    elif os.path.lexists(path):path.unlink()

def nginx_config(original):
    if re.search(r'location[^\n{]*/desktop-updates/',original):raise ValueError('A desktop-updates location already exists; inspect it before replacing')
    marker=re.compile(r'(?m)^([ \t]*)root[ \t]+/var/www/adeliatutor\.ru/?[ \t]*;[ \t]*$')
    hits=list(marker.finditer(original))
    if len(hits)!=1:raise ValueError('Expected one HTTPS website root; nginx was not changed')
    hit=hits[0]
    block='''

    # Adelia desktop downloads and per-platform beta update feeds.
    location ^~ /desktop-updates/ {
        root /var/www/adeliatutor.ru;
        index index.html;
        autoindex off;
        default_type application/octet-stream;
        add_header Cache-Control "no-cache" always;
        add_header X-Content-Type-Options "nosniff" always;
        try_files $uri $uri/ =404;
    }
'''
    return original[:hit.end()]+block+original[hit.end():]

def run(*args):subprocess.run(args,check=True)

def curl(path,head=False):
    args=['curl','-fsS','--connect-timeout','5','--max-time','20','--resolve','adeliatutor.ru:443:127.0.0.1']
    if head:args.append('-I')
    args.append('https://adeliatutor.ru'+path)
    return subprocess.check_output(args)

def verify_http():
    for target,(alias,metadata) in TARGETS.items():
        data=json.loads(curl('/desktop-updates/beta/'+target+'/release.json'))
        if data.get('version')!=VERSION or data.get('git_sha')!=SHA:raise ValueError('HTTP metadata mismatch: '+target)
        curl('/desktop-updates/'+alias,head=True)
        curl('/desktop-updates/beta/'+target+'/'+metadata)
    if VERSION.encode() not in curl('/desktop-updates/'):raise ValueError('Download page is not available')

def rollback(backup,automatic=False):
    backup=Path(backup);state=json.loads((backup/'state.json').read_text());live=Path(state['live'])
    if not automatic and (not live.is_symlink() or os.readlink(live)!=state['new_target']):
        raise ValueError('A newer release is active; refusing to roll it back')
    for row in reversed(state['snapshots']):restore(row)
    atomic_file(Path(state['config']),Path(state['old_config']).read_bytes(),state['config_mode'])
    run('nginx','-t');run('systemctl','reload','nginx')
    print('DESKTOP_ROLLBACK=OK')

def publish(archives):
    root=SITE_ROOT
    config=SITE_CONFIG.resolve(strict=True)
    original=config.read_text();updated=nginx_config(original)
    backup=Path(tempfile.mkdtemp(prefix='desktop-publish-',dir=BACKUP_DIR));backup.chmod(0o700)
    stage=backup/'verified';stage.mkdir()
    manifests={}
    for target,archive in zip(TARGETS,archives):
        manifests[target]=extract_bundle(archive,stage/target,target)
        print('VERIFIED='+target,flush=True)
    page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Скачать Аделию</title><style>body{font:17px/1.5 system-ui;background:#f8f5ff;color:#282238;margin:0;padding:32px}main{max-width:800px;margin:auto}a{color:#6440c9}article{background:white;border-radius:18px;padding:24px;margin:16px 0;border:1px solid #e6deef}h1{font-size:32px}small{color:#73687c}</style><main><a href="/">← На сайт Аделии</a><h1>Аделия для компьютера</h1><p>Версия 0.3.0-beta.2 · кабинет ученика, родителя и преподавателя.</p><article><h2>Windows</h2><a href="/desktop-updates/Adelia-latest-windows-x64.exe">Скачать установщик Windows x64</a></article><article><h2>Mac с Apple Silicon</h2><p>Для Mac с процессорами серии M.</p><a href="/desktop-updates/Adelia-latest-macos-arm64.dmg">Скачать для Mac Apple Silicon</a></article><article><h2>Mac с Intel</h2><a href="/desktop-updates/Adelia-latest-macos-x64.dmg">Скачать для Mac Intel</a></article><p>Откройте .dmg и перенесите Аделию в «Программы». На Windows запустите .exe.</p><small>Бета-сборки пока без цифровой подписи. Для телефона доступен <a href="/app/">личный кабинет</a>.</small></main></html>'''
    (stage/'index.html').write_text(page);(stage/'index.html').chmod(0o644)
    for directory in [root,root/'releases',root/'releases'/'beta']:
        directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o755)
    release_id=VERSION+'--'+SHA[:12]+'--'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    destination=root/'releases'/'beta'/release_id
    shutil.copytree(stage,destination)
    for folder,dirs,files in os.walk(destination):
        os.chmod(folder,0o755)
        for name in files:os.chmod(Path(folder)/name,0o644)
    live=root/'beta'
    links=[(root/alias,'beta/'+target+'/'+alias) for target,(alias,_) in TARGETS.items()]
    links.append((root/'index.html','beta/index.html'))
    paths=[p for p,_ in links]+[live]
    snapshots=[snapshot(p,backup,i) for i,p in enumerate(paths)]
    old_config=backup/'nginx-before.conf';shutil.copy2(config,old_config);old_config.chmod(0o600)
    state={'live':str(live),'new_target':str(destination),'config':str(config),'old_config':str(old_config),'config_mode':stat.S_IMODE(config.stat().st_mode),'snapshots':snapshots}
    (backup/'state.json').write_text(json.dumps(state,indent=2));shutil.copy2(__file__,backup/'publisher.py')
    try:
        atomic_file(config,updated.encode(),state['config_mode']);run('nginx','-t')
        for path,target in links:atomic_link(path,target)
        atomic_link(live,destination)
        run('systemctl','reload','nginx')
        for attempt in range(6):
            try:verify_http();break
            except (subprocess.CalledProcessError,ValueError):
                if attempt==5:raise
                time.sleep(1)
    except BaseException:
        try:rollback(backup,automatic=True)
        except Exception as error:print('ROLLBACK_FAILED:',error)
        print('Publication failed. Backup:',backup,flush=True)
        raise
    print('DOWNLOADS_PUBLISHED=OK')
    print('VERSION='+VERSION);print('PAGE=https://adeliatutor.ru/desktop-updates/')
    for alias,_ in TARGETS.values():print('DOWNLOAD=https://adeliatutor.ru/desktop-updates/'+alias)
    print('ROLLBACK=python3 '+str(backup/'publisher.py')+' --rollback '+str(backup))
    shutil.rmtree(stage)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('archives',nargs='*');parser.add_argument('--rollback');args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run on the Ubuntu server as root')
    import fcntl
    with open('/run/adelia-desktop-publish.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.rollback:rollback(args.rollback)
        else:
            if len(args.archives)!=3:raise SystemExit('Pass Windows, Mac ARM and Mac Intel ZIPs in that order')
            publish(args.archives)

if __name__=='__main__':main()
