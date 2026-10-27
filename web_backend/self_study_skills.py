"""Four-skill evidence, separating checked tasks and self-report samples."""
import json
from datetime import datetime,timedelta,timezone
from uuid import UUID
from database import connect


def clock():return datetime.now(timezone.utc)


def ensure_schema():
 from web_backend import self_study_routes,self_study_listening,self_study_conversation,self_study_practice
 for module in (self_study_routes,self_study_listening,self_study_conversation,self_study_practice):module.ensure_schema()
 conn=connect()
 try:
  conn.executescript('''CREATE TABLE IF NOT EXISTS personal_study_skill_cycles(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,language TEXT NOT NULL,started_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS personal_study_skill_samples(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,language TEXT NOT NULL,skill TEXT NOT NULL,form_id TEXT NOT NULL,request_id TEXT NOT NULL,text TEXT NOT NULL,rubric TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(owner_id,request_id));''');conn.commit()
 finally:conn.close()


def _selected(owner,language):
 from web_backend.self_study import profile
 p=profile(owner)
 if language not in p['languages']:raise ValueError('invalid_language')
 return p


def cycle(owner,language,start=False):
 _selected(owner,language);ensure_schema();conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');rows=conn.execute('SELECT * FROM personal_study_skill_cycles WHERE owner_id=? AND language=? ORDER BY id',(owner,language)).fetchall()
  last=rows[-1] if rows else None;due=datetime.fromisoformat(last['started_at'])+timedelta(days=28) if last else clock()
  if start and (not last or clock()>=due):
   if len(rows)>=2:raise ValueError('skill_forms_exhausted')
   conn.execute('INSERT INTO personal_study_skill_cycles(owner_id,language,started_at) VALUES(?,?,?)',(owner,language,clock().isoformat()));conn.commit()
   rows=conn.execute('SELECT * FROM personal_study_skill_cycles WHERE owner_id=? AND language=? ORDER BY id',(owner,language)).fetchall();last=rows[-1];due=datetime.fromisoformat(last['started_at'])+timedelta(days=28)
  return {'active':bool(last),'form_id':('A' if len(rows)==1 else 'B') if last else None,'started_at':last['started_at'] if last else None,'next_at':due.isoformat() if last else None,'new_available':len(rows)<2 and (not last or clock()>=due),'forms_exhausted':len(rows)>=2}
 finally:conn.close()


def task(owner,language,skill):
 p=_selected(owner,language)
 if skill not in ('speaking','writing'):raise ValueError('invalid_skill')
 c=cycle(owner,language)
 if not c['active']:raise ValueError('skill_cycle_required')
 a=c['form_id']=='A'
 situation=('У вас запланировано занятие в четверг в 18:00. Ты занят до 19:00. Предложи другое время и уточни, подходит ли оно.' if a else 'Ты записался на очное занятие, но можешь участвовать только онлайн. Объясни ограничение и предложи решение.')
 frames={'en':['Could we…?','Would that work for you?'],'de':['Könnten wir…?','Passt dir das?'],'es':['¿Podemos…?','¿Te viene bien?'],'fa':['می‌توانیم ...؟','برای شما مناسب است؟']}[language]
 return {'language':language,'skill':skill,'form_id':c['form_id'],'prompt':situation+(' Ответь вслух 30–90 секунд. Сохрани расшифровку или заметку о трудности.' if skill=='speaking' else ' Составь короткое сообщение адресату: 2–5 фраз с опорами. Фантазировать не требуется.'),
 'extension':'Если это легко, объясни компромисс, альтернативу и условие пересмотра решения. Сложность задания не подтверждает уровень.',
 'frames':frames,'rubric':{'purpose':'Передал цель и существенное ограничение','connected':'Связал предложение с причиной','revised':'Перепроверил и исправил хотя бы одну трудность либо отметил, что её не нашёл'},
 'note':'Образец и отметки сохраняются как самооценка. Языковая правильность, качество аудио и CEFR автоматически не проверяются.'}


