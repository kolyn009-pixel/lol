"""One guarded deployment for the saved October 25 teacher-workspace changes."""
import argparse
import ast
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

REPO = '/opt/tutorbot'
BASES = ['f70d2e27a5e9fc5a592ab4eceb0824a73c691331','e4a1d07993253aaa7ae0a05b6009b2adf20c7867',
         '8882d5e796abb715a7916c4c7689817766bfc715',
         '4c6e2f54929cc353d97e5716128ae61df44a5733',
         '69bbcc352343aa515a5c50dbfe8514e3935ce864',
         '9ffbdb934d51ecdc512691ad2ca4570f43ed73b3',
         '048034e3eec757bdffcc360433ec7de81b63ac3c',
         '9131881751444403d038a7e862b4b65ffa06d18f',
         'decd952e8ecf075a411c814f13d545fa7d4a969f',
         '5212965568d16c23503810a8ae1b0d7ddb894148',
         '9ac1c56bf383bf1ffc5a4c84d6850453dbd547eb',
         'ad7c84152d597cdd630390f7fa4097ccb1545474',
         'e18d5d566d26bf720368f49089e0b847362ec77f']
LEGACY = ['web/teacher_dashboard_week.css','web/teacher_clean_runtime.js',
          'web/teacher_receipt_review_tools.css','web/teacher_health.js',
          'web/learning_hub.js','web/formula_explorer.js','web/teacher_finance.js']
FAMILIES = ['teacher_workspace_review','teacher_messenger_rows','education_formula_layout',
            'weekly_invoices_chat','chat_composer','package_studio','teaching_workbench','visual_channels']
CUSTOM = [f'web/{n}.css' for n in FAMILIES] + [f'web/{n}.js' for n in
    ['teacher_workspace_review','teacher_messenger_rows','homework_formulas',
     'weekly_invoices_chat','chat_composer','package_studio','teaching_plan','teaching_workbench','visual_channels']]
CUSTOM += ['web_backend/calendar_week_invoices.py','web_backend/first_lesson_context.py','web_backend/lesson_delivery_status.py','web/pwa_workspace.js']
BACKENDS = {'web_backend/teacher_invoices.py':('deploy_calendar_week_chat_20261025.py','hook_week'),
            'web_backend/lesson_link_delivery.py':('deploy_chat_delivery_20261025.py','hook_delivery'),
            'web_backend/learning_hub.py':('deploy_teaching_workbench_20261025.py','hook_plan')}
HTML = ['web/teacher.html','web/index.html']


def git(ref, path, optional=False):
    r = subprocess.run(['git','-C',REPO,'show',ref+':'+path],capture_output=True)
    if r.returncode:
        if optional:
            return None
        raise RuntimeError('Required source unavailable: '+path)
    return r.stdout


def module(ref, name):
    scope = {'__name__':'saved_installer'}
    code = git(ref,'scripts/'+name).decode()
    exec(compile(code,name,'exec'),scope)
    return scope


