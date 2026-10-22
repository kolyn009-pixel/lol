"""Previewed teacher absences, private reasons and durable reschedule invitations."""
from datetime import date,datetime,timedelta,timezone
import hashlib,json,secrets,threading
from zoneinfo import ZoneInfo
import database
from core.lesson_time import lesson_timezone,schedule_datetime
from web_backend import availability_guard as guard,teacher_day_off_state

REASONS=[
 ('NEUTRAL','Без объяснения причины','Мне необходимо изменить расписание на этот день и перенести наше занятие.'),
 ('PERSONAL','Личные обстоятельства','По важным личным обстоятельствам я не смогу провести занятие в назначенное время.'),
 ('FAMILY','Семейные обстоятельства','Из-за семейных обстоятельств мне необходимо перенести наше занятие.'),
 ('HEALTH','Здоровье','По состоянию здоровья я не смогу провести занятие в назначенное время.'),
 ('URGENT','Срочное дело','Возникло срочное обстоятельство, из-за которого я не смогу провести занятие.'),
 ('TECHNICAL','Техническая проблема','Из-за технических неполадок я не смогу провести занятие качественно, поэтому предлагаю перенести его.'),
 ('CUSTOM','Своя причина','')]
_worker_started=False
_worker_lock=threading.Lock()

def start_worker():
 global _worker_started
 with _worker_lock:
  if _worker_started:return
  _worker_started=True
 def run():
  while True:
   try:dispatch(5);sync_calendar_jobs()
   except Exception as e:print('[day-off] delivery:',type(e).__name__,flush=True)
   threading.Event().wait(5)
 threading.Thread(target=run,name='day-off-delivery',daemon=True).start()

