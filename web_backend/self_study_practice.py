"""Spaced recall, error recovery and short parallel checks for private study.

Scheduling uses UTC instants. A self-rating cannot turn an incorrect answer into a
successful recall. Checkpoint results are separate from familiar lesson attempts.
"""
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from database import connect
from learning.language_program import LANGUAGES, lesson
from learning.language_checkpoints import FORMS, checkpoint


def clock():return datetime.now(timezone.utc)
def stamp():return clock().isoformat(timespec='seconds')


def ensure_schema():
    conn=connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS personal_study_cards (
          id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,language TEXT NOT NULL,
          lesson_id TEXT NOT NULL,source TEXT NOT NULL,source_key TEXT NOT NULL,
          prompt TEXT NOT NULL,answer TEXT NOT NULL,options TEXT NOT NULL DEFAULT '[]',
          explanation TEXT NOT NULL DEFAULT '',due_at TEXT NOT NULL,interval_days INTEGER NOT NULL DEFAULT 0,
          streak INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 0,
          success_days INTEGER NOT NULL DEFAULT 0,last_success_day TEXT,
          UNIQUE(owner_id,lesson_id,source,source_key));
        CREATE INDEX IF NOT EXISTS idx_personal_cards_due ON personal_study_cards(owner_id,language,due_at);
        CREATE TABLE IF NOT EXISTS personal_study_errors (
          owner_id INTEGER NOT NULL,lesson_id TEXT NOT NULL,check_id TEXT NOT NULL,
          language TEXT NOT NULL,topic TEXT NOT NULL,wrong_count INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL DEFAULT 'OPEN',last_failed_at TEXT NOT NULL,
          PRIMARY KEY(owner_id,lesson_id,check_id));
        CREATE TABLE IF NOT EXISTS personal_study_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,request_id TEXT NOT NULL,
          card_id INTEGER NOT NULL,card_version INTEGER NOT NULL,answer TEXT NOT NULL,
          correct INTEGER NOT NULL,created_at TEXT NOT NULL,rating TEXT,response TEXT,
          UNIQUE(owner_id,request_id));
        CREATE INDEX IF NOT EXISTS idx_personal_reviews_card ON personal_study_reviews(owner_id,card_id,card_version);
        CREATE TABLE IF NOT EXISTS personal_study_checkpoints (
          id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,language TEXT NOT NULL,
          form_id TEXT NOT NULL,fresh INTEGER NOT NULL,started_at TEXT NOT NULL,
          completed_at TEXT,answers TEXT NOT NULL DEFAULT '{}',feedback TEXT);
        CREATE INDEX IF NOT EXISTS idx_personal_checkpoints ON personal_study_checkpoints(owner_id,language,id);
        CREATE TABLE IF NOT EXISTS personal_study_practice_sync (
          owner_id INTEGER PRIMARY KEY,last_attempt_id INTEGER NOT NULL DEFAULT 0);
        ''')
        conn.commit()
    finally:conn.close()


def _lang(value):
    if value not in LANGUAGES:raise ValueError('invalid_language')
    return value


def _id(value):
    if type(value) is not int or value<1:raise ValueError('invalid_id')
    return value


def record_lesson(conn,owner_id,item,results):
    """Runs inside the caller's transaction; schema must exist before BEGIN."""
    current=stamp()
    from web_backend.self_study import normalise
    existing_vocab={normalise(r['answer']) for r in conn.execute("SELECT answer FROM personal_study_cards WHERE owner_id=? AND language=? AND source='vocabulary'",(owner_id,item['language']))}
    for index,phrase in enumerate(item['phrases']):
        if normalise(phrase['front']) in existing_vocab:continue
        conn.execute('''INSERT OR IGNORE INTO personal_study_cards
          (owner_id,language,lesson_id,source,source_key,prompt,answer,due_at)
          VALUES(?,?,?,'phrase',?,?,?,?)''',
          (owner_id,item['language'],item['id'],str(index),phrase['back'],phrase['front'],current))
    checks={q['id']:q for q in item['checks']}
    for result in results:
        if result['correct']:continue
        q=checks[result['id']]
        conn.execute('''INSERT INTO personal_study_errors VALUES(?,?,?,?,?,1,'OPEN',?)
          ON CONFLICT(owner_id,lesson_id,check_id) DO UPDATE SET
          wrong_count=wrong_count+1,status='OPEN',last_failed_at=excluded.last_failed_at''',
          (owner_id,item['id'],q['id'],item['language'],item['title'],current))
        conn.execute('''INSERT INTO personal_study_cards
          (owner_id,language,lesson_id,source,source_key,prompt,answer,options,explanation,due_at)
          VALUES(?,?,?,'error',?,?,?,?,?,?)
          ON CONFLICT(owner_id,lesson_id,source,source_key) DO UPDATE SET
          due_at=excluded.due_at,streak=0,success_days=0,last_success_day=NULL,
          interval_days=0,version=version+1''',
          (owner_id,item['language'],item['id'],q['id'],q['prompt'],q['answers'][0],
           json.dumps(q.get('options',[]),ensure_ascii=False),q['explanation'],current))


def sync_lessons(owner_id):
    # Backfill stage-1 attempts exactly once and atomically; subsequent lessons
    # are picked up here too, so existing submit responses remain unchanged.
    from web_backend.self_study import ensure_schema as ensure_core
    ensure_core();ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        previous=conn.execute('SELECT last_attempt_id FROM personal_study_practice_sync WHERE owner_id=?',(owner_id,)).fetchone()
        last=previous[0] if previous else 0
        rows=conn.execute('SELECT * FROM personal_study_attempts WHERE owner_id=? AND id>? ORDER BY id',(owner_id,last)).fetchall()
        for row in rows:
            record_lesson(conn,owner_id,lesson(row['lesson_id'],True),json.loads(row['feedback'])['results'])
            last=row['id']
        conn.execute('''INSERT INTO personal_study_practice_sync VALUES(?,?)
          ON CONFLICT(owner_id) DO UPDATE SET last_attempt_id=excluded.last_attempt_id''',(owner_id,last))
        conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.close()


def _reveal(row,card):
    return {'review_id':row['id'],'correct':bool(row['correct']),'submitted':row['answer'],
            'expected':card['answer'],'explanation':card['explanation'],
            'kind':'recognition' if json.loads(card['options']) else 'recall',
            'note':'Ожидается короткое выражение из урока; другие естественные формулировки пока могут не распознаваться.'}


def practice(owner_id,language):
    _lang(language);sync_lessons(owner_id);conn=connect()
    try:
        rows=conn.execute('''SELECT c.* FROM personal_study_cards c WHERE c.owner_id=? AND c.language=? AND c.due_at<=?
          ORDER BY CASE c.source WHEN 'error' THEN 0 ELSE 1 END,
          COALESCE((SELECT e.wrong_count FROM personal_study_errors e WHERE e.owner_id=c.owner_id AND e.lesson_id=c.lesson_id AND e.check_id=c.source_key AND c.source='error'),0) DESC,c.due_at,c.id LIMIT 20''',(owner_id,language,stamp())).fetchall()
        items=[]
        for card in rows:
            pending=conn.execute('''SELECT * FROM personal_study_reviews WHERE owner_id=? AND card_id=?
              AND card_version=? AND rating IS NULL ORDER BY id DESC LIMIT 1''',(owner_id,card['id'],card['version'])).fetchone()
            items.append({'id':card['id'],'version':card['version'],'source':card['source'],
                          'lesson_id':card['lesson_id'],'prompt':card['prompt'],'options':json.loads(card['options']),
                          'pending':_reveal(pending,card) if pending else None})
        errors=[dict(r) for r in conn.execute('''SELECT lesson_id,check_id,topic,wrong_count,status,last_failed_at
          FROM personal_study_errors WHERE owner_id=? AND language=? ORDER BY last_failed_at DESC LIMIT 100''',(owner_id,language))]
        totals=conn.execute('''SELECT COUNT(*) total,COALESCE(SUM(due_at<=?),0) due,MIN(due_at) next_due_at
          FROM personal_study_cards WHERE owner_id=? AND language=?''',(stamp(),owner_id,language)).fetchone()
        return {'items':items,'errors':errors,'total':totals['total'],'due':totals['due'],
                'next_due_at':totals['next_due_at'],'language':language,
                'note':'Начни с 5–10 минут из дневного бюджета. Узнавание вариантов и воспроизведение без вариантов — разные задания.'}
    finally:conn.close()


def answer_card(owner_id,data):
    from web_backend.self_study import normalise
    cid=_id(data.get('card_id'));version=data.get('version');answer=data.get('answer');request=data.get('request_id')
    if type(version) is not int or version<0:raise ValueError('invalid_version')
    if not isinstance(answer,str) or not answer.strip() or len(answer)>1000:raise ValueError('invalid_answers')
    try:UUID(request)
    except (ValueError,TypeError,AttributeError):raise ValueError('invalid_request_id') from None
    answer=answer.strip();ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        card=conn.execute('SELECT * FROM personal_study_cards WHERE id=? AND owner_id=?',(cid,owner_id)).fetchone()
        if not card:raise ValueError('card_not_found')
        old=conn.execute('SELECT * FROM personal_study_reviews WHERE owner_id=? AND request_id=?',(owner_id,request)).fetchone()
        if old:
            if old['card_id']!=cid or old['answer']!=answer or old['card_version']!=version:raise ValueError('request_conflict')
            return _reveal(old,card)
        if card['version']!=version:raise ValueError('stale_review')
        if card['due_at']>stamp():raise ValueError('card_not_due')
        correct=normalise(answer)==normalise(card['answer'])
        cursor=conn.execute('''INSERT INTO personal_study_reviews
          (owner_id,request_id,card_id,card_version,answer,correct,created_at) VALUES(?,?,?,?,?,?,?)''',
          (owner_id,request,cid,version,answer,int(correct),stamp()))
        row=conn.execute('SELECT * FROM personal_study_reviews WHERE id=?',(cursor.lastrowid,)).fetchone()
        conn.commit();return _reveal(row,card)
    except Exception:conn.rollback();raise
    finally:conn.close()


def rate_card(owner_id,data):
    rid=_id(data.get('review_id'));rating=data.get('rating')
    if rating not in ('again','hard','good'):raise ValueError('invalid_rating')
    ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM personal_study_reviews WHERE id=? AND owner_id=?',(rid,owner_id)).fetchone()
        if not row:raise ValueError('review_not_found')
        if row['rating']:
            response=json.loads(row['response'])
            if response['requested_rating']!=rating:raise ValueError('request_conflict')
            return response
        card=conn.execute('SELECT * FROM personal_study_cards WHERE id=? AND owner_id=?',(row['card_id'],owner_id)).fetchone()
        if not card or card['version']!=row['card_version']:raise ValueError('stale_review')
        effective=rating if row['correct'] else 'again'
        current=clock();success_days=card['success_days'];last_day=card['last_success_day']
        if effective=='again':
            interval=0;streak=0;due=current+timedelta(minutes=10);success_days=0;last_day=None
        else:
            interval=1 if effective=='hard' else min(60,max(1,round(card['interval_days']*2.2)))
            streak=card['streak']+1;due=current+timedelta(days=interval)
            # Two recalls on separate UTC days, not two immediate button presses.
            if last_day!=current.date().isoformat():success_days+=1;last_day=current.date().isoformat()
        due_at=due.isoformat(timespec='seconds')
        conn.execute('''UPDATE personal_study_cards SET due_at=?,interval_days=?,streak=?,
          success_days=?,last_success_day=?,version=version+1 WHERE id=? AND owner_id=?''',
          (due_at,interval,streak,success_days,last_day,card['id'],owner_id))
        if card['source']=='error':
            state='OPEN' if effective=='again' else 'RESOLVED' if success_days>=2 else 'PRACTICING'
            conn.execute('''UPDATE personal_study_errors SET status=? WHERE owner_id=? AND lesson_id=? AND check_id=?''',
                          (state,owner_id,card['lesson_id'],card['source_key']))
        response={'status':'saved','review_id':rid,'requested_rating':rating,'rating':effective,
                  'due_at':due_at,'interval_days':interval,'correct':bool(row['correct'])}
        conn.execute('UPDATE personal_study_reviews SET rating=?,response=? WHERE id=?',
                      (effective,json.dumps(response),rid));conn.commit();return response
    except Exception:conn.rollback();raise
    finally:conn.close()


def checkpoint_status(owner_id,language):
    _lang(language);ensure_schema();conn=connect()
    try:
        rows=[dict(r) for r in conn.execute('''SELECT id,form_id,fresh,started_at,completed_at,feedback
          FROM personal_study_checkpoints WHERE owner_id=? AND language=? ORDER BY id''',(owner_id,language))]
    finally:conn.close()
    finished=[r for r in rows if r['completed_at']]
    fresh=[r for r in finished if r['fresh']]
    active=next((r for r in rows if not r['completed_at']),None)
    used={r['form_id'] for r in fresh};unseen=[f['id'] for f in FORMS if f['language']==language and f['id'] not in used]
    due=(datetime.fromisoformat(fresh[-1]['completed_at'])+timedelta(days=28)) if fresh and unseen else None
    available=bool(unseen and (due is None or clock()>=due))
    results=[{'id':r['id'],'form_id':r['form_id'],'fresh':bool(r['fresh']),
              'completed_at':r['completed_at'],**{k:json.loads(r['feedback'])[k] for k in ('correct','total','skills')}} for r in finished]
    return {'language':language,'active_id':active['id'] if active else None,
            'new_available':available,'next_new_at':due.isoformat() if due else None,
            'new_forms_remaining':len(unseen),'results':results,
            'practice_forms':sorted(used),
            'note':'Короткие проверки чтения и воспроизведения. Первая работа с новым текстом отмечается отдельно. Устная речь и аудирование здесь не измеряются; это не тест CEFR.'}


def _checkpoint_payload(row):
    item=checkpoint(row['form_id']);item.update(attempt_id=row['id'],fresh=bool(row['fresh']),
        answers=json.loads(row['answers']),completed_at=row['completed_at'],
        feedback=json.loads(row['feedback']) if row['feedback'] else None)
    return item


def start_checkpoint(owner_id,data):
    language=_lang(data.get('language'));practice_form=data.get('practice_form')
    if practice_form is not None and not isinstance(practice_form,str):raise ValueError('checkpoint_not_found')
    ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        active=conn.execute('''SELECT * FROM personal_study_checkpoints WHERE owner_id=? AND language=?
          AND completed_at IS NULL ORDER BY id DESC LIMIT 1''',(owner_id,language)).fetchone()
        if active:return _checkpoint_payload(active)
        completed=conn.execute('''SELECT form_id,completed_at FROM personal_study_checkpoints
          WHERE owner_id=? AND language=? AND fresh=1 AND completed_at IS NOT NULL ORDER BY id''',(owner_id,language)).fetchall()
        used={r['form_id'] for r in completed}
        if practice_form:
            if practice_form not in used:raise ValueError('checkpoint_not_found')
            chosen=practice_form;fresh=False
        else:
            unseen=[f['id'] for f in FORMS if f['language']==language and f['id'] not in used]
            if not unseen:raise ValueError('no_new_checkpoints')
            if completed and clock()<datetime.fromisoformat(completed[-1]['completed_at'])+timedelta(days=28):
                raise ValueError('checkpoint_not_due')
            chosen=unseen[0];fresh=True
        cursor=conn.execute('''INSERT INTO personal_study_checkpoints
          (owner_id,language,form_id,fresh,started_at) VALUES(?,?,?,?,?)''',(owner_id,language,chosen,int(fresh),stamp()))
        row=conn.execute('SELECT * FROM personal_study_checkpoints WHERE id=?',(cursor.lastrowid,)).fetchone()
        conn.commit();return _checkpoint_payload(row)
    except Exception:conn.rollback();raise
    finally:conn.close()


def get_checkpoint(owner_id,attempt_id):
    aid=_id(attempt_id);ensure_schema();conn=connect()
    try:
        row=conn.execute('SELECT * FROM personal_study_checkpoints WHERE id=? AND owner_id=?',(aid,owner_id)).fetchone()
        if not row:raise ValueError('checkpoint_not_found')
        return _checkpoint_payload(row)
    finally:conn.close()


def save_checkpoint(owner_id,data,complete=False):
    from web_backend.self_study import _answers, normalise
    aid=_id(data.get('attempt_id'));ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM personal_study_checkpoints WHERE id=? AND owner_id=?',(aid,owner_id)).fetchone()
        if not row:raise ValueError('checkpoint_not_found')
        item=checkpoint(row['form_id'],True);answers=_answers(data,item,complete=complete)
        if row['completed_at']:
            if not complete or json.loads(row['answers'])!=answers:raise ValueError('checkpoint_finished')
            return json.loads(row['feedback'])
        if not complete:
            conn.execute('UPDATE personal_study_checkpoints SET answers=? WHERE id=?',(json.dumps(answers,ensure_ascii=False),aid))
            conn.commit();return {'status':'saved'}
        skills={key:{'correct':0,'total':0} for key in ('comprehension','recall')};results=[]
        for q in item['checks']:
            correct=normalise(answers[q['id']]) in {normalise(a) for a in q['answers']}
            skills[q['skill']]['total']+=1;skills[q['skill']]['correct']+=int(correct)
            results.append({'id':q['id'],'prompt':q['prompt'],'submitted':answers[q['id']],
                            'correct':correct,'expected':q['answers'][0],'explanation':q['explanation']})
        response={'attempt_id':aid,'form_id':item['id'],'fresh':bool(row['fresh']),
                  'correct':sum(r['correct'] for r in results),'total':len(results),'skills':skills,'results':results}
        conn.execute('''UPDATE personal_study_checkpoints SET answers=?,feedback=?,completed_at=? WHERE id=?''',
                     (json.dumps(answers,ensure_ascii=False),json.dumps(response,ensure_ascii=False),stamp(),aid))
        conn.commit();return response
    except Exception:conn.rollback();raise
    finally:conn.close()
