"""Private recovery hints: no debt, deadline mutation or family sharing."""
from datetime import datetime,timedelta,timezone,date
from zoneinfo import ZoneInfo
import math
from database import connect


def clock():return datetime.now(timezone.utc)


def ensure_schema():
 conn=connect()
 try:conn.execute('CREATE TABLE IF NOT EXISTS personal_study_comfort(owner_id INTEGER PRIMARY KEY,minutes INTEGER NOT NULL DEFAULT 5)');conn.commit()
 finally:conn.close()


def report(owner,language):
 from web_backend.self_study import overview
 state=overview(owner)
 if language not in state['courses']:raise ValueError('invalid_language')
 ensure_schema();conn=connect()
 try:
  pref=conn.execute('SELECT minutes FROM personal_study_comfort WHERE owner_id=?',(owner,)).fetchone()
  stamps=[]
  for table,column in [('personal_study_attempts','created_at'),('personal_study_sessions','updated_at'),('personal_study_skill_samples','created_at')]:
   if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
    row=conn.execute('SELECT MAX('+column+') FROM '+table+' WHERE owner_id=? AND language=?',(owner,language)).fetchone()
    if row[0]:stamps.append(datetime.fromisoformat(row[0]))
 finally:conn.close()
 today=clock().astimezone(ZoneInfo('Europe/Moscow')).date();latest=max(stamps) if stamps else None
 gap=max(0,(today-latest.astimezone(ZoneInfo('Europe/Moscow')).date()).days) if latest else None
 spec=state['profile']['languages'][language];remaining=sum(item['minutes'] for item in state['courses'][language] if not item['passed'])
 days=math.ceil(remaining/spec['minutes']);earliest=today+timedelta(days=days)
 target=date.fromisoformat(spec['target_date']) if spec.get('target_date') else None
 return {'language':language,'short_minutes':min(pref['minutes'] if pref else 5,spec['minutes']),'last_activity':latest.isoformat() if latest else None,'gap_days':gap,'returning':gap is not None and gap>=3,
 'remaining_module_minutes':remaining,'earliest_module_date':earliest.isoformat(),'deadline_tight_for_modules':bool(target and target<earliest),
 'note':'Дата — нижняя оценка времени только на оставшиеся модули при ежедневной практике. Повторения, речь, аудирование и проверки требуют дополнительного времени; это не прогноз CEFR. Цель и дедлайн не меняются автоматически.',
 'privacy':'Результаты доступны только твоему аккаунту через обычные учебные API. Владелец управляет приглашениями, а не получает семейный отчёт. Администратор сервера технически имеет доступ к базе. Голосовые записи остаются в текущем браузере.'}


def save(owner,data):
 minutes=data.get('minutes')
 if type(minutes) is not int or minutes not in (5,10):raise ValueError('invalid_short_minutes')
 ensure_schema();conn=connect()
 try:conn.execute('INSERT INTO personal_study_comfort VALUES(?,?) ON CONFLICT(owner_id) DO UPDATE SET minutes=excluded.minutes',(owner,minutes));conn.commit()
 finally:conn.close()
 return {'minutes':minutes}
