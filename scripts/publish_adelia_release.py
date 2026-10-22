#!/usr/bin/env python3
"""Publish one complete beta release from three verified bundle ZIPs."""
import argparse, importlib.util, json, os, re, tempfile, zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('desktop_publisher',Path(__file__).with_name('publish_desktop_site.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

def semver(value):
    match=re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([A-Za-z0-9.-]+))?',value)
    if not match:raise ValueError('Invalid version: '+value)
    a,b,c,pre=match.groups()
    identifiers=tuple((0,int(x)) if x.isdigit() else (1,x) for x in pre.split('.')) if pre else ()
    return int(a),int(b),int(c),1 if pre is None else 0,identifiers

def inspect_bundles(directory):
    found={};identity=None
    for archive in sorted(directory.glob('*.zip')):
        with zipfile.ZipFile(archive) as z:
            candidates=[i for i in z.infolist() if Path(i.filename).name=='manifest.json' and not i.filename.startswith('__MACOSX/')]
            if len(candidates)!=1 or candidates[0].file_size>1024*1024:raise ValueError('Not a release bundle: '+archive.name)
            m=json.loads(z.read(candidates[0]))
        names={x['name'] for x in m.get('files',[])}
        targets=[target for target,(alias,_) in p.TARGETS.items() if alias in names]
        if len(targets)!=1 or targets[0] in found:raise ValueError('Duplicate or unknown platform: '+archive.name)
        version,sha=m.get('version',''),m.get('git_sha','')
        semver(version)
        if m.get('channel')!='beta' or not re.fullmatch(r'[a-f0-9]{40}',sha):raise ValueError('Expected a beta release with full commit identity')
        current=(version,sha)
        if identity is not None and identity!=current:raise ValueError('Mixed releases: all three ZIPs must have the same version and commit')
        identity=current;found[targets[0]]=archive
    if set(found)!=set(p.TARGETS):raise ValueError('Provide exactly three bundle ZIPs: Windows x64, macOS arm64 and macOS x64')
    return identity,[found[t] for t in p.TARGETS]

def validate(directory):
    (version,sha),archives=inspect_bundles(directory)
    previous=p.SITE_ROOT/'beta/win-x64/release.json'
    if previous.is_file():
        old=json.loads(previous.read_text())
        if semver(version)<semver(old['version']):raise ValueError('Refusing to publish an older version; use the recorded rollback instead')
        if version==old['version'] and sha!=old['git_sha']:raise ValueError('Increase the version before replacing an existing version with another build')
    p.VERSION,p.SHA=version,sha
    with tempfile.TemporaryDirectory(prefix='adelia-release-preflight-') as tmp:
        for target,archive in zip(p.TARGETS,archives):p.extract_bundle(archive,Path(tmp)/target,target)
    return version,sha,archives

def main():
    import fcntl
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path,help='Directory containing exactly three release bundle ZIPs');parser.add_argument('--check',action='store_true',help='Validate without publishing');args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run on the server as root')
    with open('/run/adelia-desktop-publish.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        version,sha,archives=validate(args.directory)
        print('RELEASE_PREFLIGHT=OK',version,sha,flush=True)
        if not args.check:p.publish(archives)
if __name__=='__main__':main()
