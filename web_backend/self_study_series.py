"""Private resumable series workshop. No unlicensed media or invented scene facts."""
from uuid import UUID
from database import connect
from web_backend import self_study_scenes as scenes,self_study as core,self_study_practice as practice

STEPS=[('prepare','Подготовь сцену','Открой выбранный сериал на своём сервисе. Возьми короткий фрагмент и запиши серию и таймкод.'),('listen','Посмотри на смысл','Первый раз попробуй без субтитров. Кто чего хочет? Не пытайся разобрать каждое слово.'),('decode','Разбери трудное место','Включи субтитры на изучаемом языке. Проверь до трёх полезных выражений и повтори трудную реплику.'),('save','Сохрани сцену','Запиши таймкод, основную мысль и выражения в журнал. Перевод выражений проверь самостоятельно.'),('retell','Перескажи без текста','Закрой субтитры. Скажи своими словами, что произошло, что изменилось и как бы ты ответил.')]


def ensure_schema():
 scenes.ensure_schema();conn=connect()
 try:conn.execute('''CREATE TABLE IF NOT EXISTS personal_study_series_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,language TEXT NOT NULL,resource_id TEXT NOT NULL,minutes INTEGER NOT NULL,step INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 1,scene_id INTEGER,request_id TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(owner_id,request_id))''');conn.commit()
 finally:conn.close()


def payload(row):
 out=dict(row);out.pop('owner_id');out.pop('request_id')
 n=out['minutes'];alloc=[max(1,round(n*.1)),max(1,round(n*.25)),max(1,round(n*.25)),max(1,round(n*.2))];alloc.append(n-sum(alloc))
 out['steps']=[{'id':key,'title':title,'instruction':text,'minutes':alloc[i]} for i,(key,title,text) in enumerate(STEPS)]
 out['finished']=out['step']==5;out['note']='План и этапы сохраняются. Выполнение просмотра и пересказа отмечаешь ты. Плеер — у правообладателя; содержание сцены сервису неизвестно.'
 return out


def current(owner,language):
 if language not in core.profile(owner)['languages']:raise ValueError('invalid_language')
 ensure_schema();conn=connect()
 try:row=conn.execute('SELECT * FROM personal_study_series_plans WHERE owner_id=? AND language=? ORDER BY id DESC LIMIT 1',(owner,language)).fetchone()
 finally:conn.close()
 return {'plan':payload(row) if row else None}


def start(owner,data):
 show=scenes.resource(data.get('resource_id'),owner);language=show['language'];current(owner,language);minutes=data.get('minutes');rid=data.get('request_id')
 if minutes not in (5,10,15,20,30) or type(minutes) is not int:raise ValueError('invalid_series_plan')
 try:UUID(rid)
 except (ValueError,TypeError,AttributeError):raise ValueError('invalid_request_id') from None
 conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM personal_study_series_plans WHERE owner_id=? AND request_id=?',(owner,rid)).fetchone()
  if row:
   if row['resource_id']!=show['id'] or row['minutes']!=minutes:raise ValueError('request_conflict')
  else:
   old=conn.execute('SELECT * FROM personal_study_series_plans WHERE owner_id=? AND language=? AND step<5 ORDER BY id DESC LIMIT 1',(owner,language)).fetchone()
   if old:raise ValueError('series_plan_active')
   sid=conn.execute('INSERT INTO personal_study_series_plans(owner_id,language,resource_id,minutes,request_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(owner,language,show['id'],minutes,rid,practice.stamp(),practice.stamp())).lastrowid;row=conn.execute('SELECT * FROM personal_study_series_plans WHERE id=?',(sid,)).fetchone()
  conn.commit();return payload(row)
 except Exception:conn.rollback();raise
 finally:conn.close()


def advance(owner,data):
 sid,version=data.get('plan_id'),data.get('version')
 if type(sid) is not int or type(version) is not int:raise ValueError('invalid_series_plan')
 ensure_schema();conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM personal_study_series_plans WHERE owner_id=? AND id=?',(owner,sid)).fetchone()
  if not row:raise ValueError('invalid_series_plan')
  # A stale version cannot advance twice; reload current state after a lost reply.
  if row['version']!=version or row['step']>=5:raise ValueError('series_plan_changed')
  scene_id=row['scene_id']
  if row['step']==3:
   scene_id=data.get('scene_id')
   scene=conn.execute('SELECT * FROM personal_study_scenes WHERE owner_id=? AND id=?',(owner,scene_id)).fetchone()
   if not scene or scene['resource_id']!=row['resource_id'] or scene['created_at']<row['created_at']:raise ValueError('series_scene_required')
  if row['step']==4 and data.get('retold') is not True:raise ValueError('reflection_required')
  conn.execute('UPDATE personal_study_series_plans SET step=step+1,version=version+1,scene_id=?,updated_at=? WHERE id=?',(scene_id,practice.stamp(),sid));conn.commit()
  return payload(conn.execute('SELECT * FROM personal_study_series_plans WHERE id=?',(sid,)).fetchone())
 except Exception:conn.rollback();raise
 finally:conn.close()