def now():return datetime.now(lesson_timezone()).replace(tzinfo=None)
def _hash(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def ensure_schema():
 teacher_day_off_state.ensure_schema();c=database.connect()
 try:
  c.executescript('''CREATE TABLE IF NOT EXISTS day_off_previews(token TEXT PRIMARY KEY,payload TEXT NOT NULL,fingerprint TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS day_off_batches(id INTEGER PRIMARY KEY,preview_token TEXT UNIQUE NOT NULL,private_reason TEXT NOT NULL,public_reason TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS day_off_invitations(id INTEGER PRIMARY KEY,batch_id INTEGER NOT NULL,kind TEXT NOT NULL,lesson_id INTEGER NOT NULL,
    original_start TEXT NOT NULL,original_end TEXT NOT NULL,public_reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'WAITING',new_start TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
    UNIQUE(kind,lesson_id,original_start));
  CREATE TABLE IF NOT EXISTS day_off_deliveries(id INTEGER PRIMARY KEY,invitation_id INTEGER NOT NULL,event TEXT NOT NULL,channel TEXT NOT NULL,target TEXT NOT NULL,
    title TEXT NOT NULL,body TEXT NOT NULL,url TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',updated_at TEXT NOT NULL,
    UNIQUE(invitation_id,event,channel,target));
  CREATE INDEX IF NOT EXISTS day_off_pending ON day_off_invitations(status,lesson_id);''');c.commit()
  c.execute("CREATE TABLE IF NOT EXISTS day_off_calendar_jobs(invitation_id INTEGER PRIMARY KEY,lesson_id INTEGER NOT NULL,start_time TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',updated_at TEXT NOT NULL)");c.commit()
 finally:c.close()

def _payload(body):
 if not isinstance(body,dict):raise ValueError('Некорректные параметры.')
 try:a=date.fromisoformat(str(body.get('date','')));b=date.fromisoformat(str(body.get('end_date') or a))
 except ValueError:raise ValueError('Выберите даты выходного.') from None
 if a<now().date() or b<a or (b-a).days>30:raise ValueError('Выберите период от сегодняшнего дня, не больше 31 дня.')
 whole=body.get('whole_day') is True;s=e=None
 if not whole:
  try:
   s=datetime.strptime(str(body.get('start_time')),'%H:%M').strftime('%H:%M');e=datetime.strptime(str(body.get('end_time')),'%H:%M').strftime('%H:%M')
  except ValueError:raise ValueError('Укажите время начала и окончания.') from None
  if e<=s:raise ValueError('Окончание должно быть позже начала.')
 reason=str(body.get('reason') or '').strip()
 if len(reason)>1000:raise ValueError('Причина слишком длинная: максимум 1000 символов.')
 if not reason:reason=REASONS[0][2]
 return {'date':a.isoformat(),'end_date':b.isoformat(),'whole_day':whole,'start_time':s,'end_time':e,'reason':reason,'share_reason':body.get('share_reason') is True}

def _ranges(p):
 d=date.fromisoformat(p['date']);end=date.fromisoformat(p['end_date'])
 while d<=end:
  start=datetime.fromisoformat(d.isoformat()+'T'+(p['start_time'] or '00:00'))
  finish=datetime.fromisoformat(d.isoformat()+'T'+p['end_time']) if p['end_time'] else start+timedelta(days=1)
  yield d,start,finish;d+=timedelta(days=1)

def _affected(c,p):
 ranges=list(_ranges(p));out=[]
 rows=c.execute("SELECT l.*,u.name student_name FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.lesson_status IN ('CONFIRMED','PENDING','IN_PROGRESS')").fetchall()
 for raw in rows:
  r=dict(raw);a=guard._dt(r['start_time']);b=guard._dt(r['end_time'])
  if any(a<e and s<b for _,s,e in ranges) and b>now():
   if r['lesson_status']=='IN_PROGRESS' or a<=now():raise ValueError('Занятие уже началось. Сначала завершите его или измените период выходного.')
   if r['lesson_status']=='PENDING':raise ValueError('В выбранном периоде есть неподтверждённая запись. Сначала примите или отклоните её.')
   out.append({'kind':'LESSON','lesson_id':r['id'],'user_id':r['user_id'],'student_name':r['student_name'],'start_time':r['start_time'],'end_time':r['end_time'],'duration_minutes':r['duration_minutes']})
 if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='group_lessons'").fetchone():
  rows=c.execute("SELECT l.*,g.name group_name FROM group_lessons l JOIN study_groups g ON g.id=l.group_id WHERE l.status IN ('SCHEDULED','STARTED','IN_PROGRESS')").fetchall()
  for raw in rows:
   r=dict(raw);a=guard._dt(r['start_time']);b=guard._dt(r['end_time'])
   if any(a<e and s<b for _,s,e in ranges) and b>now():
    if r['status']!='SCHEDULED' or a<=now():raise ValueError('Групповое занятие уже началось. Измените период выходного.')
    users=[dict(x) for x in c.execute('SELECT u.id,u.name FROM group_lesson_participants p JOIN users u ON u.id=p.user_id WHERE p.lesson_id=?',(r['id'],))]
    out.append({'kind':'GROUP','lesson_id':r['id'],'student_name':r['group_name'],'users':users,'start_time':r['start_time'],'end_time':r['end_time'],'duration_minutes':int((b-a).total_seconds()/60)})
 return sorted(out,key=lambda x:(x['start_time'],x['kind'],x['lesson_id']))

def _zone(c,uid):
 try:
  from web_backend.student_portal import _student_timezone
  u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
  return ZoneInfo(_student_timezone(u,c)['zone'])
 except Exception:return lesson_timezone()

def _text(item,reason,zone,parent=False,name=None,moved=False):
 dt=schedule_datetime(item['new_start'] if moved else item['start_time']).astimezone(zone)
 when=dt.strftime('%d.%m.%Y в %H:%M')+' ('+str(zone)+')'
 intro=(f"Занятие ученика {name or ''}" if parent else 'Наше занятие')
 if moved:return f'{intro} перенесено на {when}. Оплата, длительность и стоимость сохранены.'
 if item['kind']=='GROUP':return f"Групповое занятие «{item['student_name']}» {when} необходимо перенести.\n{reason}\nПреподаватель подберёт новое время для всей группы. Оплата сохранится, доплачивать за перенос не нужно. Если есть ограничения по времени, напишите в чат группы."
 ending='Извините за изменение планов. Выберите удобное время по ссылке ниже. Если подходящего времени нет — напишите мне, подберём его вместе.' if parent else 'Извини за изменение планов. Выбери удобное время по кнопке ниже. Если подходящего времени нет — напиши мне, подберём его вместе.'
 return f'{intro} {when} необходимо перенести.\n{reason}\n{ending}\nОплата сохранится, доплачивать за перенос не нужно.'

def _parents(c,uid):
 try:
  account_cols={r['name'] for r in c.execute('PRAGMA table_info(parent_accounts)')};link_cols={r['name'] for r in c.execute('PRAGMA table_info(parent_student_links)')}
  telegram='p.telegram_id' if 'telegram_id' in account_cols else 'NULL AS telegram_id'
  preference=' AND COALESCE(l.notify_schedule,1)=1' if 'notify_schedule' in link_cols else ''
  return [dict(r) for r in c.execute('SELECT DISTINCT p.id,'+telegram+' FROM parent_student_links l JOIN parent_accounts p ON p.id=l.parent_id WHERE l.student_id=? AND p.active=1'+preference,(uid,))]
 except Exception:return []

def _messages(c,item,reason,moved=False):
 users=item.get('users') if item['kind']=='GROUP' else [{'id':item['user_id'],'name':item['student_name']}];out=[]
 for user in users:
  uid=int(user['id']);zone=_zone(c,uid);text=_text(item,reason,zone,moved=moved)
  url='/app/?dayoff='+str(item.get('invitation_id','')) if not moved else '/app/?tab=schedule'
  if item['kind']=='GROUP':url='/app/?tab=groups'
  out.append({'role':'student','target':uid,'name':user['name'],'body':text,'url':url,'timezone':str(zone)})
  for parent in _parents(c,uid):out.append({'role':'parent','target':int(parent['id']),'telegram_id':parent.get('telegram_id'),'name':user['name'],'body':_text(item,reason,zone,True,user['name'],moved),'url':'/app/parent/','timezone':str(zone)})
 return out

def preview(body):
 ensure_schema();p=_payload(body);c=database.connect()
 try:
  items=_affected(c,p);public=p['reason'] if p['share_reason'] else REASONS[0][2];messages=[m for item in items for m in _messages(c,item,public)]
  token=secrets.token_urlsafe(32);c.execute('DELETE FROM day_off_previews WHERE created_at<?',((datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=1)).isoformat(),))
  c.execute('INSERT INTO day_off_previews VALUES(?,?,?,?)',(token,json.dumps(p,ensure_ascii=False),_hash({'items':items,'messages':messages}),database.now_iso()));c.commit()
  return {'preview_token':token,'affected_lessons':items,'affected_count':len(items),'messages':messages,'timezone':str(lesson_timezone()),'public_reason':public}
 finally:c.close()

