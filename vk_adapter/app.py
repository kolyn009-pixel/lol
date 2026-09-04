from __future__ import annotations
import json,os,random,time
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import database
import college_curriculum
import education_profile
from . import schema,service,notification_sync,teacher_service,teacher_notifications
API_VERSION=os.getenv("VK_API_VERSION","5.199").strip() or "5.199";GROUP_ID=os.getenv("VK_GROUP_ID","").strip();TOKEN=os.getenv("VK_TOKEN","").strip();_PENDING={}
def _http_json(url,data=None,timeout=35):
 body=None;headers={"User-Agent":"TutorBot-VK/1.0"}
 if data is not None:body=urlencode(data).encode();headers["Content-Type"]="application/x-www-form-urlencoded"
 with urlopen(Request(url,data=body,headers=headers),timeout=timeout) as r:return json.loads(r.read().decode())
def api(method,**params):
 if not TOKEN:raise RuntimeError("VK_TOKEN is not configured")
 p=dict(params);p["access_token"]=TOKEN;p["v"]=API_VERSION;d=_http_json(f"https://api.vk.com/method/{method}",p)
 if "error" in d:raise RuntimeError(f"VK API {method}: {d['error']}")
 return d.get("response")
def _button(label,command,color="secondary"):return {"action":{"type":"text","label":label,"payload":json.dumps({"command":command},ensure_ascii=False)},"color":color}
def _keyboard_rows(rows):return json.dumps({"one_time":False,"inline":False,"buttons":rows},ensure_ascii=False)
def keyboard(linked=False,mode="home",data=None):
 data=data or {}
 if mode=="teacher":return _keyboard_rows([[_button("📅 Сегодня","t_today","primary"),_button("👥 Ученики","t_students")],[_button("💬 Сообщения","t_messages"),_button("📝 Задать ДЗ","t_hw")],[_button("🎥 Отправить ссылку","t_link","positive"),_button("🔔 События","t_events")],[_button("🏠 Главная","t_home")]])
 if mode=="teacher_lessons":
  rows=[[_button("🎥 "+teacher_service.lesson_text(r),f"t_lesson|{r['id']}","primary")] for r in data.get("lessons",[])[:8]];rows.append([_button("🏠 Главная","t_home")]);return _keyboard_rows(rows)
 if mode=="teacher_students":
  rows=[[_button(f"👤 {r['name']} · {r['grade']} кл.",f"t_student|{r['id']}")] for r in data.get("students",[])[:20]];rows.append([_button("🏠 Главная","t_home")]);return _keyboard_rows(rows)
 if mode=="teacher_student":
  uid=int(data["user_id"]);return _keyboard_rows([[_button("📝 Задать ДЗ",f"t_hw_user|{uid}","primary"),_button("💬 Написать",f"t_msg_user|{uid}")],[_button("👥 Ученики","t_students"),_button("🏠 Главная","t_home")]])
 if mode=="teacher_lesson":
  lid=int(data["lesson_id"]);uid=int(data["user_id"]);return _keyboard_rows([[_button("🎥 Отправить ссылку",f"t_sendlink|{lid}","positive")],[_button("⏹ Завершить занятие",f"t_finish|{lid}","negative")],[_button("📝 Задать ДЗ",f"t_hw_user|{uid}")],[_button("📅 Сегодня","t_today"),_button("🏠 Главная","t_home")]])
 if mode=="college_courses":
  courses=data.get("courses",[]);current=data.get("current");rows=[]
  for course in courses:
   rows.append([_button(f"🎓 {college_curriculum.course_label(course)}",f"cf_course|{course}","primary" if course==current else "secondary")])
  rows.append([_button("🏠 Главная","home")]);return _keyboard_rows(rows)
 if mode=="college_subjects":
  course=int(data["course"]);rows=[[_button(f"📖 {label}",f"cf_subject|{course}|{key}","primary")] for key,label in college_curriculum.subjects(course)]
  rows.append([_button("⬅️ К курсам","formulas"),_button("🏠 Главная","home")]);return _keyboard_rows(rows)
 if mode=="college_topics":
  course=int(data["course"]);subject=data["subject"];rows=[[_button(title[:38],f"cf_topic|{course}|{subject}|{key}")] for key,title in college_curriculum.topics(course,subject)[:30]]
  rows.append([_button("⬅️ К предметам",f"cf_course|{course}"),_button("🏠 Главная","home")]);return _keyboard_rows(rows)
 if mode=="formula_grades":
  grades=data.get("grades",[]);rows=[]
  for i in range(0,len(grades),2):rows.append([_button(f"🎓 {g} класс",f"fg|{g}","primary" if i==0 else "secondary") for g in grades[i:i+2]])
  rows.append([_button("🏠 Главная","home")]);return _keyboard_rows(rows)
 if mode=="formula_subjects":
  grade=data["grade"];rows=[[_button(f"📖 {label}",f"fs|{grade}|{key}","primary")] for key,label in data.get("subjects",[])];rows.append([_button("⬅️ К классам","formulas"),_button("🏠 Главная","home")]);return _keyboard_rows(rows)
 if mode=="formula_topics":
  grade=data["grade"];subject=data["subject"];rows=[[_button(title[:38],f"ft|{grade}|{subject}|{key}")] for key,title in data.get("topics",[])[:30]];rows.append([_button("⬅️ К предметам",f"fg|{grade}"),_button("🏠 Главная","home")]);return _keyboard_rows(rows)
 if not linked:rows=[[_button("🔗 Связать с Telegram","link_help","primary")],[_button("ℹ️ Как это работает","help")]]
 elif mode=="cancel":rows=[[_button("❌ Отмена","cancel")],[_button("🏠 Главная","home")]]
 elif mode=="more":rows=[[_button("💳 Профиль и оплата","profile","primary")],[_button("💬 История сообщений","chat_history")],[_button("🔗 Связь с Telegram","linked")],[_button("🏠 Главная","home")]]
 else:rows=[[_button("📅 Мои занятия","lessons","primary"),_button("📝 Домашнее задание","homework")],[_button("📚 Моя учёба","study"),_button("🧮 Формулы","formulas")],[_button("💬 Преподаватель","teacher"),_button("🖥 Доска","board")],[_button("➕ Записаться","booking","positive"),_button("••• Ещё","more")]]
 return _keyboard_rows(rows)
