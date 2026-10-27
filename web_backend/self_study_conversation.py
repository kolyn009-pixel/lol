import json
from uuid import UUID
from datetime import datetime,timezone
from database import connect
from learning.conversation_program import DATA,scenario,prompt


def ensure_schema():
 conn=connect()
 try:
  conn.execute('''CREATE TABLE IF NOT EXISTS personal_study_conversations(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,request_id TEXT NOT NULL,scenario_id TEXT NOT NULL,answers TEXT NOT NULL DEFAULT '[]',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(owner_id,request_id))''');conn.commit()
 finally:conn.close()


def _payload(row):
 m=scenario(row['scenario_id']);answers=json.loads(row['answers']);turn=len(answers)
 return {'id':row['id'],'scenario_id':row['scenario_id'],'language':m['language'],'title':m['title'],'band':m['band'],'role':m['role'],'frames':m['frames'],'answers':answers,'turn':turn,'version':row['version'],'finished':turn==3,'prompt':prompt(m,answers,turn) if turn<3 else None,
 'note':'Собеседник следует авторским веткам по выбранному тобой намерению. Содержание ответа автоматически не распознаётся. Три сохранённые реплики — практика, не оценка CEFR.'}


def get(owner,sid):
 if type(sid) is not int:raise ValueError('conversation_not_found')
 ensure_schema();conn=connect()
 try:row=conn.execute('SELECT * FROM personal_study_conversations WHERE owner_id=? AND id=?',(owner,sid)).fetchone()
 finally:conn.close()
 if not row:raise ValueError('conversation_not_found')
 return _payload(row)


def catalog(owner,language):
 from web_backend.self_study import profile
 if language not in profile(owner)['languages']:raise ValueError('invalid_language')
 ensure_schema();conn=connect()
 try:rows=[_payload(r) for r in conn.execute('SELECT * FROM personal_study_conversations WHERE owner_id=? ORDER BY id DESC LIMIT 100',(owner,)) if DATA[r['scenario_id']]['language']==language]
 finally:conn.close()
 return {'scenarios':[{'id':k,**{p:v[p] for p in ('language','title','band','role')}} for k,v in DATA.items() if v['language']==language],'sessions':rows}


def start(owner,data):
 m=scenario(data.get('scenario_id'));catalog(owner,m['language']);rid=data.get('request_id')
 try:
  if not isinstance(rid,str):raise ValueError()
  UUID(rid)
 except (ValueError,AttributeError):raise ValueError('invalid_request_id') from None
 conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM personal_study_conversations WHERE owner_id=? AND request_id=?',(owner,rid)).fetchone()
  if row:
   if row['scenario_id']!=data['scenario_id']:raise ValueError('request_conflict')
  else:
   cid=conn.execute('INSERT INTO personal_study_conversations(owner_id,request_id,scenario_id,created_at) VALUES(?,?,?,?)',(owner,rid,data['scenario_id'],datetime.now(timezone.utc).isoformat())).lastrowid
   row=conn.execute('SELECT * FROM personal_study_conversations WHERE id=?',(cid,)).fetchone()
  conn.commit();return _payload(row)
 except Exception:conn.rollback();raise
 finally:conn.close()


def answer(owner,data):
 sid,version=data.get('session_id'),data.get('version');text=data.get('text');intention=data.get('intention');rid=data.get('request_id')
 if type(sid) is not int or type(version) is not int or not isinstance(text,str) or not 1<=len(text.strip())<=3000 or intention not in ('clarify','agree','alternative'):raise ValueError('invalid_conversation')
 try:
  if not isinstance(rid,str):raise ValueError()
  UUID(rid)
 except (ValueError,AttributeError):raise ValueError('invalid_request_id') from None
 ensure_schema();conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM personal_study_conversations WHERE owner_id=? AND id=?',(owner,sid)).fetchone()
  if not row:raise ValueError('conversation_not_found')
  answers=json.loads(row['answers']);m=scenario(row['scenario_id']);reflection=data.get('reflection')
  if reflection not in (None,'with_help','independent','difficult'):raise ValueError('invalid_conversation')
  record={'text':text.strip(),'intention':intention,'request_id':rid,'reflection':reflection}
  old=next((a for a in answers if a['request_id']==rid),None)
  if old:
   if any(old[k]!=record[k] for k in record):raise ValueError('request_conflict')
   return _payload(row)
  if row['version']!=version:raise ValueError('conversation_changed')
  if len(answers)>=3:raise ValueError('conversation_finished')
  if len(answers)==2 and reflection not in ('with_help','independent','difficult'):raise ValueError('reflection_required')
  record['prompt']=prompt(m,answers,len(answers));answers.append(record)
  conn.execute('UPDATE personal_study_conversations SET answers=?,version=version+1 WHERE id=?',(json.dumps(answers,ensure_ascii=False),sid));conn.commit()
  return _payload(conn.execute('SELECT * FROM personal_study_conversations WHERE id=?',(sid,)).fetchone())
 except Exception:conn.rollback();raise
 finally:conn.close()