def html_update(text, path, version):
    scripts = (['formula_explorer','teacher_clean_runtime','teacher_health','learning_hub',
                'teacher_finance','teacher_workspace_review','teacher_messenger_rows',
                'homework_formulas','weekly_invoices_chat','chat_composer','package_studio',
                'teaching_plan','teaching_workbench','visual_channels','pwa_workspace'] if path.endswith('teacher.html') else
               ['formula_explorer','homework_formulas'])
    styles = (['teacher_dashboard_week','teacher_receipt_review_tools']+FAMILIES
              if path.endswith('teacher.html') else ['education_formula_layout'])
    # Keep local HTML edits. Reinsert only our standalone assets in known order.
    standalone = {Path(p).name for p in CUSTOM if p.startswith('web/')}
    for name in standalone:
        text = re.sub(r'<script\b[^>]*\bsrc=["\']/app/'+re.escape(name)+r'(?:\?[^"\']*)?["\'][^>]*>\s*</script>','',text)
        text = re.sub(r'<link\b[^>]*\bhref=["\']/app/'+re.escape(name)+r'(?:\?[^"\']*)?["\'][^>]*>','',text)
    if text.count('</head>') != 1:
        raise RuntimeError('Expected one HTML head: '+path)
    additions = []
    for names, extension in [(scripts,'.js'),(styles,'.css')]:
        for name in names:
            asset=name+extension;url='/app/'+asset+'?v='+version
            pattern=r'(?P<q>["\'])/app/'+re.escape(asset)+r'(?:\?[^"\']*)?(?P=q)'
            text,count=re.subn(pattern,lambda m:m['q']+url+m['q'],text)
            if count>1:
                raise RuntimeError('Duplicate HTML asset: '+asset)
            if not count:
                additions.append('<script defer src="'+url+'"></script>' if extension=='.js'
                                 else '<link rel="stylesheet" href="'+url+'">')
    return text.replace('</head>',''.join(additions)+'</head>',1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0 or not re.fullmatch('[0-9a-f]{40}',args.commit):
        raise SystemExit('Run as root with a full pinned commit')
    with open('/run/adelia-learning-deploy.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        root=Path('/opt/adelia-current').resolve(strict=True)
        if root.parent!=Path('/opt/adelia-releases'):
            raise RuntimeError('Unexpected active release')
        pid=int(subprocess.check_output(['systemctl','show','tutorbot-web','-p','MainPID','--value']))
        if pid<=0 or Path(f'/proc/{pid}/cwd').resolve()!=root:
            raise RuntimeError('Web process does not use the active release')
        shared=module(args.commit,'deploy_calendar_week_chat_20261025.py')
        education=module(args.commit,'deploy_education_formulas_20261025.py')
        atomic,served=shared['atomic'],shared['served']
        helpers={name:module(args.commit,name) for name,_ in BACKENDS.values()}
        files=CUSTOM+LEGACY+list(BACKENDS)+HTML
        originals,stats,updates={},{},{}
        for name in files:
            p=root/name
            if p.is_symlink() or p.resolve()!=p:
                raise RuntimeError('Unexpected symlink: '+name)
            originals[name]=p.read_bytes() if p.is_file() else None
            stats[name]=p.stat() if p.is_file() else None
            live=originals[name]
            target=git(args.commit,name)
            if name in CUSTOM:
                if live is not None and live.rstrip()!=target.rstrip():
                    known=[git(base,name,True) for base in BASES]
                    if not any(old is not None and old.rstrip()==live.rstrip() for old in known):
                        raise RuntimeError('Custom local edits need review: '+name)
                updates[name]=target
            elif live is None:
                raise RuntimeError('Required live file missing: '+name)
            elif name in BACKENDS:
                script,fn=BACKENDS[name]
                updates[name]=helpers[script][fn](live.decode()).encode()
            elif name in HTML:
                updates[name]=html_update(live.decode(),name,args.commit[:12]).encode()
            elif live.rstrip()==target.rstrip():
                updates[name]=live
            else:
                for base in BASES:
                    old=git(base,name,True)
                    if old is None:
                        continue
                    try:
                        delta=education['delta'] if name.endswith('formula_explorer.js') else shared['delta']
                        updates[name]=delta(live.decode(),old.decode(),target.decode(),name).encode()
                        break
                    except RuntimeError:
                        continue
                else:
                    raise RuntimeError('Code differs from reviewed versions; no files changed: '+name)
            if name == 'web_backend/lesson_link_delivery.py':
                marker = '# Previous channel delivery status (no automatic resend)'
                if marker not in updates[name].decode():
                    updates[name] += b'\n\n# Previous channel delivery status (no automatic resend)\n_status_original_individual = send_individual\ndef send_individual(lesson_id):\n    from web_backend.lesson_delivery_status import previous_individual\n    return previous_individual(_status_original_individual(lesson_id), lesson_id)\n'
            if name.endswith('.py'):
                ast.parse(updates[name],filename=name)
            if live is not None and name.startswith('web/') and served(name)!=live:
                raise RuntimeError('Nginx serves a different file: '+name)
        # Required by the connected-channel delivery patch.
        delivery=ast.parse((root/'web_backend/message_delivery.py').read_text())
        if not any(isinstance(n,ast.FunctionDef) and n.name=='_enabled_channels' for n in delivery.body):
            raise RuntimeError('Connected-channel resolver missing')
        print('ALL_PREFLIGHT_OK:',root,flush=True)
        changed=[n for n in files if originals[n]!=updates[n]]
        print('Files to update:',len(changed),flush=True)
        if not changed:
            print('ALREADY_INSTALLED')
            return
        if not args.apply:
            print('No files changed. Use --apply to install.')
            return
        if Path('/opt/adelia-current').resolve()!=root:
            raise RuntimeError('Release changed during preflight')
        for n in files:
            if ((root/n).read_bytes() if (root/n).is_file() else None)!=originals[n]:
                raise RuntimeError('File changed during preflight: '+n)
        backups=Path('/opt/tutorbot/backups');backups.mkdir(exist_ok=True)
        backup=Path(tempfile.mkdtemp(prefix='adelia-all-20261025-',dir=backups));os.chmod(backup,0o700)
        manifest={'release':str(root),'commit':args.commit,'files':{}}
        for n in changed:
            manifest['files'][n]=originals[n] is not None
            if originals[n] is not None:
                saved=backup/n;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,saved)
        (backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
        # A manual rollback restores only code; it never restores or replaces the DB.
        (backup/'rollback.py').write_text('import json,os,shutil,tempfile\nfrom pathlib import Path\nb=Path(__file__).parent;m=json.loads((b/"manifest.json").read_text());r=Path(m["release"])\nfor n,exists in m["files"].items():\n p=r/n\n if exists:\n  fd,t=tempfile.mkstemp(dir=p.parent);os.close(fd);shutil.copy2(b/n,t);s=(b/n).stat();os.chown(t,s.st_uid,s.st_gid);os.replace(t,p)\n else:p.unlink(missing_ok=True)\nimport subprocess\nsubprocess.run(["systemctl","restart","tutorbot-web"],check=True)\n')
        written=[]
        try:
            for n in changed:
                atomic(root/n,updates[n],stats[n]);written.append(n)
            shared['restart_and_check']()
            for n in files:
                if n.startswith('web/') and served(n)!=updates[n]:
                    raise RuntimeError('Updated asset verification failed: '+n)
        except BaseException:
            for n in reversed(written):
                if originals[n] is None:
                    (root/n).unlink(missing_ok=True)
                else:
                    atomic(root/n,originals[n],stats[n])
            subprocess.run(['systemctl','restart','tutorbot-web'],check=False,timeout=60)
            print('UPDATE_FAILED; original files restored. Backup:',backup,flush=True)
            raise
        print('ADELIA_ALL_OK')
        print('Backup:',backup)
        print('Rollback: python3',backup/'rollback.py')
        print('Web service restarted. No database migration; no automatic messages sent.')


if __name__=='__main__':
    main()