def send(peer_id,text,linked=False,mode="home",data=None):return api("messages.send",peer_id=int(peer_id),random_id=random.randint(1,2_000_000_000),message=str(text),keyboard=keyboard(linked,mode,data))
def _extract_command(m):
 payload=m.get("payload")

 def unpack(value):
  for _ in range(4):
   if isinstance(value,dict):
    cmd=value.get("command") or value.get("cmd")
    if cmd:
     return str(cmd).strip()
    value=value.get("payload")
    if value is None:
     return ""
   elif isinstance(value,str):
    value=value.strip()
    if not value:
     return ""
    try:
     value=json.loads(value)
    except Exception:
     return value
   else:
    return ""
  return ""

 cmd=unpack(payload)
 if cmd:
  return cmd

 t=" ".join(
  str(m.get("text") or "")
  .strip()
  .lower()
  .split()
 )

 mp={
  "📅 мои занятия":"lessons",
  "📝 домашнее задание":"homework",
  "📚 моя учёба":"study",
  "🧮 формулы":"formulas",
  "💬 преподаватель":"teacher",
  "🖥 доска":"board",
  "➕ записаться":"booking",
  "••• ещё":"more",
  "💳 профиль и оплата":"profile",
  "💬 история сообщений":"chat_history",
  "🏠 главное меню":"home",
  "🏠 главная":"home",
  "❌ отмена":"cancel",
  "🔗 связь с telegram":"linked",
  "🔗 связать с telegram":"link_help",
  "ℹ️ как это работает":"help",
  "привет":"home",
  "начать":"home",
  "start":"home",
  "/start":"home",

  "📅 сегодня":"t_today",
  "👥 ученики":"t_students",
  "💬 сообщения":"t_messages",
  "📝 задать дз":"t_hw",
  "🎥 отправить ссылку":"t_link",
  "🔔 события":"t_events",
 }

 return mp.get(t,"")

def _profile(v):
 try:
  rows=api("users.get",user_ids=int(v),fields="screen_name") or []
  if rows:r=rows[0];return {"display_name":f"{r.get('first_name','')} {r.get('last_name','')}".strip(),"username":r.get("screen_name")}
 except Exception:pass
 return {"display_name":None,"username":None}
