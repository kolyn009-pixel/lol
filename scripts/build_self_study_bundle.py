"""Package an explicit source allowlist, without databases, credentials or work checkout."""
import argparse,hashlib,io,json,re,tarfile
from pathlib import Path
from install_self_study import MODULES,SOURCE


def files():
 names=set(MODULES)|{'scripts/configure_self_study_ai.py','scripts/install_self_study.py','scripts/install_self_study_bot.py','scripts/self_study_server_probe.py','scripts/build_self_study_bundle.py','web_backend/self_study_bot.py','handlers/self_study_family.py','vk_adapter/self_study_family.py','web_backend/api_v7.py','desktop/bundled_ui_manifest.js'}
 names|={str(p.relative_to(SOURCE)) for pattern in ('self_study_*selftest.py','self_study_*selftest.cjs') for p in (SOURCE/'scripts').glob(pattern)}
 names|={str(p.relative_to(SOURCE)) for p in (SOURCE/'docs').glob('SELF_STUDY*.md')}
 result={}
 for name in sorted(names):
  p=SOURCE/name
  if p.is_symlink() or not p.resolve().is_relative_to(SOURCE):raise RuntimeError('Source escapes allowlist root: '+name)
  result[name]=p.read_bytes()
 return result


def verify(root):
 root=root.resolve();manifest=json.loads((root/'MANIFEST.json').read_text())
 for name,digest in manifest['files'].items():
  p=root/name
  if not p.resolve().is_relative_to(root) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise RuntimeError('Checksum mismatch: '+name)
 return manifest


def build(output,commit):
 if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Specify exact source commit')
 data=files();manifest={'revision':commit,'files':{name:hashlib.sha256(content).hexdigest() for name,content in data.items()},'note':'Source checksum manifest detects corruption, not authorship. No deployment performed.'}
 data['MANIFEST.json']=json.dumps(manifest,indent=2).encode();output.parent.mkdir(parents=True,exist_ok=True)
 with tarfile.open(output,'w:gz') as archive:
  for name,content in sorted(data.items()):
   entry=tarfile.TarInfo('adelia-family-languages/'+name);entry.size=len(content);entry.mode=0o644;entry.mtime=0;archive.addfile(entry,io.BytesIO(content))
 return len(manifest['files'])


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--commit');p.add_argument('--verify',type=Path);a=p.parse_args()
 if a.verify:print(json.dumps({'verified_revision':verify(a.verify)['revision']}));return
 if not a.output or not a.commit:p.error('--output and --commit are required')
 print(json.dumps({'files':build(a.output,a.commit),'archive':str(a.output)}))

if __name__=='__main__':main()
