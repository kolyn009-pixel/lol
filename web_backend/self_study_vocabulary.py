"""Daily vocabulary additions with one atomic grant per UTC day and language."""
from datetime import datetime,timezone,date,timedelta
import json,math
from database import connect
from learning.language_program import lesson


def clock():return datetime.now(timezone.utc)


def ensure_schema():
    from web_backend.self_study_practice import ensure_schema as cards
    cards();conn=connect()
    try:
        conn.executescript('''CREATE TABLE IF NOT EXISTS personal_study_word_goals(
          owner_id INTEGER NOT NULL,language TEXT NOT NULL,target INTEGER NOT NULL,deadline TEXT NOT NULL,
          PRIMARY KEY(owner_id,language));
          CREATE TABLE IF NOT EXISTS personal_study_word_days(
          owner_id INTEGER NOT NULL,language TEXT NOT NULL,day TEXT NOT NULL,card_ids TEXT NOT NULL,
          PRIMARY KEY(owner_id,language,day));''');conn.commit()
    finally:conn.close()


def _context(owner,language):
    from web_backend.self_study import overview,normalise
    from web_backend.self_study_practice import sync_lessons
    state=overview(owner)
    if language not in state['courses']:raise ValueError('invalid_language')
    sync_lessons(owner);ensure_schema()
    bank={}
    route=state.get('routes',{}).get(language)
    permitted={item['id'] for node in route['stages'] if node['status'] in ('review','learning','complete','check_ready') for item in node['lessons']} if route and route['enabled'] else None
    potential=set()
    for unit in state['courses'][language]:
        for phrase in lesson(unit['id'])['phrases']:
            potential.add(normalise(phrase['front']))
            if permitted is not None and unit['id'] not in permitted:continue
            bank.setdefault(normalise(phrase['front']),{'front':phrase['front'],'back':phrase['back']})
    spec={**state['profile']['languages'][language],'word_target_default':min(30,len(potential))}
    return spec,bank


def _snapshot(conn,owner,language,spec,bank):
    from web_backend.self_study import normalise
    today=clock().date();day=today.isoformat()
    row=conn.execute('SELECT target,deadline FROM personal_study_word_goals WHERE owner_id=? AND language=?',(owner,language)).fetchone()
    default_date=min(spec.get('target_date') or '2036-12-31',(today+timedelta(days=28)).isoformat())
    target,deadline=(row['target'],row['deadline']) if row else (spec['word_target_default'],default_date)
    existing=conn.execute("SELECT answer FROM personal_study_cards WHERE owner_id=? AND language=? AND source!='error'",(owner,language)).fetchall()
    known={normalise(x['answer']) for x in existing};available=[(key,value) for key,value in bank.items() if key not in known]
    due=conn.execute('SELECT COUNT(*) FROM personal_study_cards WHERE owner_id=? AND language=? AND due_at<=?',(owner,language,clock().isoformat(timespec='seconds'))).fetchone()[0]
    recent=conn.execute('''SELECT r.correct FROM personal_study_reviews r JOIN personal_study_cards c ON c.id=r.card_id AND c.owner_id=r.owner_id
      WHERE r.owner_id=? AND c.language=? AND r.rating IS NOT NULL ORDER BY r.id DESC LIMIT 20''',(owner,language)).fetchall()
    days=max(1,(date.fromisoformat(deadline)-today).days) if deadline else 28
    remaining=max(0,target-len(known));capacity=max(1,min(10,spec['minutes']//3))
    proposed=min(capacity,max(1,math.ceil(remaining/days))) if remaining else 0
    reason='Порция рассчитана по цели, сроку и времени на этот язык.'
    if len(recent)>=5 and sum(x['correct'] for x in recent)/len(recent)<.6:
        proposed=min(proposed,1);reason='Пока много ошибок: добавляем меньше нового и закрепляем знакомое.'
    if due>=max(10,capacity*3):proposed=0;reason='Сначала разгрузим повторения. Новые слова сегодня можно не добавлять.'
    grant=conn.execute('SELECT card_ids FROM personal_study_word_days WHERE owner_id=? AND language=? AND day=?',(owner,language,day)).fetchone()
    ids=json.loads(grant[0]) if grant else []
    cards=[]
    for cid in ids:
        c=conn.execute('SELECT id,prompt,answer FROM personal_study_cards WHERE id=? AND owner_id=?',(cid,owner)).fetchone()
        if c:cards.append({'id':c['id'],'front':c['answer'],'back':c['prompt']})
    info={'language':language,'day':day,'target':target,'deadline':deadline,'in_deck':len(known),'due':due,
          'proposed':min(proposed,len(available),remaining),'available':len(available),'claimed':grant is not None,
          'added_today':len(ids),'cards':cards,'reason':reason,'capacity_per_day':capacity,
          'pace_exceeds_budget':remaining>capacity*days,'bank_shortfall':remaining>len(available),
          'note':'Количество в колоде не равно числу выученных слов и не подтверждает CEFR. Банк конечный; новые слова появляются после нажатия, без долгов за пропуски. Новый день — 00:00 UTC.'}
    return info,available


def status(owner,language):
    spec,bank=_context(owner,language);conn=connect()
    try:return _snapshot(conn,owner,language,spec,bank)[0]
    finally:conn.close()


def save_goal(owner,data):
    language=data.get('language');spec,bank=_context(owner,language)
    target=data.get('target');deadline=data.get('deadline','')
    if type(target) is not int or not 1<=target<=1000:raise ValueError('invalid_word_goal')
    if not isinstance(deadline,str):raise ValueError('invalid_word_goal')
    if deadline:
        try:parsed=date.fromisoformat(deadline)
        except ValueError:raise ValueError('invalid_word_goal') from None
        if not date(2026,1,1)<=parsed<=date(2036,12,31):raise ValueError('invalid_word_goal')
    conn=connect()
    try:
        conn.execute('INSERT INTO personal_study_word_goals VALUES(?,?,?,?) ON CONFLICT(owner_id,language) DO UPDATE SET target=excluded.target,deadline=excluded.deadline',(owner,language,target,deadline));conn.commit()
    finally:conn.close()
    return status(owner,language)


def start(owner,data):
    language=data.get('language');spec,bank=_context(owner,language);conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE');info,available=_snapshot(conn,owner,language,spec,bank)
        if info['claimed']:return info
        ids=[]
        for key,value in available[:info['proposed']]:
            c=conn.execute('''INSERT OR IGNORE INTO personal_study_cards
              (owner_id,language,lesson_id,source,source_key,prompt,answer,due_at)
              VALUES(?,?,?,'vocabulary',?,?,?,?)''',(owner,language,'vocab:'+language,key,value['back'],value['front'],clock().isoformat(timespec='seconds')))
            if c.rowcount:ids.append(c.lastrowid)
        # A zero-card visit does not consume the day's opportunity after a review.
        if ids:conn.execute('INSERT INTO personal_study_word_days VALUES(?,?,?,?)',(owner,language,info['day'],json.dumps(ids)))
        conn.commit();return _snapshot(conn,owner,language,spec,bank)[0]
    except Exception:conn.rollback();raise
    finally:conn.close()