def _student_home(p,u):send(p,f"💜 АДЕЛИЯ • ГЛАВНАЯ\n\n{u['name']}, я рядом и собрала главное в одном месте.\n\n📅 Занятия, ДЗ, учёба и связь с преподавателем доступны ниже.",True)
def _teacher_home(p):send(p,teacher_service.home_text(),True,"teacher")
def _attachment_label(attachments):
 from .attachment_bridge import vk_attachment_descriptor
 names=[]
 for x in attachments or []:
  d=vk_attachment_descriptor(x)
  if d:names.append(d['filename'])
 return ', '.join(names)
def _handle_teacher(p,v,c,raw,attachments=None):
 attachments=attachments or [];pending=_PENDING.get(v)
 if pending and not c:
  _PENDING.pop(v,None);kind=pending[0]
  if kind=="t_link":
   delivered,error=teacher_service.send_lesson_link(int(pending[1]),raw);send(p,"❌ "+error if error else f"✅ Ссылка отправлена.\nTelegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}",True,"teacher");return
  if kind=="t_hw":
   if not raw and attachments:raw='📎 '+_attachment_label(attachments)
   hid,delivered=teacher_service.create_homework(int(pending[1]),raw);uid=int(pending[1])
   if attachments:
    from .attachment_bridge import vk_forward_to_student
    files=vk_forward_to_student(uid,attachments,f"📝 ДЗ #{hid}\n\n{raw}")
   send(p,f"✅ ДЗ #{hid} создано.\nTelegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}",True,"teacher");return
  if kind=="t_msg":
   uid=int(pending[1]);from crm_plus import service as crm;from .channel_delivery import send_student
   delivered=send_student(uid,f"👨‍🏫 Сообщение от преподавателя\n\n{raw}") if raw else {'telegram':False,'vk':False}
   if attachments:
    from .attachment_bridge import vk_forward_to_student
    files=vk_forward_to_student(uid,attachments,raw or '👨‍🏫 Файл от преподавателя')
    delivered['telegram']=delivered['telegram'] or files['telegram']>0;delivered['vk']=delivered['vk'] or files['vk']>0
   label=raw+(('\n' if raw else '')+f"📎 {_attachment_label(attachments)}" if attachments else '');crm.log_message(uid,'OUT',label,int(teacher_service.is_teacher(v)),'STUDENT','SENT' if any(delivered.values()) else 'FAILED');send(p,f"✅ Отправлено. Telegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}",True,"teacher");return
 if c in ("t_home","home",""):_teacher_home(p);return
 if c in ("t_today","t_link"):
  rows=teacher_service.today_lessons();send(p,"📅 СЕГОДНЯ\n\nВыбери занятие:" if rows else "📅 Сегодня занятий нет.",True,"teacher_lessons",{"lessons":rows});return
 if c in ("t_students","t_hw"):
  rows=teacher_service.active_students();send(p,"👥 УЧЕНИКИ\n\nВыбери ученика:",True,"teacher_students",{"students":rows});return
 if c.startswith("t_student|"):
  uid=int(c.split("|",1)[1]);u=database.get_user(uid);send(p,f"👤 {u['name']} · {u['grade']} класс",True,"teacher_student",{"user_id":uid});return
 if c.startswith("t_lesson|"):
  lid=int(c.split("|",1)[1]);l=database.get_lesson(lid);u=database.get_user(int(l['user_id']));send(p,f"🎓 ЗАНЯТИЕ\n\n👤 {u['name']}\n🕐 {str(l['start_time'])[11:16]}",True,"teacher_lesson",{"lesson_id":lid,"user_id":int(u['id'])});return
 if c.startswith("t_finish|"):
  lid=int(c.split("|",1)[1])
  try:
   result=database.finish_lesson(lid)
   send(p,f"✅ Занятие завершено.\n\n⏱ Фактически: {result['actual_minutes']} мин\n⏳ Недоработано: {result['underworked_minutes']} мин\n🎁 Бонус ученику: {result['bonus_minutes_awarded']} мин",True,"teacher")
  except Exception as exc:
   send(p,f"❌ Не удалось завершить занятие: {exc}",True,"teacher")
  return
 if c.startswith("t_sendlink|"):_PENDING[v]=("t_link",int(c.split("|",1)[1]));send(p,"🎥 Пришли следующим сообщением ссылку на Телемост.",True,"teacher");return
 if c.startswith("t_hw_user|"):_PENDING[v]=("t_hw",int(c.split("|",1)[1]));send(p,"📝 Пришли текст ДЗ и/или прикрепи фото/файл. Всё уйдёт ученику в Telegram и VK.",True,"teacher");return
 if c.startswith("t_msg_user|"):_PENDING[v]=("t_msg",int(c.split("|",1)[1]));send(p,"💬 Пришли текст, фото или файл ученику.",True,"teacher");return
 if c in ("t_messages","t_events"):send(p,"🔔 Уведомления преподавателя активны. Новые сообщения учеников и напоминания перед занятиями будут приходить сюда автоматически.",True,"teacher");return
 _teacher_home(p)
