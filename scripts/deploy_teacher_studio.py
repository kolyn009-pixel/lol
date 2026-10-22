#!/usr/bin/env python3
"""Preflight and install Studio static assets, preserving non-conflicting live edits."""
import argparse, importlib.util, re, subprocess, tempfile
from pathlib import Path
BASE='8977ae3da7bcb226de4e9c782c9f06f42e62d54e'
CHANGED=['teacher_library_stage6.js','formula_explorer.js','learning_hub.js','teacher_request_center.js','teacher_finance_receipts.js','teacher_trial_board.js']
NEW=['teacher_studio.css','teacher_studio.js']
CHANGED.append('learning_hub.css')
spec=importlib.util.spec_from_file_location('workspace_ui',Path(__file__).with_name('deploy_desktop_workspace_v3.py'))
workspace=importlib.util.module_from_spec(spec);spec.loader.exec_module(workspace)

def merge(live,old,new,name):
    if live==old or live==new:return new
    with tempfile.TemporaryDirectory(prefix='adelia-studio-merge-') as tmp:
        paths=[Path(tmp)/n for n in ['live','base','updated']]
        for p,data in zip(paths,[live,old,new]):p.write_bytes(data)
        result=subprocess.run(['git','merge-file','--stdout',*map(str,paths)],capture_output=True)
        if result.returncode:raise RuntimeError('Live edits conflict in '+name+'; no files changed. Resolve the file before updating.')
        return result.stdout

def build_updates(root,payload,base=None):
    if base is None:base=lambda p:subprocess.check_output(['git','-C','/opt/tutorbot','show',BASE+':'+p])
    updates=workspace.build_updates(root,payload)
    for name in CHANGED:
        rel='web/'+name;updates[root/rel]=merge((root/rel).read_bytes(),base(rel),payload(rel),name)
    for name in NEW:
        rel='web/'+name;path=root/rel;data=payload(rel)
        if path.exists() and path.read_bytes()!=data:
            # Never silently replace a separately customized Studio asset.
            raise RuntimeError('Existing custom Studio asset: '+name+'; no files changed.')
        updates[path]=data
    path=root/'web/teacher.html';html=updates[path].decode()
    if 'data-adelia-studio4' not in html:
        html=html.replace('</head>','<link data-adelia-studio4 rel="stylesheet" href="/app/teacher_studio.css?v=20261022-studio4"><script defer src="/app/teacher_studio.js?v=20261022-studio4"></script></head>',1)
    updates[path]=html.encode()
    for document in ['teacher.html','index.html','parent/index.html']:
        path=root/'web'/document
        if not path.exists():continue
        html=updates.get(path,path.read_bytes()).decode()
        for name in CHANGED+['desktop_teacher_app.css']:
            html=re.sub(r'('+re.escape(name)+r')(?:\?[^\s"\'<>]*)?',r'\1?v=20261022-studio4',html)
        updates[path]=html.encode()
    return updates

def install(root,payload,backups,base=None):
    updates=build_updates(root,payload,base)
    workspace.install(root,payload,backups,prepared=updates)
    print('ADELIA_STUDIO4_STATIC_OK')

if __name__=='__main__':
    import os
    parser=argparse.ArgumentParser();parser.add_argument('commit');args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run on the server as root')
    root=Path('/opt/adelia-current').resolve(strict=True)
    payload=lambda p:subprocess.check_output(['git','-C','/opt/tutorbot','show',args.commit+':'+p])
    install(root,payload,'/opt/tutorbot/backups')
