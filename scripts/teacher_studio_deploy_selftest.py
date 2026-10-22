#!/usr/bin/env python3
import argparse, contextlib, importlib.util, io, shutil, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('studio_deploy',ROOT/'scripts/deploy_teacher_studio.py');ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
# Local source fixtures are obtained from the pinned predecessor for this check.
parser=argparse.ArgumentParser();parser.add_argument('--base-fixtures',type=Path);args=parser.parse_args()
base=lambda p:(args.base_fixtures/Path(p).name).read_bytes() if args.base_fixtures else subprocess.check_output(['git','-C',str(ROOT),'show',ui.BASE+':'+p])
payload=lambda p:(ROOT/p).read_bytes()
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp)/'live';(root/'web').mkdir(parents=True);backups=Path(tmp)/'backups';backups.mkdir()
 for p in (ROOT/'web').iterdir():
  if p.is_file():shutil.copy2(p,root/'web'/p.name)
 for name in ui.CHANGED:(root/'web'/name).write_bytes(base('web/'+name))
 for name in ui.NEW:(root/'web'/name).unlink(missing_ok=True)
 live=root/'web/teacher_library_stage6.js';live.write_bytes(live.read_bytes()+b'\n// retained server customization\n')
 before={p:p.read_bytes() for p in (root/'web').iterdir() if p.is_file()}
 out=io.StringIO()
 with contextlib.redirect_stdout(out):ui.install(root,payload,backups,base)
 assert b'retained server customization' in live.read_bytes()
 assert 'data-adelia-studio4' in (root/'web/teacher.html').read_text()
 first={p:p.read_bytes() for p in ui.build_updates(root,payload,base)}
 assert all(p.read_bytes()==d for p,d in first.items()),'repeat install changes content'
 backup=next(backups.iterdir());subprocess.run(['python3',str(backup/'rollback.py')],check=True)
 assert all(p.read_bytes()==data for p,data in before.items())
 assert not (root/'web/teacher_studio.js').exists()
 # Real overlapping edit must fail preflight with the original site intact.
 live.write_bytes(b'// an incompatible replacement\n')
 state={p:p.read_bytes() for p in (root/'web').iterdir() if p.is_file()}
 try:ui.build_updates(root,payload,base)
 except RuntimeError:pass
 else:raise AssertionError('Conflicting server edit was overwritten')
 assert all(p.read_bytes()==data for p,data in state.items())
print('STUDIO_DEPLOY_PREFLIGHT_MERGE_REPEAT_ROLLBACK=OK')
