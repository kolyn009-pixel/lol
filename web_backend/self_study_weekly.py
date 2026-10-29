"""Seven real calendar days of own evidence. No CEFR inference or fake streaks."""
from datetime import datetime,timedelta,timezone,time
from zoneinfo import ZoneInfo
import json
from database import connect
from web_backend import self_study as core,self_study_practice as practice


def clock():return datetime.now(timezone.utc)


def report(owner,language):
 if language not in core.profile(owner)['languages']:raise ValueError('invalid_language')
 practice.sync_lessons(owner)
 from web_backend import self_study_listening as listening,self_study_conversation as conversation,self_study_skills as skills,self_study_scenes as scenes
 for module in (listening,conversation,skills,scenes):module.ensure_schema()
 today=clock().astimezone(ZoneInfo('Europe/Moscow')).date()
 start=datetime.combine(today-timedelta(days=6),time.min,ZoneInfo('Europe/Moscow')).astimezone(timezone.utc)
 end=datetime.combine(today+timedelta(days=1),time.min,ZoneInfo('Europe/Moscow')).astimezone(timezone.utc)
 def within(value):return bool(value) and start<=datetime.fromisoformat(value)<end
 conn=connect()
 try:
  attempts=[dict(r) for r in conn.execute('SELECT * FROM personal_study_attempts WHERE owner_id=? AND language=? ORDER BY id',(owner,language))]
  seen=set();first=[];repeats=[];dates=set()
  for a in attempts:
   fresh=a['lesson_id'] not in seen;seen.add(a['lesson_id'])
   if within(a['created_at']):
    (first if fresh else repeats).append(a);dates.add(datetime.fromisoformat(a['created_at']).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat())
  reviews=[dict(r) for r in conn.execute('SELECT r.created_at,r.correct,r.rating FROM personal_study_reviews r JOIN personal_study_cards c ON c.id=r.card_id WHERE r.owner_id=? AND c.language=? AND r.rating IS NOT NULL',(owner,language)) if within(r['created_at'])]
  for r in reviews:dates.add(datetime.fromisoformat(r['created_at']).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat())
  from learning.listening_program import SOURCES
  heard=[];known=set()
  for r in conn.execute('SELECT * FROM personal_study_listening WHERE owner_id=? ORDER BY id',(owner,)):
   source=SOURCES.get(r['source_id'])
   if not source or source['language']!=language or not r['first_result']:continue
   familiar=r['source_id'] in known;known.add(r['source_id'])
   listened=json.loads(r['first_result']).get('saved_at',r['created_at'])
   if within(listened):heard.append({'source_id':r['source_id'],'familiar':familiar,'delivery':source.get('delivery','publisher'),'result':json.loads(r['first_result'])})
  controls=[{'form_id':r['form_id'],'completed_at':r['completed_at'],'skills':json.loads(r['feedback'])['skills']} for r in conn.execute('SELECT * FROM personal_study_checkpoints WHERE owner_id=? AND language=? AND fresh=1 AND completed_at IS NOT NULL',(owner,language)) if within(r['completed_at'])]
  samples=[dict(r) for r in conn.execute('SELECT skill,created_at FROM personal_study_skill_samples WHERE owner_id=? AND language=?',(owner,language)) if within(r['created_at'])]
  scene_count=sum(within(r['created_at']) for r in conn.execute('SELECT created_at FROM personal_study_scenes WHERE owner_id=? AND language=?',(owner,language)))
  errors=[dict(r) for r in conn.execute("SELECT topic,wrong_count,status FROM personal_study_errors WHERE owner_id=? AND language=? AND status!='RESOLVED' ORDER BY wrong_count DESC,last_failed_at DESC LIMIT 3",(owner,language))]
  tutor_turns=0
  if conn.execute("SELECT 1 FROM sqlite_master WHERE name='personal_study_tutor_turns'").fetchone():
   tutor_turns=sum(within(r['created_at']) for r in conn.execute('SELECT t.created_at FROM personal_study_tutor_turns t JOIN personal_study_tutor s ON s.id=t.session_id WHERE s.owner_id=? AND s.language=?',(owner,language)))
 finally:conn.close()
 # Counted activity dates deliberately cover module attempts and rated cards only.
 focus=('Начни с одной повторяющейся трудности: '+errors[0]['topic']+'. Повтори по памяти, затем примени в другой ситуации.' if errors else 'Добавь короткое аудирование и пересказ.' if not heard else 'Продолжай чередовать новый материал и самостоятельное воспроизведение.')
 return {'language':language,'from':start.astimezone(ZoneInfo('Europe/Moscow')).date().isoformat(),'through':today.isoformat(),'recorded_days':sorted(dates),'first_modules':len(first),'repeat_modules':len(repeats),'first_module_answers':{'correct':sum(a['correct'] for a in first),'total':sum(a['total'] for a in first)},'rated_cards':len(reviews),'recalled_cards':sum(r['correct'] for r in reviews),'listening':heard,'new_controls':controls,'speaking_samples':sum(s['skill']=='speaking' for s in samples),'writing_samples':sum(s['skill']=='writing' for s in samples),'tutor_turns':tutor_turns,'saved_scenes':scene_count,'difficulties':errors,'next_focus':focus,
 'note':'Последние 7 календарных дней по Москве. Первые модули и повторы разделены; в модулях разрешена помощь. Новые контрольные показаны отдельно. Дни учитывают проверки модулей и оценённые карточки, не все действия. Речь и письмо здесь — сохранённые образцы, без независимого балла. Разные задания не доказывают рост CEFR; дедлайн и нагрузка сами не меняются.'}