def handle_message(m):
 v=int(m.get("from_id") or 0);p=int(m.get("peer_id") or v)
 if v<=0:return
 c=_extract_command(m);raw=str(m.get("text") or "").strip();attachments=m.get('attachments') or []
 print("VK BUTTON:", "from=",v, "command=",repr(c), "text=",repr(raw), "payload=",repr(m.get("payload")), flush=True)
 if raw.upper().replace(" ","").startswith("ADELIA-ADMIN-"):
  pr=_profile(v);aid,error=schema.consume_admin_link_code(raw,"VK",str(v),pr.get("username"),pr.get("display_name"));send(p,"❌ "+error if error else "✅ VK преподавателя подключён к TutorBot.\n\nТеперь рабочие уведомления и действия доступны здесь.",not bool(error),"teacher" if not error else "home");return
 if teacher_service.is_teacher(v):_handle_teacher(p,v,c,raw,attachments);return
 u=service.linked_user(v)
 if raw.upper().replace(" ","").startswith("ADELIA-"):
  pr=_profile(v);uid,error=schema.consume_link_code(raw,"VK",str(v),pr.get("username"),pr.get("display_name"));send(p,"❌ "+error if error else f"✅ VK подключён к TutorBot.\n\nТеперь это одна карточка ученика: {database.get_user(int(uid))['name']}.",not bool(error));return
 if not u:send(p,"💜 АДЕЛИЯ\n\nДля ученика: получи код «🔗 Привязать VK» в Telegram.\nДля преподавателя: используй /vkadminlink в Telegram.",False);return
 if c.startswith("trial_keep_slot|"):
  from handlers import trial_ux_runtime
  lesson_id=int(c.split("|",1)[1])
  ok,text=trial_ux_runtime.create_same_time_request(int(u["id"]),lesson_id)
  send(p,text,True)
  return
 pending=_PENDING.get(v)
 if pending and not c:
  _PENDING.pop(v,None);uid=int(u['id'])
  if pending=="teacher_message":
   label=raw+(('\n' if raw else '')+f"📎 {_attachment_label(attachments)}" if attachments else '')
   if not label:send(p,'Пришли текст, фото или файл 💜',True);return
   _,r=service.submit_teacher_message(uid,label,v)
   if attachments:
    try:
     from .attachment_bridge import vk_forward_to_admin_telegram
     vk_forward_to_admin_telegram(attachments,f"💬 Файл от {u['name']}\n\n{raw}")
    except Exception as exc:print('VK STUDENT ATTACHMENT ERROR:',repr(exc))
   send(p,r,True);return
  if pending=="booking":_,r=service.submit_booking_request(uid,raw);send(p,r,True);return
 if c=="cancel":_PENDING.pop(v,None);send(p,"Хорошо, действие отменено 💜",True);return
 if c in ("home",""):_student_home(p,u);return
 uid=int(u['id'])
 if c=="lessons":send(p,service.upcoming_text(uid),True);return
 if c=="homework":send(p,service.homework_text(uid),True);return
 if c=="study":send(p,service.study_text(uid),True);return
 if c=="formulas":
  profile=education_profile.get(uid)
  if profile["type"]=="COLLEGE":
   current=int(profile["level"] or 1)
   send(p,f"🧮 ФОРМУЛЫ И ТЕМЫ КОЛЛЕДЖА\n\n🎓 {profile['label']}\n\nТвой курс показан первым 👇",True,"college_courses",{"courses":college_curriculum.courses(current),"current":current});return
  send(p,service.formulas_text(uid),True,"formula_grades",{"grades":service.formula_grades(uid)});return
 if c.startswith("cf_course|"):
  course=int(c.split("|",1)[1]);send(p,f"🎓 {college_curriculum.course_label(course)}\n\nВыбери предмет:",True,"college_subjects",{"course":course});return
 if c.startswith("cf_subject|"):
  _,course,subject=c.split("|",2);course=int(course);send(p,f"🎓 {college_curriculum.course_label(course)} · {college_curriculum.SUBJECT_NAMES.get(subject,subject)}\n\nВыбери тему:",True,"college_topics",{"course":course,"subject":subject});return
 if c.startswith("cf_topic|"):
  _,course,subject,topic=c.split("|",3);course=int(course);send(p,college_curriculum.topic(course,subject,topic) or "Тема не найдена.",True,"college_topics",{"course":course,"subject":subject});return
 if c.startswith("fg|"):
  g=int(c.split("|")[1]);send(p,f"🧮 {g} КЛАСС\n\nВыбери предмет:",True,"formula_subjects",{"grade":g,"subjects":service.formula_subjects(g)});return
 if c.startswith("fs|"):
  _,g,s=c.split("|",2);send(p,f"🧮 {g} КЛАСС · {service.SUBJECT_NAMES.get(s,s)}\n\nВыбери тему:",True,"formula_topics",{"grade":int(g),"subject":s,"topics":service.formula_topics(int(g),s)});return
 if c.startswith("ft|"):
  _,g,s,t=c.split("|",3);send(p,service.formula_topic(int(g),s,t) or "Тема не найдена.",True,"formula_topics",{"grade":int(g),"subject":s,"topics":service.formula_topics(int(g),s)});return
 if c=="board":send(p,service.board_text(uid),True);return
 if c=="teacher":_PENDING[v]="teacher_message";send(p,service.message_history_text(uid)+"\n\n✍️ Напиши текст или прикрепи фото/файл преподавателю.",True,"cancel");return
 if c=="chat_history":send(p,service.message_history_text(uid),True,"more");return
 if c=="booking":_PENDING[v]="booking";send(p,"➕ Напиши желаемый день, время и предмет одним сообщением.",True,"cancel");return
 if c in ("more","profile"):send(p,service.more_text(uid),True,"more");return
 if c=="linked":send(p,f"✅ VK связан с карточкой «{u['name']}».",True,"more");return
 _student_home(p,u)
