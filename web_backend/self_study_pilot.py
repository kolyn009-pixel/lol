"""Seven real days of own feedback; does not measure language competence."""
import json
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from database import connect


def today():return datetime.now(ZoneInfo('Europe/Moscow')).date()


def ensure_schema():
 conn=connect()
 try:conn.executescript('''CREATE TABLE IF NOT EXISTS personal_study_pilot(owner_id INTEGER PRIMARY KEY,started_on TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS personal_study_pilot_days(owner_id INTEGER NOT NULL,day INTEGER NOT NULL,ease INTEGER NOT NULL,effort INTEGER NOT NULL,minutes INTEGER NOT NULL,note TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(owner_id,day));''');conn.commit()
 finally:conn.close()


def status(owner):
 ensure_schema();conn=connect()
 try:
  start=conn.execute('SELECT started_on FROM personal_study_pilot WHERE owner_id=?',(owner,)).fetchone();rows=[dict(r) for r in conn.execute('SELECT day,ease,effort,minutes,note,version FROM personal_study_pilot_days WHERE owner_id=? ORDER BY day',(owner,))]
 finally:conn.close()
 if not start:return {'started':False,'days':[],'feedback':[]}
 from datetime import date
 first=date.fromisoformat(start[0]);elapsed=(today()-first).days
 tasks=['Пройти стартовые проверки и выбрать удобную цель.','Пройти занятие и сохранить паузу.','Попробовать карточки и повторение.','Прослушать запись и сравнить две попытки.','Завершить разговорную ситуацию.','Сохранить короткий образец письма.','Открыть четыре навыка и решить, что изменить.']
 return {'started':True,'started_on':start[0],'current_day':min(7,max(1,elapsed+1)),'finished_period':elapsed>=7,
 'days':[{'day':i+1,'date':(first+timedelta(days=i)).isoformat(),'task':task,'available':i<=elapsed,'recorded':any(r['day']==i+1 for r in rows)} for i,task in enumerate(tasks)],'feedback':rows,
 'note':'Это личные впечатления от сервиса, не подтверждение выполнения заданий или уровня. Дни нельзя пройти заранее. Сводка семьи владельцу автоматически не передаётся.'}


def start(owner):
 ensure_schema();conn=connect()
 try:conn.execute('INSERT OR IGNORE INTO personal_study_pilot VALUES(?,?)',(owner,today().isoformat()));conn.commit()
 finally:conn.close()
 return status(owner)


def save(owner,data):
 state=status(owner);day=data.get('day');version=data.get('version',0)
 if not state['started'] or type(day) is not int or not 1<=day<=7 or not state['days'][day-1]['available']:raise ValueError('pilot_day_unavailable')
 if type(version) is not int:raise ValueError('pilot_changed')
 for key in ('ease','effort'):
  if type(data.get(key)) is not int or not 1<=data[key]<=5:raise ValueError('invalid_pilot_feedback')
 minutes=data.get('minutes');note=data.get('note','')
 if type(minutes) is not int or not 0<=minutes<=180 or not isinstance(note,str) or len(note)>1000:raise ValueError('invalid_pilot_feedback')
 ensure_schema();conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');old=conn.execute('SELECT * FROM personal_study_pilot_days WHERE owner_id=? AND day=?',(owner,day)).fetchone()
  expected=old['version'] if old else 0
  values=(data['ease'],data['effort'],minutes,note.strip())
  if old and tuple(old[k] for k in ('ease','effort','minutes','note'))==values:
   conn.rollback();return status(owner)
  if expected!=version:raise ValueError('pilot_changed')
  conn.execute('INSERT INTO personal_study_pilot_days(owner_id,day,ease,effort,minutes,note) VALUES(?,?,?,?,?,?) ON CONFLICT(owner_id,day) DO UPDATE SET ease=excluded.ease,effort=excluded.effort,minutes=excluded.minutes,note=excluded.note,version=version+1',(owner,day,*values));conn.commit()
 except Exception:conn.rollback();raise
 finally:conn.close()
 return status(owner)
