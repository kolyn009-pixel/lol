"""Copy only existing bot AI credentials to an isolated language configuration.

No provider request, process restart, global AI config or environment mutation.
Never prints key, base URL, environment or exception details.
"""
import argparse,json,os,subprocess,tempfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from web_backend.self_study_ai import validate

TARGET=Path('/etc/adelia-family-languages/ai.json')


def process(service):
 pid=subprocess.check_output(['systemctl','show',service,'--property=MainPID','--value'],text=True).strip()
 if not pid.isdigit() or int(pid)<1:raise RuntimeError('Служба не запущена: '+service)
 root=Path('/proc')/pid
 return root


def configure(bot_process,web_process,target=TARGET,apply=False):
 env={}
 for item in (bot_process/'environ').read_bytes().split(b'\0'):
  key,sep,value=item.partition(b'=')
  if sep and key in (b'OPENROUTER_API_KEY',b'OPENROUTER_BASE_URL',b'AI_MODEL'):env[key.decode()]=value.decode()
 provider=validate({'api_key':env.get('OPENROUTER_API_KEY',''),'base_url':env.get('OPENROUTER_BASE_URL','https://openrouter.ai/api/v1'),'model':env.get('AI_MODEL','openrouter/free') or 'openrouter/free'})
 info={line.split(':',1)[0]:line.split(':',1)[1].split() for line in (web_process/'status').read_text().splitlines() if ':' in line}
 uid=int(info['Uid'][1]);gid=int(info['Gid'][1])
 if target.is_symlink() or target.parent.is_symlink():raise RuntimeError('Отказ: путь настройки является ссылкой.')
 if target.exists():
  if validate(json.loads(target.read_text()))!=provider:raise RuntimeError('Отдельная настройка уже существует и отличается. Она не перезаписана.')
  return {'status':'already_configured','language_only':True}
 if not apply:return {'status':'check','language_only':True,'source_key_present':True,'web_uid':uid,'web_gid':gid}
 target.parent.mkdir(mode=0o700 if uid==0 else 0o750,parents=True,exist_ok=True)
 os.chown(target.parent,0,gid);os.chmod(target.parent,0o700 if uid==0 else 0o750)
 fd,name=tempfile.mkstemp(prefix='.language-ai-',dir=target.parent)
 try:
  os.fchmod(fd,0o600 if uid==0 else 0o640);os.fchown(fd,0,gid)
  with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(provider,stream);stream.flush();os.fsync(stream.fileno())
  os.replace(name,target)
 finally:
  if os.path.exists(name):os.unlink(name)
 return {'status':'configured','language_only':True,'key_printed':False,'restart_required':'tutorbot-web.service'}


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');args=p.parse_args()
 try:result=configure(process('tutorbot.service'),process('tutorbot-web.service'),apply=args.apply)
 except Exception as exc:
  print(json.dumps({'status':'not_configured','error_type':type(exc).__name__,'note':'Настройка не завершена. Ключи и подробности исключения не выводятся.'},ensure_ascii=False));raise SystemExit(1)
 print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
