from __future__ import annotations

import json
import os
import random
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import database
from . import schema, service, notification_sync, teacher_service, teacher_notifications

API_VERSION = os.getenv("VK_API_VERSION", "5.199").strip() or "5.199"
GROUP_ID = os.getenv("VK_GROUP_ID", "").strip()
TOKEN = os.getenv("VK_TOKEN", "").strip()
_PENDING = {}


def _http_json(url, data=None, timeout=35):
    body = None
    headers = {"User-Agent": "TutorBot-VK/1.0"}
    if data is not None:
        body = urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = Request(url, data=body, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api(method, **params):
    if not TOKEN:
        raise RuntimeError("VK_TOKEN is not configured")
    payload = dict(params); payload["access_token"] = TOKEN; payload["v"] = API_VERSION
    data = _http_json(f"https://api.vk.com/method/{method}", payload)
    if "error" in data: raise RuntimeError(f"VK API {method}: {data['error']}")
    return data.get("response")


def _button(label, command, color="secondary"):
    return {"action":{"type":"text","label":label,"payload":json.dumps({"command":command},ensure_ascii=False)},"color":color}


def _keyboard_rows(rows):
    return json.dumps({"one_time":False,"inline":False,"buttons":rows},ensure_ascii=False)


def keyboard(linked=False, mode="home", data=None):
    data=data or {}
    if mode == "teacher":
        rows=[
            [_button("📅 Сегодня","t_today","primary"),_button("👥 Ученики","t_students")],
            [_button("💬 Сообщения","t_messages"),_button("📝 Задать ДЗ","t_hw")],
            [_button("🎥 Отправить ссылку","t_link","positive"),_button("🔔 События","t_events")],
            [_button("🏠 Главная","t_home")],
        ]
        return _keyboard_rows(rows)
    if mode == "teacher_lessons":
        rows=[]
        for row in data.get("lessons",[])[:8]:
            rows.append([_button("🎥 "+teacher_service.lesson_text(row),f"t_lesson|{row['id']}","primary")])
        rows.append([_button("🏠 Главная","t_home")])
        return _keyboard_rows(rows)
    if mode == "teacher_students":
        rows=[]
        for row in data.get("students",[])[:20]:
            rows.append([_button(f"👤 {row['name']} · {row['grade']} кл.",f"t_student|{row['id']}")])
        rows.append([_button("🏠 Главная","t_home")])
        return _keyboard_rows(rows)
    if mode == "teacher_student":
        uid=int(data["user_id"])
        return _keyboard_rows([
            [_button("📝 Задать ДЗ",f"t_hw_user|{uid}","primary"),_button("💬 Написать",f"t_msg_user|{uid}")],
            [_button("📅 Занятия",f"t_user_lessons|{uid}")],[_button("👥 Ученики","t_students"),_button("🏠 Главная","t_home")],
        ])
    if mode == "teacher_lesson":
        lid=int(data["lesson_id"]); uid=int(data["user_id"])
        return _keyboard_rows([
            [_button("🎥 Отправить ссылку",f"t_sendlink|{lid}","positive")],
            [_button("📝 Задать ДЗ",f"t_hw_user|{uid}")],[_button("📅 Сегодня","t_today"),_button("🏠 Главная","t_home")],
        ])
    if mode == "formula_grades":
        grades=data.get("grades",[]); rows=[]
        for i in range(0,len(grades),2): rows.append([_button(f"🎓 {g} класс",f"fg|{g}","primary" if i==0 else "secondary") for g in grades[i:i+2]])
        rows.append([_button("🏠 Главная","home")]); return _keyboard_rows(rows)
    if mode == "formula_subjects":
        grade=data["grade"]; rows=[[_button(f"📖 {s}",f"fs|{grade}|{s}","primary")] for s in data.get("subjects",[])]
        rows += [[_button("⬅️ К классам","formulas"),_button("🏠 Главная","home")]]; return _keyboard_rows(rows)
    if mode == "formula_topics":
        grade=data["grade"]; subject=data["subject"]; rows=[[_button(title[:38],f"ft|{grade}|{subject}|{key}")] for key,title in data.get("topics",[])[:30]]
        rows += [[_button("⬅️ К предметам",f"fg|{grade}"),_button("🏠 Главная","home")]]; return _keyboard_rows(rows)
    if not linked: rows=[[_button("🔗 Связать с Telegram","link_help","primary")],[_button("ℹ️ Как это работает","help")]]
    elif mode=="cancel": rows=[[_button("❌ Отмена","cancel")],[_button("🏠 Главная","home")]]
    elif mode=="more": rows=[[_button("💳 Профиль и оплата","profile","primary")],[_button("💬 История сообщений","chat_history")],[_button("🔗 Связь с Telegram","linked")],[_button("🏠 Главная","home")]]
    else: rows=[[_button("📅 Мои занятия","lessons","primary"),_button("📝 Домашнее задание","homework")],[_button("📚 Моя учёба","study"),_button("🧮 Формулы","formulas")],[_button("💬 Преподаватель","teacher"),_button("🖥 Доска","board")],[_button("➕ Записаться","booking","positive"),_button("••• Ещё","more")]]
    return _keyboard_rows(rows)


def send(peer_id,text,linked=False,mode="home",data=None):
    return api("messages.send",peer_id=int(peer_id),random_id=random.randint(1,2_000_000_000),message=str(text),keyboard=keyboard(linked,mode,data))


def _extract_command(message):
    payload=message.get("payload")
    if payload:
        try:return str((json.loads(payload) if isinstance(payload,str) else payload).get("command") or "").strip()
        except Exception:pass
    text=str(message.get("text") or "").strip().lower()
    mapping={"📅 мои занятия":"lessons","📝 домашнее задание":"homework","📚 моя учёба":"study","🧮 формулы":"formulas","💬 преподаватель":"teacher","🖥 доска":"board","➕ записаться":"booking","••• ещё":"more","💳 профиль и оплата":"profile","💬 история сообщений":"chat_history","🏠 главное меню":"home","🏠 главная":"home","❌ отмена":"cancel","🔗 связь с telegram":"linked","🔗 связать с telegram":"link_help","ℹ️ как это работает":"help","привет":"home","начать":"home","start":"home","/start":"home","📅 сегодня":"t_today","👥 ученики":"t_students","💬 сообщения":"t_messages","📝 задать дз":"t_hw","🎥 отправить ссылку":"t_link","🔔 события":"t_events"}
    return mapping.get(text,"")


def _profile(vk_id):
    try:
        rows=api("users.get",user_ids=int(vk_id),fields="screen_name") or []
        if rows:
            r=rows[0]; return {"display_name":f"{r.get('first_name','')} {r.get('last_name','')}".strip(),"username":r.get("screen_name")}
    except Exception:pass
    return {"display_name":None,"username":None}


def _student_home(peer,user): send(peer,f"💜 АДЕЛИЯ • ГЛАВНАЯ\n\n{user['name']}, я рядом и собрала главное в одном месте.\n\n📅 Занятия, ДЗ, учёба и связь с преподавателем доступны ниже.",True)

def _teacher_home(peer): send(peer,teacher_service.home_text(),True,"teacher")


def _handle_teacher(peer,vk_id,command,raw):
    pending=_PENDING.get(vk_id)
    if pending and not command:
        _PENDING.pop(vk_id,None); kind=pending[0]
        if kind=="t_link":
            delivered,error=teacher_service.send_lesson_link(int(pending[1]),raw)
            if error: send(peer,"❌ "+error,True,"teacher")
            else: send(peer,f"✅ Ссылка отправлена.\nTelegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}",True,"teacher")
            return
        if kind=="t_hw":
            hid,delivered=teacher_service.create_homework(int(pending[1]),raw)
            send(peer,f"✅ ДЗ #{hid} создано.\nTelegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}",True,"teacher"); return
        if kind=="t_msg":
            uid=int(pending[1]); from crm_plus import service as crm
            delivered=__import__('vk_adapter.channel_delivery',fromlist=['send_student']).send_student(uid,f"👨‍🏫 Сообщение от преподавателя\n\n{raw}")
            crm.log_message(uid,'OUT',raw,int(teacher_service.is_teacher(vk_id)),'STUDENT','SENT' if any(delivered.values()) else 'FAILED')
            send(peer,f"✅ Отправлено. Telegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}",True,"teacher"); return
    if command in ("t_home","home",""): _teacher_home(peer); return
    if command in ("t_today","t_link"):
        rows=teacher_service.today_lessons(); send(peer,"📅 СЕГОДНЯ\n\nВыбери занятие:" if rows else "📅 Сегодня занятий нет.",True,"teacher_lessons",{"lessons":rows}); return
    if command in ("t_students","t_hw"):
        rows=teacher_service.active_students(); send(peer,"👥 УЧЕНИКИ\n\nВыбери ученика:",True,"teacher_students",{"students":rows}); return
    if command.startswith("t_student|"):
        uid=int(command.split("|",1)[1]); u=database.get_user(uid); send(peer,f"👤 {u['name']} · {u['grade']} класс",True,"teacher_student",{"user_id":uid}); return
    if command.startswith("t_lesson|"):
        lid=int(command.split("|",1)[1]); l=database.get_lesson(lid); u=database.get_user(int(l['user_id'])); send(peer,f"🎓 ЗАНЯТИЕ\n\n👤 {u['name']}\n🕐 {str(l['start_time'])[11:16]}",True,"teacher_lesson",{"lesson_id":lid,"user_id":int(u['id'])}); return
    if command.startswith("t_sendlink|"):
        lid=int(command.split("|",1)[1]); _PENDING[vk_id]=("t_link",lid); send(peer,"🎥 Пришли следующим сообщением ссылку на Телемост.\nОна уйдёт ученику в Telegram и VK.",True,"teacher"); return
    if command.startswith("t_hw_user|"):
        uid=int(command.split("|",1)[1]); _PENDING[vk_id]=("t_hw",uid); send(peer,"📝 Пришли следующим сообщением текст домашнего задания.\nОно сохранится в общей базе и придёт ученику в Telegram и VK.",True,"teacher"); return
    if command.startswith("t_msg_user|"):
        uid=int(command.split("|",1)[1]); _PENDING[vk_id]=("t_msg",uid); send(peer,"💬 Пришли следующим сообщением текст ученику.",True,"teacher"); return
    if command in ("t_messages","t_events"): send(peer,"🔔 Уведомления преподавателя активны. Новые сообщения учеников и напоминания перед занятиями будут приходить сюда автоматически.",True,"teacher"); return
    _teacher_home(peer)


def handle_message(message):
    vk_id=int(message.get("from_id") or 0); peer=int(message.get("peer_id") or vk_id)
    if vk_id<=0:return
    command=_extract_command(message); raw=str(message.get("text") or "").strip(); profile=None
    if raw.upper().replace(" ","").startswith("ADELIA-ADMIN-"):
        profile=_profile(vk_id); aid,error=schema.consume_admin_link_code(raw,"VK",str(vk_id),profile.get("username"),profile.get("display_name"))
        if error: send(peer,"❌ "+error,False); return
        send(peer,"✅ VK преподавателя подключён к TutorBot.\n\nТеперь рабочие уведомления и действия доступны здесь.",True,"teacher"); return
    if teacher_service.is_teacher(vk_id): _handle_teacher(peer,vk_id,command,raw); return
    user=service.linked_user(vk_id)
    if raw.upper().replace(" ","").startswith("ADELIA-"):
        profile=_profile(vk_id); uid,error=schema.consume_link_code(raw,"VK",str(vk_id),profile.get("username"),profile.get("display_name"))
        if error:send(peer,"❌ "+error,False);return
        u=database.get_user(int(uid));send(peer,f"✅ VK подключён к TutorBot.\n\nТеперь это одна карточка ученика: {u['name']}.",True);return
    if not user:
        send(peer,"💜 АДЕЛИЯ\n\nДля ученика: получи код кнопкой «🔗 Привязать VK» в Telegram.\nДля преподавателя: используй /vkadminlink в Telegram.",False);return
    pending=_PENDING.get(vk_id)
    if pending and not command:
        _PENDING.pop(vk_id,None)
        if pending=="teacher_message": _,reply=service.submit_teacher_message(int(user['id']),raw,vk_id);send(peer,reply,True);return
        if pending=="booking": _,reply=service.submit_booking_request(int(user['id']),raw);send(peer,reply,True);return
    if command=="cancel":_PENDING.pop(vk_id,None);send(peer,"Хорошо, действие отменено 💜",True);return
    if command in ("home",""):_student_home(peer,user);return
    uid=int(user['id'])
    if command=="lessons":send(peer,service.upcoming_text(uid),True);return
    if command=="homework":send(peer,service.homework_text(uid),True);return
    if command=="study":send(peer,service.study_text(uid),True);return
    if command=="formulas":send(peer,service.formulas_text(uid),True,"formula_grades",{"grades":service.formula_grades(uid)});return
    if command.startswith("fg|"):
        grade=int(command.split("|")[1]);send(peer,f"🧮 {grade} КЛАСС\n\nВыбери предмет:",True,"formula_subjects",{"grade":grade,"subjects":service.formula_subjects(grade)});return
    if command.startswith("fs|"):
        _,g,s=command.split("|",2);send(peer,f"🧮 {g} КЛАСС · {s}\n\nВыбери тему:",True,"formula_topics",{"grade":int(g),"subject":s,"topics":service.formula_topics(int(g),s)});return
    if command.startswith("ft|"):
        _,g,s,t=command.split("|",3);text=service.formula_topic(int(g),s,t) or "Тема не найдена.";send(peer,text,True,"formula_topics",{"grade":int(g),"subject":s,"topics":service.formula_topics(int(g),s)});return
    if command=="board":send(peer,service.board_text(uid),True);return
    if command=="teacher":_PENDING[vk_id]="teacher_message";send(peer,service.message_history_text(uid)+"\n\n✍️ Напиши следующим сообщением текст преподавателю.",True,"cancel");return
    if command=="chat_history":send(peer,service.message_history_text(uid),True,"more");return
    if command=="booking":_PENDING[vk_id]="booking";send(peer,"➕ Напиши желаемый день, время и предмет одним сообщением.",True,"cancel");return
    if command in ("more","profile"):send(peer,service.more_text(uid),True,"more");return
    if command=="linked":send(peer,f"✅ VK связан с карточкой «{user['name']}».",True,"more");return
    _student_home(peer,user)


def long_poll_server():
    d=api("groups.getLongPollServer",group_id=GROUP_ID);return d["server"],d["key"],d["ts"]


def run_forever():
    if not GROUP_ID or not TOKEN:raise SystemExit("VK_GROUP_ID/VK_TOKEN are not configured")
    schema.initialize();notification_sync.initialize();teacher_notifications.initialize();server,key,ts=long_poll_server();print(f"VK LONG POLL START group={GROUP_ID} api={API_VERSION}");last=0.0
    while True:
        try:
            d=_http_json(f"{server}?"+urlencode({"act":"a_check","key":key,"ts":ts,"wait":25}),timeout=35)
            if d.get("failed"):server,key,ts=long_poll_server();continue
            ts=d.get("ts",ts)
            for upd in d.get("updates",[]):
                if upd.get("type")=="message_new":
                    obj=upd.get("object") or {};msg=obj.get("message") if isinstance(obj,dict) else None
                    if msg:handle_message(msg)
            now=time.monotonic()
            if now-last>=30:
                try:
                    notification_sync.tick(send)
                    teacher_notifications.tick(lambda p,t:send(p,t,True,"teacher"))
                except Exception as exc:print("VK NOTIFICATION ERROR:",repr(exc))
                last=now
        except KeyboardInterrupt:raise
        except Exception as exc:
            print("VK LONG POLL ERROR:",repr(exc));time.sleep(3)
            try:server,key,ts=long_poll_server()
            except Exception:time.sleep(5)

if __name__=="__main__":run_forever()
