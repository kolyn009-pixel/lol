"""Own lesson help and error transfer. Assisted drills never advance a course."""
import json
from uuid import UUID
from database import connect
from learning.language_workshop import scaffold,transfer
from web_backend import self_study as core,self_study_practice as practice


def ensure_schema():
 practice.ensure_schema();conn=connect()
 try:
  conn.execute('''CREATE TABLE IF NOT EXISTS personal_study_support(id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,request_id TEXT NOT NULL,lesson_id TEXT NOT NULL,check_id TEXT NOT NULL,mode TEXT NOT NULL,answer TEXT NOT NULL,correct INTEGER NOT NULL,created_at TEXT NOT NULL,UNIQUE(owner_id,request_id))''');conn.commit()
 finally:conn.close()


def material(owner,lesson_id,check_id=None,keys=False):
 item=core.get_lesson(owner,lesson_id)
 if item['language'] not in core.profile(owner)['languages']:raise ValueError('invalid_language')
 help=scaffold(item['language']);q=next((q for q in item['checks'] if q['id']==check_id),None)
 if check_id is not None and q is None:raise ValueError('invalid_answers')
 # get_lesson intentionally has no answer keys; resolve only after owning access.
 from learning.language_program import lesson
 full=lesson(lesson_id,include_keys=True);original=next((q for q in full['checks'] if q['id']==check_id),None)
 drill=transfer(original['answers'][0]) if original else None
 generic=not bool(drill)
 if generic:drill={'prompt':help['task'],'options':help['options'],'answer':help['answer'],'why':help['why']}
 if not keys:drill={k:v for k,v in drill.items() if k not in ('answer','why')}
 help={k:v for k,v in help.items() if k not in ('answer','options','task','why')}
 return {'lesson_id':lesson_id,'check_id':check_id or '', 'language':item['language'],'title':item['title'],'help':help,'phrases':item['phrases'][:3],'drill':drill,'generic':generic,
 'note':'Помощь и упражнение с опорой не повышают баллы модуля. '+('Это общая разминка по языку; похожего задания именно на эту конструкцию пока нет.' if generic and check_id else 'Попробуй новую ситуацию, затем вернись к заданию.')}


def submit(owner,data):
 rid=data.get('request_id');mode=data.get('mode','support')
 try:UUID(rid)
 except (ValueError,TypeError,AttributeError):raise ValueError('invalid_request_id') from None
 if mode not in ('support','repair'):raise ValueError('invalid_answers')
 m=material(owner,data.get('lesson_id'),data.get('check_id') or None,keys=True)
 answer=data.get('answer')
 if not isinstance(answer,str) or answer not in m['drill']['options']:raise ValueError('invalid_answers')
 ensure_schema();conn=connect()
 try:
  conn.execute('BEGIN IMMEDIATE');old=conn.execute('SELECT * FROM personal_study_support WHERE owner_id=? AND request_id=?',(owner,rid)).fetchone()
  clean=(m['lesson_id'],m['check_id'],mode,answer)
  if old and tuple(old[k] for k in ('lesson_id','check_id','mode','answer'))!=clean:raise ValueError('request_conflict')
  correct=core.normalise(answer)==core.normalise(m['drill']['answer'])
  if not old:conn.execute('INSERT INTO personal_study_support(owner_id,request_id,lesson_id,check_id,mode,answer,correct,created_at) VALUES(?,?,?,?,?,?,?,?)',(owner,rid,*clean,int(correct),practice.stamp()))
  conn.commit()
  return {'correct':correct,'expected':m['drill']['answer'],'explanation':m['drill']['why'],'note':'Отдельная тренировка с опорой. Результаты урока и интервалы карточек не изменены.'}
 except Exception:conn.rollback();raise
 finally:conn.close()


def repair(owner,language):
 if language not in core.profile(owner)['languages']:raise ValueError('invalid_language')
 practice.sync_lessons(owner);conn=connect()
 try:errors=[dict(r) for r in conn.execute("SELECT lesson_id,check_id,topic,wrong_count,status FROM personal_study_errors WHERE owner_id=? AND language=? AND status!='RESOLVED' ORDER BY wrong_count DESC,last_failed_at DESC LIMIT 12",(owner,language))]
 finally:conn.close()
 return {'errors':errors,'note':'Чаще возвращаемся к повторяющимся трудностям. Ошибка закрепляется только после верных воспроизведений в разные дни; отдельная разминка не закрывает её автоматически.'}