def long_poll_server():
 d=api("groups.getLongPollServer",group_id=GROUP_ID);return d["server"],d["key"],d["ts"]
def run_forever():
 if not GROUP_ID or not TOKEN:raise SystemExit("VK_GROUP_ID/VK_TOKEN are not configured")
 schema.initialize();notification_sync.initialize();teacher_notifications.initialize();__import__('homework_attachments').initialize();__import__('homework_attachments').install_vk_bridge();server,key,ts=long_poll_server();print(f"VK LONG POLL START group={GROUP_ID} api={API_VERSION}");last=0.0
 while True:
  try:
   d=_http_json(f"{server}?"+urlencode({"act":"a_check","key":key,"ts":ts,"wait":25}),timeout=35)
   if d.get("failed"):server,key,ts=long_poll_server();continue
   ts=d.get("ts",ts)
   for upd in d.get("updates",[]):
    utype=upd.get("type")
    obj=upd.get("object") or {}

    if utype=="message_new":
     msg=obj.get("message") if isinstance(obj,dict) else None
     if msg:
      handle_message(msg)

    elif utype=="message_event" and isinstance(obj,dict):
     event_payload=obj.get("payload")
     synthetic={
      "from_id":obj.get("user_id") or obj.get("from_id"),
      "peer_id":obj.get("peer_id") or obj.get("user_id"),
      "text":"",
      "payload":event_payload,
      "attachments":[],
     }
     print(
      "VK MESSAGE_EVENT:",
      repr(synthetic),
      flush=True,
     )
     handle_message(synthetic)
   now=time.monotonic()
   if now-last>=30:
    try:notification_sync.tick(send);teacher_notifications.tick(lambda peer,text:send(peer,text,True,"teacher"))
    except Exception as exc:print("VK NOTIFICATION ERROR:",repr(exc))
    last=now
  except KeyboardInterrupt:raise
  except Exception as exc:
   print("VK LONG POLL ERROR:",repr(exc));time.sleep(3)
   try:server,key,ts=long_poll_server()
   except Exception:time.sleep(5)
if __name__=="__main__":run_forever()
