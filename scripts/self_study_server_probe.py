"""Read-only service metadata. Prints no environment, tokens, credentials or DB rows."""
import json,os,re,subprocess
from pathlib import Path


def command(args):
 r=subprocess.run(args,capture_output=True,text=True,timeout=10)
 if r.returncode:raise RuntimeError('Read-only systemctl command failed')
 return r.stdout


def inspect_service(name):
 text=command(['systemctl','show',name,'--property=WorkingDirectory,MainPID,FragmentPath'])
 fields=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
 pid=int(fields.get('MainPID') or 0);root=fields.get('WorkingDirectory') or None
 if pid:
  try:root=str(Path('/proc',str(pid),'cwd').resolve(strict=True))
  except OSError:pass
 return {'service':name,'pid':pid,'working_directory':root,'unit_file':fields.get('FragmentPath') or None,
         'has_language_installer':bool(root and Path(root,'scripts/install_self_study.py').is_file())}


def main():
 listing=command(['systemctl','list-units','--all','--type=service','--no-legend','--plain'])
 names=[line.split()[0] for line in listing.splitlines() if line.split() and re.fullmatch(r'[A-Za-z0-9_.@-]+\.service',line.split()[0]) and re.search(r'tutor|adelia',line.split()[0],re.I)]
 print(json.dumps({'services':[inspect_service(n) for n in names],
 'next':'Confirm the live web service, bot services, real SQLite file and loopback API port before installation. This probe does not guess them or modify files.'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
