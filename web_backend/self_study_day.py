"""Resumable personal study sessions. Self-report never becomes a test score."""
from datetime import datetime, timezone
import json
from zoneinfo import ZoneInfo
from database import connect
from learning.language_program import lesson


def ensure_schema():
    conn=connect()
    try:
        conn.executescript('''CREATE TABLE IF NOT EXISTS personal_study_sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,language TEXT NOT NULL,
          lesson_id TEXT NOT NULL,local_date TEXT NOT NULL,timezone TEXT NOT NULL,
          minutes INTEGER NOT NULL,plan TEXT NOT NULL,step INTEGER NOT NULL DEFAULT 0,
          version INTEGER NOT NULL DEFAULT 1,status TEXT NOT NULL DEFAULT 'ACTIVE',
          baseline_attempt INTEGER NOT NULL,baseline_review INTEGER NOT NULL,
          evidence TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
          CREATE UNIQUE INDEX IF NOT EXISTS idx_personal_session_active
          ON personal_study_sessions(owner_id,language) WHERE status IN ('ACTIVE','PAUSED');''');conn.commit()
    finally:conn.close()


def _payload(row):
    result=dict(row);result.pop('owner_id');result['plan']=json.loads(result['plan']);result['evidence']=json.loads(result['evidence'])
    result['material']=lesson(row['lesson_id'])
    result['content_exhausted']=any(p.get('familiar_only') for p in result['plan'])
    result['note']=('Стартовый набор пройден: закрепляем знакомое. ' if result['content_exhausted'] else '')+'Понимание материала и устный перенос отмечаются тобой. Проверяемый результат относится только к заданиям.'
    return result


def current(owner,language):
    ensure_schema();conn=connect()
    try:
        row=conn.execute("SELECT * FROM personal_study_sessions WHERE owner_id=? AND language=? AND status IN ('ACTIVE','PAUSED') ORDER BY id DESC LIMIT 1",(owner,language)).fetchone()
        return {'session':_payload(row) if row else None}
    finally:conn.close()


