"""Private curriculum progress. Passing a programme block never awards CEFR."""
from datetime import datetime,timezone
import json,re
from uuid import UUID
from database import connect
from learning.language_routes import BANDS,stages,challenge


def ensure_schema():
    conn=connect()
    try:
        conn.executescript('''CREATE TABLE IF NOT EXISTS personal_study_routes(
          owner_id INTEGER NOT NULL,language TEXT NOT NULL,start_band TEXT NOT NULL,updated_at TEXT NOT NULL,
          PRIMARY KEY(owner_id,language));
          CREATE TABLE IF NOT EXISTS personal_study_route_checks(
          id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,language TEXT NOT NULL,band TEXT NOT NULL,
          request_id TEXT NOT NULL,answers TEXT NOT NULL,correct INTEGER NOT NULL,total INTEGER NOT NULL,
          feedback TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(owner_id,request_id));''');conn.commit()
    finally:conn.close()


def starting_band(owner,language,p):
    from web_backend.self_study_placement import result
    cfg=p.get('preferences') or {};declared=cfg.get('levels',{}).get(language)
    measured=result(owner,language)
    if measured:
        level=measured['working_band']
        if level=='B2' and declared=='C1':level='C1'
    else:
        level=declared
        if level in (None,'unknown'):
            match=re.search(r'\b(A[012]|B[12]|C1)\b',p['languages'][language].get('start',''))
            level=match.group(1) if match else 'A1'
    return level if level in BANDS else 'A1'


def activate(owner,language,recalibrate=False):
    from web_backend.self_study import profile
    p=profile(owner)
    if language not in p['languages']:raise ValueError('invalid_language')
    band=starting_band(owner,language,p);ensure_schema();conn=connect()
    try:
        sql=('INSERT INTO personal_study_routes VALUES(?,?,?,?) ON CONFLICT(owner_id,language) DO UPDATE SET start_band=excluded.start_band,updated_at=excluded.updated_at'
             if recalibrate else 'INSERT OR IGNORE INTO personal_study_routes VALUES(?,?,?,?)')
        conn.execute(sql,(owner,language,band,datetime.now(timezone.utc).isoformat()));conn.commit()
    finally:conn.close()
    return view(owner,language)


def state(owner,language,p,attempts):
    ensure_schema();conn=connect()
    try:
        enrollment=conn.execute('SELECT start_band FROM personal_study_routes WHERE owner_id=? AND language=?',(owner,language)).fetchone()
        checks=[dict(r) for r in conn.execute('SELECT id,band,correct,total,created_at FROM personal_study_route_checks WHERE owner_id=? AND language=? ORDER BY id',(owner,language))]
    finally:conn.close()
    start=enrollment['start_band'] if enrollment else starting_band(owner,language,p)
    start_at=BANDS.index(start);nodes=stages(language);unlocked=True;next_action='complete';next_lesson=None;current_band=None
    for index,node in enumerate(nodes):
        records=[x for x in checks if x['band']==node['band']]
        node['first_check']=records[0] if records else None;node['latest_check']=records[-1] if records else None
        node['checked']=any(r['correct']/r['total']>=.75 for r in records)
        for item in node['lessons']:
            history=[r for r in attempts if r['lesson_id']==item['id']]
            item['passed']=bool(history and history[-1]['correct']/history[-1]['total']>=.75)
        node['completed_lessons']=sum(x['passed'] for x in node['lessons'])
        if index<start_at:node['status']='review'
        elif not unlocked:node['status']='locked'
        elif not node['lessons']:node['status']='materials_needed';unlocked=False
        elif node['completed_lessons']<len(node['lessons']):node['status']='learning';unlocked=False
        elif not node['checked']:node['status']='check_ready';unlocked=False
        else:node['status']='complete'
        if index>=start_at and current_band is None and node['status']!='complete':
            current_band=node['band'];next_action={'learning':'lesson','check_ready':'check','materials_needed':'materials_needed','locked':'materials_needed'}[node['status']]
            next_lesson=next((x['id'] for x in node['lessons'] if not x['passed']),None)
    return {'language':language,'enabled':bool(enrollment),'start_band':start,'current_band':current_band,
            'next_action':next_action,'next_lesson':next_lesson,'stages':nodes,
            'note':'Ступени обозначают учебные задачи. Пройденный блок и переход по новому тексту не подтверждают CEFR: аудирование, речь и письмо ещё требуют отдельных проверок. Нижние ступени доступны для повторения.'}