def save(owner,data):
 language,skill=data.get('language'),data.get('skill');t=task(owner,language,skill);rid=data.get('request_id');text=data.get('text');rubric=data.get('rubric')
 if data.get('form_id')!=t['form_id']:raise ValueError('skill_form_changed')
 try:
  if not isinstance(rid,str):raise ValueError()
  UUID(rid)
 except (ValueError,AttributeError):raise ValueError('invalid_request_id') from None
 if not isinstance(text,str) or not 1<=len(text.strip())<=4000 or not isinstance(rubric,dict) or set(rubric)!=set(t['rubric']) or any(type(v) is not bool for v in rubric.values()):raise ValueError('invalid_skill_sample')
 ensure_schema();conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM personal_study_skill_samples WHERE owner_id=? AND request_id=?',(owner,rid)).fetchone()
  if row:
   if (row['language'],row['skill'],row['form_id'],row['text'],json.loads(row['rubric']))!=(language,skill,t['form_id'],text.strip(),rubric):raise ValueError('request_conflict')
   return {'id':row['id'],'type':'self_report'}
  cid=conn.execute('INSERT INTO personal_study_skill_samples(owner_id,language,skill,form_id,request_id,text,rubric,created_at) VALUES(?,?,?,?,?,?,?,?)',(owner,language,skill,t['form_id'],rid,text.strip(),json.dumps(rubric),clock().isoformat())).lastrowid;conn.commit()
  return {'id':cid,'type':'self_report'}
 except Exception:conn.rollback();raise
 finally:conn.close()


def report(owner,language):
 _selected(owner,language);c=cycle(owner,language);ensure_schema();conn=connect()
 try:
  reading=[dict(r) for r in conn.execute('SELECT id,band,correct,total,created_at FROM personal_study_route_checks WHERE owner_id=? AND language=? ORDER BY id',(owner,language))]
  controls=[{'form_id':r['form_id'],'completed_at':r['completed_at'],**json.loads(r['feedback'])['skills']['comprehension']} for r in conn.execute('SELECT form_id,completed_at,feedback FROM personal_study_checkpoints WHERE owner_id=? AND language=? AND fresh=1 AND completed_at IS NOT NULL ORDER BY id',(owner,language))]
  first={}
  for r in reading:first.setdefault(r['band'],r)
  listening=[];seen=set()
  from learning.listening_program import SOURCES
  for r in conn.execute('SELECT * FROM personal_study_listening WHERE owner_id=? ORDER BY id',(owner,)):
   if SOURCES[r['source_id']]['language']!=language or not r['first_result']:continue
   value=json.loads(r['first_result']);listening.append({'id':r['id'],'source_id':r['source_id'],'first':value,'second':json.loads(r['second_result']) if r['second_result'] else None,'familiar':r['source_id'] in seen});seen.add(r['source_id'])
  from learning.conversation_program import DATA
  conversations=[r for r in conn.execute('SELECT * FROM personal_study_conversations WHERE owner_id=?',(owner,)) if DATA[r['scenario_id']]['language']==language and len(json.loads(r['answers']))==3]
  samples=[{**dict(r),'rubric':json.loads(r['rubric'])} for r in conn.execute('SELECT id,skill,form_id,text,rubric,created_at FROM personal_study_skill_samples WHERE owner_id=? AND language=? ORDER BY id',(owner,language))]
 finally:conn.close()
 return {'language':language,'cycle':c,'reading':{'new_controls':controls,'first_by_band':list(first.values()),'latest':reading[-1] if reading else None,'note':'Новый текст плюс языковые конструкции. Разные ступени напрямую не сравниваются; повторы не являются независимым ростом.'},
 'listening':{'attempts':listening,'note':'Проверяемые вопросы есть для отдельных EN-записей; покрытие остальных языков пока неполное. Факт прослушивания отмечает учащийся; знакомые записи выделены.'},
 'speaking':{'completed_conversations':len(conversations),'samples':[s for s in samples if s['skill']=='speaking'],'verification':'self_report','note':'Расшифровки и самооценка не подтверждают качество речи или произношение.'},
 'writing':{'samples':[s for s in samples if s['skill']=='writing'],'verification':'self_report','note':'Сохранённые тексты и самооценка. Независимой проверки письма пока нет.'},
 'note':'Четыре отдельных вида данных, без общего балла и автоматического CEFR. Отсутствие проверки означает пробел, а не нулевой уровень. Два варианта образцов; затем нужно новое наполнение.'}
