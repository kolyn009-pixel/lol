"""Guarded additive hooks for existing Telegram and VK bot processes."""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from datetime import datetime,timezone

FILES=['handlers/olympiads.py','vk_adapter/olympiads.py','web_backend/olympiad_bot.py']
TAG='# ADELIA OLYMPIAD BOT 20261029'

def insert_function(text,name,code):
    tree=ast.parse(text);fn=next((x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name),None)
    if not fn or fn.lineno==fn.end_lineno:raise RuntimeError('Function needs review: '+name)
    lines=text.splitlines(True);at=fn.body[0].lineno-1
    # Keep a function docstring, if present, as the first statement.
    if isinstance(fn.body[0],ast.Expr) and isinstance(fn.body[0].value,ast.Constant) and isinstance(fn.body[0].value.value,str):at=fn.body[0].end_lineno
    lines.insert(at,code);return ''.join(lines)

def hook_bot(text):
    marker=TAG+' TG'
    if marker in text:return text
    tree=ast.parse(text);fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='student_menu')
    lines=text.splitlines(True);segment=''.join(lines[fn.lineno-1:fn.end_lineno])
    if segment.count('rows = []')!=1:raise RuntimeError('Student menu needs review')
    segment=segment.replace('rows = []','rows = [[InlineKeyboardButton("🏆 Олимпиады",callback_data="olympiads")]]',1)
    text=''.join(lines[:fn.lineno-1])+segment+''.join(lines[fn.end_lineno:])
    return insert_main_registration(text,marker)

def insert_main_registration(text,marker):
    # Register only after app construction, before all broad legacy handlers.
    anchor='    app.add_handler(MessageHandler(filters.ALL, core_test_lab.route_update), group=-200)'
    if text.count(anchor)!=1:raise RuntimeError('Telegram app registration needs review')
    return text.replace(anchor,'    '+marker+'\n    from handlers import olympiads as olympiad_bot\n    olympiad_bot.register(app)\n'+anchor,1)

def hook_vk(text):
    if TAG+' VK' in text:return text
    text=insert_function(text,'handle_message','    '+TAG+' VK\n    from . import olympiads\n    if olympiads.intercept(app,message):return\n')
    return insert_function(text,'run_forever','    from . import olympiads\n    olympiads.install(app)\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default='/opt/adelia-current');p.add_argument('--apply',action='store_true');a=p.parse_args()
    source=Path(__file__).resolve().parents[1];root=Path(a.root).resolve();changes={};original={}
    import fcntl
    lock=open('/run/adelia-olympiad-bots.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    record=root/'olympiad_bots_install.json';prior=json.loads(record.read_text()) if record.exists() else {}
    for name in FILES:
        value=(source/name).read_bytes();live=(root/name).read_bytes() if (root/name).exists() else None
        if live is not None and live!=value and prior.get(name)!=hashlib.sha256(live).hexdigest():raise RuntimeError('Local module needs review: '+name)
        changes[name]=value;original[name]=live
    for name,hook in [('bot.py',hook_bot),('vk_adapter/runtime.py',hook_vk)]:
        original[name]=(root/name).read_bytes();changes[name]=hook(original[name].decode()).encode()
    original[record.name]=record.read_bytes() if record.exists() else None
    changes[record.name]=json.dumps({n:hashlib.sha256(changes[n]).hexdigest() for n in FILES}).encode()
    for name,value in changes.items():
        if name.endswith('.py'):ast.parse(value)
    changed=[n for n in changes if changes[n]!=original[n]]
    print(json.dumps({'mode':'apply' if a.apply else 'check','changed_files':changed}))
    if not a.apply or not changed:return
    if os.geteuid()!=0:raise RuntimeError('Run apply as root')
    if not (root/'web_backend/olympiad_store.py').exists():raise RuntimeError('Install the olympiad website module first')
    for svc in ['tutorbot.service','tutorbot-vk.service']:
        cwd=subprocess.check_output(['systemctl','show',svc,'-p','WorkingDirectory','--value'],text=True).strip()
        if not cwd or Path(cwd).resolve()!=root:raise RuntimeError('Service uses different release: '+svc)
    command=subprocess.check_output(['systemctl','show','tutorbot-vk.service','-p','ExecStart','--value'],text=True)
    if 'vk_adapter.runtime' not in command:raise RuntimeError('VK uses a different entrypoint; needs review')
    backup=Path('/opt/tutorbot/backups')/('olympiad-bots-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));backup.mkdir(parents=True)
    for n in changed:
        if original[n] is not None:
            f=backup/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(original[n])
    try:
        for n in changed:
            f=root/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(changes[n])
        for svc in ['tutorbot.service','tutorbot-vk.service']:
            subprocess.run(['systemctl','restart',svc],check=True,timeout=60)
            subprocess.run(['systemctl','is-active','--quiet',svc],check=True,timeout=10)
    except Exception:
        for n in changed:
            if original[n] is None:(root/n).unlink(missing_ok=True)
            else:(root/n).write_bytes(original[n])
        for svc in ['tutorbot.service','tutorbot-vk.service']:subprocess.run(['systemctl','restart',svc],timeout=60)
        raise
    print('OLYMPIAD_BOTS_INSTALLED\nBackup: '+str(backup))

if __name__=='__main__':main()
