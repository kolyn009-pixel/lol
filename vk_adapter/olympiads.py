"""Olympiad VK menu and explicit command interception."""
import json
from web_backend.olympiad_bot import summary,cabinet


def install(app):
    if getattr(app,'_olympiads_installed',False):return
    original=app.keyboard
    def wrapped(linked=False,mode='home',data=None):
        if mode=='olympiads':
            role=(data or {}).get('role','student')
            return app._keyboard_rows([[app._button('⚛️ Физика','olympiads:PHYSICS'),app._button('🧪 Химия','olympiads:CHEMISTRY')],
                [app._link_button('🗓 Календарь и подготовка',cabinet(role))],
                [app._button('🏠 Главная','t_home' if role=='teacher' else 'home')]])
        result=original(linked,mode,data)
        if mode=='teacher' or linked and mode=='home':
            payload=json.loads(result);payload['buttons'].insert(0,[app._button('🏆 Олимпиады','olympiads')]);return json.dumps(payload,ensure_ascii=False)
        return result
    app.keyboard=wrapped;app._olympiads_installed=True


def intercept(app,message):
    command=app._extract_command(message) or '';raw=str(message.get('text') or '').strip().casefold()
    if command not in {'olympiads','olympiads:PHYSICS','olympiads:CHEMISTRY'} and raw not in {'/olympiads','олимпиады','🏆 олимпиады'}:return False
    ext=int(message.get('from_id') or 0);peer=int(message.get('peer_id') or ext)
    if ext<=0 or peer!=ext:return True
    teacher=app.teacher_service.is_teacher(ext);user=None if teacher else app.service.linked_user(ext)
    if not teacher and (not user or not user['active']):app.send(peer,'Сначала подключите свой аккаунт Аделии.',False);return True
    role='teacher' if teacher else 'student';uid=ext if teacher else int(user['id'])
    subject=command.split(':',1)[1] if ':' in command else ''
    if subject not in {'PHYSICS','CHEMISTRY'}:subject=''
    try:text=summary(role,uid,subject)
    except Exception:text='🏆 Расписание временно недоступно. Откройте календарь в кабинете.'
    app.send(peer,text,True,'olympiads',{'role':role});return True