def view(owner,language):
    from web_backend.self_study import profile,ensure_schema as core
    p=profile(owner)
    if language not in p['languages']:raise ValueError('invalid_language')
    core();conn=connect()
    try:attempts=[dict(r) for r in conn.execute('SELECT lesson_id,correct,total FROM personal_study_attempts WHERE owner_id=? ORDER BY id',(owner,))]
    finally:conn.close()
    return state(owner,language,p,attempts)


def course(route):
    start=BANDS.index(route['start_band'])
    return [{**item,'number':i+1} for i,item in enumerate(item for node in route['stages'][start:] for item in node['lessons'])]


def get_check(owner,language,band):
    route=view(owner,language)
    node=next((x for x in route['stages'] if x['band']==band),None)
    if not route['enabled'] or not node or node['status'] not in ('check_ready','complete'):raise ValueError('route_check_locked')
    out=challenge(language,band);out['fresh']=node['first_check'] is None
    out['previous']=node['latest_check'];return out


def submit_check(owner,data):
    from web_backend.self_study import normalise
    language,band,request_id=data.get('language'),data.get('band'),data.get('request_id');answers=data.get('answers')
    try:
        if not isinstance(request_id,str):raise ValueError()
        UUID(request_id)
    except (ValueError,AttributeError):raise ValueError('invalid_request_id') from None
    task=challenge(language,band,True)
    if not isinstance(answers,dict) or set(answers)!={q['id'] for q in task['checks']}:raise ValueError('answer_all_questions')
    if any(not isinstance(v,str) or not v.strip() or len(v)>1000 for v in answers.values()):raise ValueError('invalid_answers')
    clean={k:v.strip() for k,v in answers.items()};ensure_schema();conn=connect()
    try:
        previous=conn.execute('SELECT * FROM personal_study_route_checks WHERE owner_id=? AND request_id=?',(owner,request_id)).fetchone()
        if previous:
            if previous['language']!=language or previous['band']!=band or json.loads(previous['answers'])!=clean:raise ValueError('request_conflict')
            return json.loads(previous['feedback'])
    finally:conn.close()
    get_check(owner,language,band)  # validates selected course and prerequisites
    conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        previous=conn.execute('SELECT * FROM personal_study_route_checks WHERE owner_id=? AND request_id=?',(owner,request_id)).fetchone()
        if previous:
            if previous['language']!=language or previous['band']!=band or json.loads(previous['answers'])!=clean:raise ValueError('request_conflict')
            return json.loads(previous['feedback'])
        fresh=not conn.execute('SELECT 1 FROM personal_study_route_checks WHERE owner_id=? AND language=? AND band=?',(owner,language,band)).fetchone()
        results=[{'id':q['id'],'prompt':q['prompt'],'submitted':clean[q['id']], 'expected':q['answers'][0],
                  'correct':normalise(clean[q['id']]) in {normalise(a) for a in q['answers']}} for q in task['checks']]
        score=sum(x['correct'] for x in results)
        output={'language':language,'band':band,'correct':score,'total':len(results),'passed':score/len(results)>=.75,'fresh':fresh,'results':results,
                'note':'Результат нового текста внутри программы.' if fresh else 'Повтор знакомого текста: тренировка, не независимый рост.'}
        conn.execute('INSERT INTO personal_study_route_checks(owner_id,language,band,request_id,answers,correct,total,feedback,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
          (owner,language,band,request_id,json.dumps(clean),score,len(results),json.dumps(output,ensure_ascii=False),datetime.now(timezone.utc).isoformat()));conn.commit()
        return output
    except Exception:conn.rollback();raise
    finally:conn.close()
