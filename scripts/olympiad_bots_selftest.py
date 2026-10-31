import importlib.util,json,sys,types
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
sys.modules['database']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('installer',root/'scripts/install_olympiad_bots.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
bot='''def student_menu(user_id=None):
    rows = []
    return rows

def main():
    app = build()
    app.add_handler(MessageHandler(filters.ALL, core_test_lab.route_update), group=-200)
'''
a=m.hook_bot(bot);assert m.hook_bot(a)==a;assert 'callback_data="olympiads"' in a;assert a.count('olympiad_bot.register(app)')==1
vk='''def handle_message(message):
    return old(message)

def run_forever():
    return app.run_forever()
'''
a=m.hook_vk(vk);assert m.hook_vk(a)==a;assert 'olympiads.intercept(app,message)' in a
from vk_adapter import olympiads as v
sent=[]
app=types.SimpleNamespace(_extract_command=lambda x:x.get('command',''),teacher_service=types.SimpleNamespace(is_teacher=lambda x:False),service=types.SimpleNamespace(linked_user=lambda x:{'id':7,'active':1}),send=lambda *args:sent.append(args),keyboard=lambda *args:json.dumps({'buttons':[]}),_button=lambda title,cmd:{'action':{'label':title,'payload':cmd}},_link_button=lambda title,url:{'action':{'label':title,'link':url}},_keyboard_rows=lambda rows:json.dumps({'buttons':rows}))
v.summary=lambda role,uid,subject:f'{role}:{uid}:{subject}'
assert not v.intercept(app,{'from_id':1,'text':'другая команда'})
assert v.intercept(app,{'from_id':1,'peer_id':20000001,'command':'olympiads'});assert not sent
assert v.intercept(app,{'from_id':1,'peer_id':1,'command':'olympiads:PHYSICS'});assert sent[-1][1]=='student:7:PHYSICS'
v.install(app);v.install(app);assert len(json.loads(app.keyboard(True))['buttons'])==1
assert 'olympiads=1' in app.keyboard(True,'olympiads',{'role':'student'})
print('Bot hook idempotency, personal VK routing, linked user identity and menu buttons: OK')