def _plan(minutes,has_review):
    names=[('input','Понять материал'),('practice','Проверить себя'),('transfer','Применить в своей ситуации')]
    if has_review and minutes>=15:names.insert(0,('review','Вспомнить несколько выражений'))
    weights=[1,2,2] if len(names)==3 else [1,2,3,2]
    parts=[max(1,minutes*w//sum(weights)) for w in weights]
    parts[-1]+=minutes-sum(parts)
    return [{'kind':kind,'title':title,'minutes':part} for (kind,title),part in zip(names,parts)]


def start(owner,data):
    from web_backend.self_study import overview
    from web_backend.self_study_practice import practice
    from web_backend.self_study_placement import result as diagnostic
    state=overview(owner);language=data.get('language');minutes=data.get('minutes')
    if language not in state['courses']:raise ValueError('invalid_language')
    if type(minutes) is not int or not 5<=minutes<=state['profile']['languages'][language]['minutes']:raise ValueError('invalid_session_minutes')
    zone=data.get('timezone','Europe/Moscow')
    try:tz=ZoneInfo(zone)
    except (KeyError,ValueError,TypeError):raise ValueError('invalid_timezone') from None
    active=current(owner,language)['session']
    if active:return {'action':'resume','session':active}
    cfg=state['profile'].get('preferences')
    if owner<0 and diagnostic(owner,language) is None:
        return {'action':'diagnostic','note':'Сначала стартовая проверка выбранного языка, чтобы выбрать начальную точку.'}
    route=state.get('routes',{}).get(language)
    if route and route['enabled'] and route['next_action']!='lesson':
        return {'action':'route_check' if route['next_action']=='check' else 'route_review','language':language,
                'band':route['current_band'],'note':'Открой маршрут: следующий шаг — проверка блока или его итог, а не повторное назначение старого урока.'}
    course=state['courses'][language]
    unfinished=[item for item in course if not item['passed']]
    draft=next((item for item in unfinished if item['draft']),None)
    route_next=next((item for item in course if route and route['enabled'] and item['id']==route['next_lesson']),None)
    chosen=route_next or draft or (unfinished[0] if unfinished else course[0])
    exhausted=not unfinished
    has_review=practice(owner,language)['due']>0
    plan=_plan(minutes,has_review)
    if exhausted:
        plan[-1]['title']='Перенести знакомый материал в новую ситуацию'
        plan[-1]['familiar_only']=True
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds');ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        old=conn.execute("SELECT * FROM personal_study_sessions WHERE owner_id=? AND language=? AND status IN ('ACTIVE','PAUSED')",(owner,language)).fetchone()
        if old:return {'action':'resume','session':_payload(old)}
        baseline=conn.execute('SELECT COALESCE(MAX(id),0) FROM personal_study_attempts WHERE owner_id=?',(owner,)).fetchone()[0]
        review=conn.execute('SELECT COALESCE(MAX(id),0) FROM personal_study_reviews WHERE owner_id=?',(owner,)).fetchone()[0]
        cursor=conn.execute('''INSERT INTO personal_study_sessions
          (owner_id,language,lesson_id,local_date,timezone,minutes,plan,baseline_attempt,baseline_review,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(owner,language,chosen['id'],datetime.now(tz).date().isoformat(),zone,minutes,json.dumps(plan,ensure_ascii=False),baseline,review,stamp,stamp))
        row=conn.execute('SELECT * FROM personal_study_sessions WHERE id=?',(cursor.lastrowid,)).fetchone();conn.commit()
        return {'action':'start','session':_payload(row),'content_exhausted':exhausted,
                'note':'Стартовый набор пройден. Это занятие закрепляет знакомое, а не подтверждает новый уровень.' if exhausted else 'Занятие подобрано по текущей программе.'}
    except Exception:conn.rollback();raise
    finally:conn.close()


def update(owner,data):
    sid,version=data.get('session_id'),data.get('version');action=data.get('action')
    if type(sid) is not int or type(version) is not int:raise ValueError('invalid_session')
    if action not in ('advance','skip_review','pause','resume','shorten'):raise ValueError('invalid_session')
    ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM personal_study_sessions WHERE id=? AND owner_id=?',(sid,owner)).fetchone()
        if not row:raise ValueError('session_not_found')
        if row['version']!=version:raise ValueError('session_changed')
        if row['status']=='FINISHED':return {'session':_payload(row)}
        step=row['step'];plan=json.loads(row['plan']);evidence=json.loads(row['evidence']);status=row['status']
        if action=='shorten':
            minutes=data.get('minutes')
            remaining=sum(p['minutes'] for p in plan[step:])
            if type(minutes) is not int or minutes not in (5,10):raise ValueError('invalid_short_minutes')
            budget=min(minutes,remaining);parts=plan[step:]
            # Preserve every prerequisite and completed step; shorten estimates only.
            allocation=[max(1,budget//len(parts)) for _ in parts];allocation[-1]+=budget-sum(allocation)
            for p,n in zip(parts,allocation):p['minutes']=n
            status='ACTIVE'
        elif action=='pause':status='PAUSED'
        elif action=='resume':status='ACTIVE'
        else:
            if status=='PAUSED':raise ValueError('session_paused')
            stage=plan[step]['kind'];record={'stage':stage,'type':'self_report'}
            if action=='skip_review':
                if stage!='review':raise ValueError('invalid_session')
                record['type']='skipped'
            elif stage=='practice':
                attempt=conn.execute('''SELECT id,correct,total FROM personal_study_attempts
                  WHERE owner_id=? AND lesson_id=? AND id>? ORDER BY id DESC LIMIT 1''',(owner,row['lesson_id'],row['baseline_attempt'])).fetchone()
                if not attempt:raise ValueError('practice_result_required')
                record={'stage':stage,'type':'checked_task',**dict(attempt)}
            elif stage=='review':
                review=conn.execute('''SELECT r.id FROM personal_study_reviews r JOIN personal_study_cards c ON c.id=r.card_id AND c.owner_id=r.owner_id
                  WHERE r.owner_id=? AND r.id>? AND r.rating IS NOT NULL AND c.language=? LIMIT 1''',(owner,row['baseline_review'],row['language'])).fetchone()
                if not review:raise ValueError('review_result_required')
                record={'stage':stage,'type':'recorded_review','review_id':review['id']}
            elif stage=='transfer':
                reflection=data.get('reflection')
                if reflection not in ('with_help','independent','difficult'):raise ValueError('reflection_required')
                record['reflection']=reflection
            evidence.append(record);step+=1
            if step>=len(plan):status='FINISHED'
        conn.execute('''UPDATE personal_study_sessions SET step=?,status=?,version=version+1,evidence=?,updated_at=?,plan=?,minutes=?
          WHERE id=?''',(step,status,json.dumps(evidence,ensure_ascii=False),datetime.now(timezone.utc).isoformat(timespec='seconds'),json.dumps(plan,ensure_ascii=False),sum(p['minutes'] for p in plan),sid))
        updated=conn.execute('SELECT * FROM personal_study_sessions WHERE id=?',(sid,)).fetchone();conn.commit()
        return {'session':_payload(updated)}
    except Exception:conn.rollback();raise
    finally:conn.close()
