"""Publish desktop installation help and a homepage link, preserving all binaries."""
import fcntl,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path

VERSION='20261022-install-guide1'
PAGE='web/desktop_install.html'
TARGETS={'win-x64':'Adelia-latest-windows-x64.exe','macos-arm64':'Adelia-latest-macos-arm64.dmg','macos-x64':'Adelia-latest-macos-x64.dmg'}

def patch_homepage(source):
    if 'id="adelia-install-link"' not in source:
        pattern=r'(<div\b[^>]*class=[\"\'][^\"\']*\bhero-actions\b[^\"\']*[\"\'][^>]*>[\s\S]*?</div>)'
        addition='<p id="adelia-install-link" style="margin:16px 0 0"><a class="hero-secondary" style="max-width:100%;box-sizing:border-box;white-space:normal;text-align:center" href="/desktop-updates/">Скачать приложение для Windows и Mac ↓</a></p>'
        source,count=re.subn(pattern,lambda m:m[1]+addition,source,count=1)
        if count!=1:raise RuntimeError('Homepage structure changed; original page preserved')
    if 'id="adelia-install-footer"' not in source:
        footer=list(re.finditer(r'<footer\b[^>]*>[\s\S]*?</footer>',source,re.I))
        if len(footer)!=1:raise RuntimeError('Expected one homepage footer')
        a,b=footer[0].span();part=source[a:b];pos=part.rfind('</div>')
        if pos<0:pos=part.rfind('</footer>')
        part=part[:pos]+'<a id="adelia-install-footer" href="/desktop-updates/">Скачать и установить Аделию</a>'+part[pos:];source=source[:a]+part+source[b:]
    return source

def atomic(path,data,mode=0o644,owner=None):
    fd,tmp=tempfile.mkstemp(prefix='.adelia-install-guide-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.chmod(tmp,mode)
        if owner:os.chown(tmp,owner.st_uid,owner.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def restore(backup,rows):
    for row in reversed(rows):
        path=Path(row['path'])
        if row['kind']=='link':
            fd,tmp=tempfile.mkstemp(dir=path.parent);os.close(fd);os.unlink(tmp)
            try:os.symlink(row['target'],tmp);os.replace(tmp,path)
            finally:
                if os.path.lexists(tmp):os.unlink(tmp)
        elif row['kind']=='file':
            saved=backup/row['saved'];s=saved.stat();atomic(path,saved.read_bytes(),int(row['mode']),s)
        else:path.unlink(missing_ok=True)

def install(commit):
    if os.geteuid()!=0:raise SystemExit('Run inside SSH as root')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise SystemExit('A full pinned commit is required')
    with open('/run/adelia-learning-deploy.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        public=Path('/var/www/adeliatutor.ru');downloads=public/'desktop-updates';release=Path('/opt/adelia-current').resolve()
        if public.resolve()!=public or downloads.resolve()!=downloads or not downloads.is_dir():raise RuntimeError('Unexpected website directory')
        home=(public/'index.html').resolve(strict=True)
        roots=[public,release/'web',Path('/opt/tutorbot/web')]
        if not home.is_file() or not any(home.is_relative_to(r) for r in roots):raise RuntimeError('Unexpected homepage target')
        guide=downloads/'index.html'
        if guide.exists() and guide.is_dir():raise RuntimeError('Download index is a directory')
        def curl(path,head=False):
            cmd=['curl','--resolve','adeliatutor.ru:443:127.0.0.1','--max-time','15','-fsS']
            if head:cmd.append('-I')
            return subprocess.check_output(cmd+['https://adeliatutor.ru'+path],timeout=20)
        versions=[];builds=[]
        for target,alias in TARGETS.items():
            root='/desktop-updates/beta/'+target+'/'
            manifest=json.loads(curl(root+'manifest.json'));release_meta=json.loads(curl(root+'release.json'))
            entry=next(x for x in manifest['files'] if x['name']==alias)
            if manifest['version']!=release_meta['version'] or manifest['git_sha']!=release_meta['git_sha']:raise RuntimeError('Release metadata mismatch: '+target)
            headers=curl('/desktop-updates/'+alias,True).decode('latin-1')
            if not re.search(r'^HTTP/\S+ 200\b',headers,re.M):raise RuntimeError('Installer is not publicly available: '+alias)
            lengths=re.findall(r'^content-length:\s*(\d+)',headers,re.I|re.M)
            if not lengths or int(lengths[-1])!=int(entry['size']) or int(entry['size'])<10*1024*1024:raise RuntimeError('Unexpected installer size: '+alias)
            versions.append(manifest['version']);builds.append(manifest['git_sha'])
        if len(set(versions))!=1 or len(set(builds))!=1:raise RuntimeError('Desktop builds belong to different releases')
        page=subprocess.check_output(['git','-C','/opt/tutorbot','show',commit+':'+PAGE])
        text=page.decode('utf-8')
        for alias in TARGETS.values():
            if '/desktop-updates/'+alias not in text:raise RuntimeError('Missing installer link')
        updates={guide:page,home:patch_homepage(home.read_text()).encode()}
        root=Path('/opt/tutorbot/backups');root.mkdir(parents=True,exist_ok=True)
        backup=Path(tempfile.mkdtemp(prefix='install-guide-20261022-',dir=root));os.chmod(backup,0o700);rows=[]
        for n,path in enumerate(updates):
            row={'path':str(path)}
            if path.is_symlink():row.update(kind='link',target=os.readlink(path))
            elif path.is_file():
                s=path.stat();saved=str(n);shutil.copy2(path,backup/saved);row.update(kind='file',saved=saved,mode=s.st_mode&0o777)
            else:row['kind']='absent'
            rows.append(row)
        (backup/'files.json').write_text(json.dumps(rows));shutil.copy2(__file__,backup/'installer.py')
        (backup/'rollback.sh').write_text('#!/bin/bash\nset -euo pipefail\npython3 "$(dirname "$0")/installer.py" --rollback "$(dirname "$0")"\n');os.chmod(backup/'rollback.sh',0o700)
        try:
            # Replace only the download page symlink itself. Installer/update links
            # and their manifests remain attached to the existing beta release.
            for path,data in updates.items():
                s=path.stat() if path.is_file() else None
                atomic(path,data,(s.st_mode&0o777) if path==home and s else 0o644,s)
            if curl('/desktop-updates/?v='+VERSION)!=page:raise RuntimeError('Served install guide mismatch')
            if curl('/?v='+VERSION)!=updates[home]:raise RuntimeError('Served homepage mismatch')
            for alias in TARGETS.values():curl('/desktop-updates/'+alias,True)
        except BaseException:
            restore(backup,rows);print('INSTALL_GUIDE_FAILED; original pages restored. Backup:',backup);raise
        print('INSTALL_GUIDE_OK')
        print('Downloads: https://adeliatutor.ru/desktop-updates/')
        print('Desktop version:',versions[0]);print('Backup:',backup);print('Rollback: bash',backup/'rollback.sh')

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--rollback':
        backup=Path(sys.argv[2]);restore(backup,json.loads((backup/'files.json').read_text()));print('INSTALL_GUIDE_ROLLBACK_OK')
    else:install(sys.argv[1])
