"""Opt-in bot-only installer. Dry run by default; never changes ordinary commands."""
import argparse,ast,json,os,re,tempfile
from pathlib import Path
from install_self_study import atomic,digest,restart,restore

SOURCE=Path(__file__).resolve().parents[1]
FILES=('web_backend/self_study_bot.py','handlers/self_study_family.py')
ANCHOR='    for handler in learning_handlers.handlers():\n        app.add_handler(handler)'
HOOK='    from handlers.self_study_family import install as install_family_languages\n    install_family_languages(app)'
MARKER='self_study_bot_install.json'
VK_HOOK='    from .self_study_family import intercept as family_language_command\n    if family_language_command(app, message):return'

def patch_vk(text):
 if VK_HOOK in text:
  if text.count(VK_HOOK)!=1:raise RuntimeError('Duplicate VK family hook')
  return text
 anchor='def handle_message(message):\n'
 if text.count(anchor)!=1:raise RuntimeError('Unknown VK runtime registration structure')
 text=text.replace(anchor,anchor+VK_HOOK+'\n',1);ast.parse(text);return text



def patch_bot(text):
 if HOOK in text:
  if text.count(HOOK)!=1:raise RuntimeError('Duplicate family hook')
  return text
 if text.count(ANCHOR)!=1:raise RuntimeError('Unknown bot registration structure: review required')
 text=text.replace(ANCHOR,ANCHOR+'\n\n'+HOOK,1);ast.parse(text);return text


def install(root,service,apply=False,channel='telegram'):
 if channel not in ('telegram','vk'):raise RuntimeError('Invalid channel')
 files=FILES if channel=='telegram' else ('web_backend/self_study_bot.py','vk_adapter/self_study_family.py')
 marker=MARKER if channel=='telegram' else 'self_study_vk_install.json'
 entry_path='bot.py' if channel=='telegram' else 'vk_adapter/runtime.py'
 root=root.resolve()
 if root==SOURCE:raise RuntimeError('Target must be a different live checkout')
 if not re.fullmatch(r'[a-zA-Z0-9_.@-]+',service):raise RuntimeError('Invalid service')
 if not (root/'web_backend/self_study_access.py').is_file():raise RuntimeError('Install the web language section first')
 previous=json.loads((root/marker).read_text()) if (root/marker).exists() else {}
 candidate={name:(SOURCE/name).read_bytes() for name in files}
 for name in files:
  p=root/name
  if p.exists() and p.read_bytes()!=candidate[name] and digest(p.read_bytes())!=previous.get('hashes',{}).get(name):raise RuntimeError('Local module conflict: '+name)
 candidate[entry_path]=(patch_bot if channel=='telegram' else patch_vk)((root/entry_path).read_text()).encode()
 candidate[marker]=json.dumps({'hashes':{k:digest(v) for k,v in candidate.items()}},indent=2).encode()
 for name,data in candidate.items():
  if not (root/name).resolve().is_relative_to(root):raise RuntimeError('Target escapes live checkout')
  if name.endswith('.py'):ast.parse(data)
 original={n:(root/n).read_bytes() if (root/n).exists() else None for n in candidate}
 changed={n:v for n,v in candidate.items() if original[n]!=v}
 print(json.dumps({'mode':'apply' if apply else 'check','changed_files':list(changed)}))
 if not apply or not changed:return None
 backup=Path(tempfile.mkdtemp(prefix='family-bot-',dir=root.parent));os.chmod(backup,0o700);before={}
 for name in changed:
  before[name]=None
  if original[name] is not None:
   path=backup/'files'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(original[name]);before[name]={'mode':(root/name).stat().st_mode&0o777}
 (backup/'manifest.json').write_text(json.dumps({'root':str(root),'before':before,'installed':{n:digest(v) for n,v in changed.items()}},indent=2))
 written=[]
 try:
  for name,data in changed.items():
   if ((root/name).read_bytes() if (root/name).exists() else None)!=original[name]:raise RuntimeError('Concurrent change: '+name)
   atomic(root/name,data,before[name]['mode'] if before[name] else 0o644);written.append(name)
  restart(service)
 except BaseException:
  for name in reversed(written):
   if original[name] is None:(root/name).unlink(missing_ok=True)
   else:atomic(root/name,original[name],before[name]['mode'])
  restart(service);raise
 print('Installed. Code-only rollback backup:',backup);return backup


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--channel',choices=('telegram','vk'),default='telegram');p.add_argument('--root',type=Path,required=True);p.add_argument('--service',required=True);p.add_argument('--apply',action='store_true');p.add_argument('--rollback',type=Path);a=p.parse_args()
 if not re.fullmatch(r'[a-zA-Z0-9_.@-]+',a.service):p.error('Invalid service')
 if a.apply:
  import fcntl
  lock=open(a.root.resolve().parent/'self-study-update.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if a.rollback:
  if not a.apply:p.error('Rollback requires --apply')
  restore(a.root.resolve(),a.rollback.resolve());restart(a.service)
 else:install(a.root,a.service,a.apply,a.channel)

if __name__=='__main__':main()