def _queue(c,item,reason,event='INVITE'):
 title='🗓️ Выберите новое время занятия' if event=='INVITE' else '🗓️ Перенос подтверждён'
 for m in _messages(c,item,reason,event!='INVITE'):
  choices=[(m['role'],str(m['target']))]
  if m['role']=='student':
   user=c.execute('SELECT telegram_id FROM users WHERE id=?',(m['target'],)).fetchone()
   if user and user['telegram_id']:choices.append(('telegram',str(user['telegram_id'])))
   try:
    vk=c.execute("SELECT external_id FROM channel_identities WHERE user_id=? AND channel='VK' AND enabled=1",(m['target'],)).fetchall()
    choices.extend(('vk',str(r['external_id'])) for r in vk)
   except Exception:pass
  elif m.get('telegram_id'):choices.append(('telegram',str(m['telegram_id'])))
  for channel,target in choices:
   c.execute('''INSERT OR IGNORE INTO day_off_deliveries(invitation_id,event,channel,target,title,body,url,updated_at)
      VALUES(?,?,?,?,?,?,?,?)''',(item['invitation_id'],event,channel,target,title,m['body'],m['url'],database.now_iso()))

def save(body):
 ensure_schema();token=str(body.get('preview_token') or '');c=database.connect();ids=[]
 try:
  c.execute('BEGIN IMMEDIATE');existing=c.execute('SELECT id FROM day_off_batches WHERE preview_token=?',(token,)).fetchone()
  if existing:c.rollback();return {'status':'ok','batch_id':existing['id'],'already_saved':True,'deliveries':delivery_summary()}
  old=c.execute('SELECT * FROM day_off_previews WHERE token=?',(token,)).fetchone()
  if not old or datetime.fromisoformat(old['created_at'])<datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(minutes=15):raise ValueError('Предпросмотр устарел. Проверьте занятия ещё раз.')
  p=json.loads(old['payload']);items=_affected(c,p);public=p['reason'] if p['share_reason'] else REASONS[0][2]
  messages=[m for item in items for m in _messages(c,item,public)]
  if _hash({'items':items,'messages':messages})!=old['fingerprint']:raise ValueError('Расписание изменилось или обновились получатели. Проверьте затронутые занятия ещё раз.')
  stamp=database.now_iso()
  cur=c.execute('INSERT INTO day_off_batches(preview_token,private_reason,public_reason,created_at) VALUES(?,?,?,?)',(token,p['reason'],public,stamp));bid=cur.lastrowid
  for d,_,_ in _ranges(p):
   exists=c.execute("SELECT id FROM schedule_exceptions WHERE date=? AND exception_type='CLOSED' AND COALESCE(start_time,'')=? AND COALESCE(end_time,'')=?",(d.isoformat(),p['start_time'] or '',p['end_time'] or '')).fetchone()
   if exists:eid=exists['id']
   else:eid=c.execute("INSERT INTO schedule_exceptions(date,exception_type,start_time,end_time,comment,created_at) VALUES(?,'CLOSED',?,?,?,?)",(d.isoformat(),p['start_time'],p['end_time'],p['reason'],stamp)).lastrowid
   ids.append((d.isoformat(),eid))
  for item in items:
   cur=c.execute('''INSERT OR IGNORE INTO day_off_invitations(batch_id,kind,lesson_id,original_start,original_end,public_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)''',(bid,item['kind'],item['lesson_id'],item['start_time'],item['end_time'],public,stamp,stamp))
   if not cur.rowcount:continue
   item['invitation_id']=cur.lastrowid
   if item['kind']=='LESSON':
    eid=next((i for d,i in ids if d==guard._dt(item['start_time']).date().isoformat()),ids[0][1])
    c.execute("INSERT OR REPLACE INTO teacher_day_off_lessons VALUES(?,?,?,'TEACHER_DAY_OFF')",(item['lesson_id'],eid,stamp))
   _queue(c,item,public)
  c.commit()
 except BaseException:c.rollback();raise
 finally:c.close()
 # Delivery is explicit after commit; the durable inbox is already available.
 start_worker()
 return {'status':'ok','batch_id':bid,'affected_count':len(items),'deliveries':delivery_summary()}

