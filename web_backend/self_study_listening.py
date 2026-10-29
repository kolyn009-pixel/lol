import json
from datetime import datetime,timezone
from uuid import UUID
from database import connect
from learning.listening_program import SOURCES,source


def ensure_schema():
 conn=connect()
 try:
  conn.execute('''CREATE TABLE IF NOT EXISTS personal_study_listening(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,request_id TEXT NOT NULL,source_id TEXT NOT NULL,first_result TEXT,second_result TEXT,created_at TEXT NOT NULL,UNIQUE(owner_id,request_id))''');conn.commit()
 finally:conn.close()


def catalog(owner,language):
 from web_backend.self_study import profile
 if language not in profile(owner)['languages']:raise ValueError('invalid_language')
 ensure_schema();conn=connect()
 try:
  rows=[_payload(r) for r in conn.execute('SELECT * FROM personal_study_listening WHERE owner_id=? ORDER BY id DESC LIMIT 100',(owner,)) if SOURCES[r['source_id']]['language']==language]
 finally:conn.close()
 return {'sources':[source(k) for k,v in SOURCES.items() if v['language']==language],'sessions':rows,
 'note':'Есть записи издателей и отдельная авторская студия с синтезом речи устройства. Тип материала указан в карточке. Первое и повторное прослушивания сохраняются отдельно; это практика, не экзамен.'}


def _payload(row):
 out={k:row[k] for k in ('id','source_id','created_at')}
 out['first']=json.loads(row['first_result']) if row['first_result'] else None
 out['second']=json.loads(row['second_result']) if row['second_result'] else None
 out['material']=source(row['source_id'],reveal=bool(out['first']))
 return out


def start(owner,data):
 material=source(data.get('source_id'));catalog(owner,material['language'])
 rid=data.get('request_id')
 try:
  if not isinstance(rid,str):raise ValueError()
  UUID(rid)
 except (ValueError,AttributeError):raise ValueError('invalid_request_id') from None
 conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM personal_study_listening WHERE owner_id=? AND request_id=?',(owner,rid)).fetchone()
  if row:
   if row['source_id']!=material['id']:raise ValueError('request_conflict')
  else:
   cid=conn.execute('INSERT INTO personal_study_listening(owner_id,request_id,source_id,created_at) VALUES(?,?,?,?)',(owner,rid,material['id'],datetime.now(timezone.utc).isoformat())).lastrowid
   row=conn.execute('SELECT * FROM personal_study_listening WHERE id=?',(cid,)).fetchone()
  conn.commit();return _payload(row)
 except Exception:conn.rollback();raise
 finally:conn.close()


def submit(owner,data):
 sid=data.get('session_id');phase=data.get('phase')
 if type(sid) is not int or phase not in ('first','second') or data.get('heard') is not True:raise ValueError('invalid_listening')
 ensure_schema();conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM personal_study_listening WHERE id=? AND owner_id=?',(sid,owner)).fetchone()
  if not row:raise ValueError('listening_not_found')
  if phase=='second' and not row['first_result']:raise ValueError('listening_first_required')
  m=source(row['source_id'],keys=True,reveal=True)
  if m['mode']=='checked':
   answers=data.get('answers')
   if not isinstance(answers,dict) or set(answers)!={q['id'] for q in m['checks']} or any(answers[q['id']] not in q['options'] for q in m['checks']):raise ValueError('invalid_answers')
   checked=[{'id':q['id'],'correct':answers[q['id']]==q['answer'],'expected':q['answer']} for q in m['checks']]
   result={'type':'checked','answers':answers,'correct':sum(r['correct'] for r in checked),'total':len(checked),'results':checked}
  else:
   note=data.get('note');reference=data.get('reference')
   if not isinstance(note,str) or not 3<=len(note.strip())<=1000 or not isinstance(reference,str) or not 1<=len(reference.strip())<=160:raise ValueError('invalid_listening')
   result={'type':'self_report','note':note.strip(),'reference':reference.strip()}
  result['phase']=phase
  previous=row[phase+'_result']
  if previous:
   old=json.loads(previous);old.pop('saved_at',None)
   if old!=result:raise ValueError('request_conflict')
   return _payload(row)
  result['saved_at']=datetime.now(timezone.utc).isoformat()
  conn.execute('UPDATE personal_study_listening SET '+phase+'_result=? WHERE id=?',(json.dumps(result,ensure_ascii=False),sid));conn.commit()
  return _payload(conn.execute('SELECT * FROM personal_study_listening WHERE id=?',(sid,)).fetchone())
 except Exception:conn.rollback();raise
 finally:conn.close()