def delivery_summary():
 c=database.connect()
 try:return {r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM day_off_deliveries GROUP BY status')}
 finally:c.close()

def dispatch(limit=40):
 c=database.connect()
 try:ids=[r['id'] for r in c.execute("SELECT id FROM day_off_deliveries WHERE status='PENDING' ORDER BY id LIMIT ?",(max(1,min(int(limit),100)),))]
 finally:c.close()
 for did in ids:
  c=database.connect()
  try:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM day_off_deliveries WHERE id=?',(did,)).fetchone()
   if not row or row['status']!='PENDING':c.rollback();continue
   c.execute("UPDATE day_off_deliveries SET status='SENDING',updated_at=? WHERE id=?",(database.now_iso(),did));c.commit();r=dict(row)
  finally:c.close()
  status='FAILED'
  try:
   url='https://adeliatutor.ru'+r['url'];message=r['title']+'\n\n'+r['body']+'\n\n'+url
   if r['channel'] in ('student','parent'):
    from web_backend import web_push
    body=r['body'] if len(r['body'])<=600 else r['body'][:600]+'… Полный текст в кабинете.'
    result=web_push.send(r['channel'],int(r['target']),r['title'],body,r['url'],'day-off-'+str(r['invitation_id'])+'-'+r['event'],{'type':'teacher_day_off','invitation_id':r['invitation_id']})
    status='SENT' if result.get('sent') else 'UNAVAILABLE' if not result.get('failed') else 'FAILED'
   else:
    from vk_adapter import channel_delivery as delivery
    if r['channel']=='telegram':
     label='Открыть кабинет' if '/parent/' in url else 'Открыть группу' if 'tab=groups' in url else 'Перенести занятие' if r['event']=='INVITE' else 'Открыть расписание'
     ok=delivery.send_telegram_chat(int(r['target']),message,{'inline_keyboard':[[{'text':label,'url':url}]]})
    else:ok=delivery.send_vk_peer(int(r['target']),message)
    status='SENT' if ok else 'FAILED'
  except Exception:status='FAILED'
  c=database.connect()
  try:c.execute('UPDATE day_off_deliveries SET status=?,updated_at=? WHERE id=?',(status,database.now_iso(),did));c.commit()
  finally:c.close()
 return delivery_summary()

def _refresh(c):
 for r in c.execute("SELECT * FROM day_off_invitations WHERE status='WAITING'").fetchall():
  table,key=('lessons','lesson_status') if r['kind']=='LESSON' else ('group_lessons','status')
  lesson=c.execute(f'SELECT start_time,{key} state FROM {table} WHERE id=?',(r['lesson_id'],)).fetchone()
  status=None
  if not lesson or lesson['state'] in ('CANCELLED','REJECTED'):status='CANCELLED'
  elif lesson['start_time']!=r['original_start']:status='MOVED_EXTERNALLY'
  elif lesson['state'] in ('COMPLETED','FINISHED'):status='COMPLETED'
  if status:c.execute('UPDATE day_off_invitations SET status=?,updated_at=? WHERE id=?',(status,database.now_iso(),r['id']))

def invitations(uid=None,teacher=False):
 ensure_schema();c=database.connect()
 try:
  _refresh(c);rows=c.execute("SELECT * FROM day_off_invitations ORDER BY CASE status WHEN 'WAITING' THEN 0 ELSE 1 END,id DESC LIMIT 300").fetchall();out=[]
  for raw in rows:
   r=dict(raw)
   if r['kind']=='LESSON':
    lesson=c.execute('SELECT l.*,u.name student_name FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?',(r['lesson_id'],)).fetchone()
    if not lesson or (not teacher and int(lesson['user_id'])!=int(uid)):continue
   else:
    lesson=c.execute('SELECT l.*,g.name student_name FROM group_lessons l JOIN study_groups g ON g.id=l.group_id WHERE l.id=?',(r['lesson_id'],)).fetchone()
    if not lesson or (not teacher and not c.execute('SELECT 1 FROM group_lesson_participants WHERE lesson_id=? AND user_id=?',(r['lesson_id'],uid)).fetchone()):continue
   r.update(student_name=lesson['student_name'],original_at=schedule_datetime(r['original_start']).isoformat(),current_start=lesson['start_time'],timezone=str(lesson_timezone()),viewer_timezone=str(lesson_timezone() if teacher else _zone(c,uid)))
   if teacher:
    batch=c.execute('SELECT private_reason FROM day_off_batches WHERE id=?',(r['batch_id'],)).fetchone();r['private_reason']=batch['private_reason'] if batch else ''
   out.append(r)
  c.commit();return {'items':out,'timezone':str(lesson_timezone()),'today':now().date().isoformat(),'templates':[{'id':a,'label':b,'text':t} for a,b,t in REASONS],**({'deliveries':delivery_summary()} if teacher else {})}
 finally:c.close()

def _owned(c,iid,uid,teacher=False):
 r=c.execute("SELECT * FROM day_off_invitations WHERE id=?",(int(iid),)).fetchone()
 if not r:raise PermissionError('Предложение переноса не найдено.')
 table='lessons' if r['kind']=='LESSON' else 'group_lessons';lesson=c.execute(f'SELECT * FROM {table} WHERE id=?',(r['lesson_id'],)).fetchone()
 if not lesson or (not teacher and (r['kind']!='LESSON' or int(lesson['user_id'])!=int(uid))):raise PermissionError('Предложение переноса не найдено.')
 if r['status']!='WAITING' or lesson['start_time']!=r['original_start']:raise ValueError('Это занятие уже изменено. Обновите список.')
 if (lesson['lesson_status'] if r['kind']=='LESSON' else lesson['status']) not in ('CONFIRMED','SCHEDULED'):raise ValueError('Занятие больше не доступно для переноса.')
 return dict(r),dict(lesson)

def _allowed(c,r,l,start,end,snapshot=None):
 if start<=now() or start.minute%15 or start.second or start.microsecond or start.date()!=end.date():return False
 if l.get('payment_status')=='AWAITING_PAYMENT' and start<=now()+timedelta(hours=2):return False
 hours=database.get_effective_working_hours(start.date(),conn=c)
 if not any(str(x['start_time'])[:5]<=start.strftime('%H:%M') and end.strftime('%H:%M')<=str(x['end_time'])[:5] for x in hours):return False
 # Explicit closures are checked on this transaction's connection, including
 # overnight lessons and offset-aware historic data.
 for x in c.execute("SELECT * FROM schedule_exceptions WHERE exception_type='CLOSED'"):
  a=datetime.fromisoformat(x['date']+'T'+(x['start_time'] or '00:00'));b=datetime.fromisoformat(x['date']+'T'+x['end_time']) if x['end_time'] else datetime.fromisoformat(x['date']+'T00:00')+timedelta(days=1)
  if start<b and a<end:return False
 snap=snapshot or guard.availability_snapshot(start,end,conn=c)
 snap={**snap,'group_lessons':[x for x in snap.get('group_lessons',[]) if not(r['kind']=='GROUP' and x['id']==r['lesson_id'])]}
 return not guard.conflicts_from_snapshot(start,end,snap,ignore_lesson_id=r['lesson_id'] if r['kind']=='LESSON' else None,ignore_regular_id=l.get('regular_schedule_id') if r['kind']=='LESSON' else None)

def slots(iid,uid=None,teacher=False):
 ensure_schema();c=database.connect()
 try:
  r,l=_owned(c,iid,uid,teacher);duration=guard._dt(l['end_time'])-guard._dt(l['start_time']);start=now().replace(hour=0,minute=0,second=0,microsecond=0)
  snap=guard.availability_snapshot(start,start+timedelta(days=31),conn=c);out=[]
  for n in range(31):
   day=(start+timedelta(days=n)).date();values=[]
   for x in database.get_effective_working_hours(day,conn=c):
    a=datetime.fromisoformat(day.isoformat()+'T'+str(x['start_time'])[:5]);end=datetime.fromisoformat(day.isoformat()+'T'+str(x['end_time'])[:5]);a+=timedelta(minutes=(-a.minute)%15)
    while a+duration<=end:
     if _allowed(c,r,l,a,a+duration,snap):values.append({'start_time':a.isoformat(),'start_at':schedule_datetime(a.isoformat()).isoformat(),'end_time':(a+duration).isoformat()})
     a+=timedelta(minutes=15)
   if values:out.append({'date':day.isoformat(),'slots':list({x['start_time']:x for x in values}.values())})
  return {'items':out,'timezone':str(lesson_timezone()),'duration_minutes':int(duration.total_seconds()/60)}
 finally:c.close()

def move(iid,start_value,uid=None,teacher=False):
 ensure_schema();start=guard._dt(start_value);c=database.connect()
 try:
  c.execute('BEGIN IMMEDIATE');r,l=_owned(c,iid,uid,teacher);end=start+(guard._dt(l['end_time'])-guard._dt(l['start_time']))
  if not _allowed(c,r,l,start,end):raise ValueError('Это время уже занято или недоступно. Выберите другое окно.')
  stamp=database.now_iso();table='lessons' if r['kind']=='LESSON' else 'group_lessons'
  c.execute(f'UPDATE {table} SET start_time=?,end_time=?,updated_at=? WHERE id=?',(start.isoformat(),end.isoformat(),stamp,r['lesson_id']))
  if r['kind']=='LESSON' and l.get('payment_status')=='AWAITING_PAYMENT':c.execute('UPDATE lessons SET payment_deadline=? WHERE id=?',((start-timedelta(hours=2)).isoformat(),r['lesson_id']))
  c.execute("UPDATE day_off_invitations SET status='RESCHEDULED',new_start=?,updated_at=? WHERE id=?",(start.isoformat(),stamp,int(iid)))
  # The old free-move entitlement is consumed; ordinary rules apply to the new date.
  if r['kind']=='LESSON':
   c.execute('DELETE FROM teacher_day_off_lessons WHERE lesson_id=?',(r['lesson_id'],))
   c.execute('INSERT INTO day_off_calendar_jobs VALUES(?,?,?,\'PENDING\',?)',(int(iid),r['lesson_id'],start.isoformat(),stamp))
  item={'kind':r['kind'],'lesson_id':r['lesson_id'],'invitation_id':r['id'],'start_time':r['original_start'],'new_start':start.isoformat()}
  if r['kind']=='LESSON':
   user=c.execute('SELECT name FROM users WHERE id=?',(l['user_id'],)).fetchone();item.update(user_id=l['user_id'],student_name=user['name'])
  else:
   group=c.execute('SELECT name FROM study_groups WHERE id=?',(l['group_id'],)).fetchone();item.update(student_name=group['name'],users=[dict(x) for x in c.execute('SELECT u.id,u.name FROM group_lesson_participants p JOIN users u ON u.id=p.user_id WHERE p.lesson_id=?',(l['id'],))])
  _queue(c,item,'',event='MOVED');c.commit()
 except BaseException:c.rollback();raise
 finally:c.close()
 start_worker()
 return {'status':'ok','start_time':start.isoformat(),'end_time':end.isoformat(),'calendar_sync_pending':r['kind']=='LESSON','payment_preserved':True}

def sync_calendar_jobs():
 c=database.connect()
 try:rows=[dict(r) for r in c.execute("SELECT * FROM day_off_calendar_jobs WHERE status='PENDING' ORDER BY invitation_id LIMIT 3")]
 finally:c.close()
 for r in rows:
  state='FAILED'
  try:
   lesson=database.get_lesson(r['lesson_id'])
   if not lesson or lesson['start_time']!=r['start_time']:state='SUPERSEDED'
   else:
    from core import schedule_sync
    result=schedule_sync.sync_lessons_blocking([r['lesson_id']]);state='FAILED' if result.get('failed') else 'DONE'
  except Exception:pass
  c=database.connect()
  try:c.execute('UPDATE day_off_calendar_jobs SET status=?,updated_at=? WHERE invitation_id=?',(state,database.now_iso(),r['invitation_id']));c.commit()
  finally:c.close()

def suppress_reminder(lesson_id,reminder_type=None):
 if not lesson_id:return False
 c=database.connect()
 try:
  if not c.execute("SELECT 1 FROM sqlite_master WHERE name='day_off_invitations' AND type='table'").fetchone():return False
  if c.execute("SELECT 1 FROM day_off_invitations d JOIN lessons l ON l.id=d.lesson_id WHERE d.kind='LESSON' AND d.lesson_id=? AND d.status='WAITING' AND d.original_start=l.start_time",(int(lesson_id),)).fetchone():return True
  if reminder_type:
   row=c.execute("SELECT l.start_time FROM day_off_invitations d JOIN lessons l ON l.id=d.lesson_id WHERE d.kind='LESSON' AND d.lesson_id=? AND d.status='RESCHEDULED' AND d.new_start=l.start_time LIMIT 1",(int(lesson_id),)).fetchone()
   if row:
    suffix=str(reminder_type).rsplit('_',1)[-1];minutes={'24H':1440,'8H':480,'2H':120,'30M':30,'10M':10}.get(suffix)
    if minutes is not None:return abs((guard._dt(row['start_time'])-timedelta(minutes=minutes)-now()).total_seconds())>1200
  return False
 finally:c.close()

def hold_auto_cancel(lesson_id):
 """Hold old non-payment timers while awaiting a teacher-initiated move."""
 c=database.connect()
 try:
  if not c.execute("SELECT 1 FROM sqlite_master WHERE name='day_off_invitations' AND type='table'").fetchone():return False
  rows=c.execute("SELECT d.status,d.original_start,d.new_start,l.start_time FROM day_off_invitations d JOIN lessons l ON l.id=d.lesson_id WHERE d.kind='LESSON' AND d.lesson_id=?",(int(lesson_id),)).fetchall()
  for r in rows:
   if r['status']=='WAITING' and r['original_start']==r['start_time']:return True
   if r['status']=='RESCHEDULED' and r['new_start']==r['start_time'] and now()<guard._dt(r['start_time'])-timedelta(hours=2):return True
  return False
 finally:c.close()
