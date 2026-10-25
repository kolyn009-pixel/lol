"""Shared learning records. Teacher drafts stay private until publication."""
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from database import connect


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def text(value, limit=4000, required=False):
    value=str(value or '').strip()
    if len(value)>limit: raise ValueError('text_too_long')
    if required and not value: raise ValueError('text_required')
    return value


def ensure_tables():
    conn=connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS learning_lesson_summaries (
          lesson_id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,topics TEXT NOT NULL,
          achievement TEXT,next_step TEXT,published INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_learning_summaries_user ON learning_lesson_summaries(user_id,published);
        CREATE TABLE IF NOT EXISTS learning_error_journal (
          id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,subject TEXT NOT NULL,
          topic TEXT NOT NULL,description TEXT NOT NULL,practice TEXT,
          status TEXT NOT NULL DEFAULT 'OPEN',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_learning_errors_user ON learning_error_journal(user_id,status);
        CREATE TABLE IF NOT EXISTS learning_study_plans (
          id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,subject TEXT NOT NULL,
          target TEXT NOT NULL,target_date TEXT,updated_at TEXT NOT NULL,
          UNIQUE(user_id,subject),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS learning_plan_steps (
          id INTEGER PRIMARY KEY AUTOINCREMENT,plan_id INTEGER NOT NULL,title TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'TODO',sort_order INTEGER NOT NULL,
          FOREIGN KEY(plan_id) REFERENCES learning_study_plans(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS learning_wait_requests (
          id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,subject TEXT NOT NULL,
          preferred_date TEXT NOT NULL,preferred_from TEXT NOT NULL,preferred_to TEXT NOT NULL,
          timezone TEXT NOT NULL,note TEXT,status TEXT NOT NULL DEFAULT 'ACTIVE',created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_learning_wait_user ON learning_wait_requests(user_id,status);
        CREATE TABLE IF NOT EXISTS learning_slot_offers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,request_id INTEGER NOT NULL,start_at TEXT NOT NULL,
          duration_minutes INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'OFFERED',created_at TEXT NOT NULL,
          UNIQUE(request_id,start_at),FOREIGN KEY(request_id) REFERENCES learning_wait_requests(id) ON DELETE CASCADE);
        ''')
        conn.commit()
    finally: conn.close()


def _user(conn, uid):
    row=conn.execute('SELECT id,name FROM users WHERE id=?',(int(uid),)).fetchone()
    if not row: raise PermissionError('student_not_found')
    return dict(row)


def _subject(value):
    value=text(value,40,True).upper()
    if value not in {'PHYSICS','CHEMISTRY','MATH'}: raise ValueError('invalid_subject')
    return value


def overview(user_id, teacher=False):
    ensure_tables();uid=int(user_id);conn=connect()
    try:
        student=_user(conn,uid)
        published='' if teacher else ' AND s.published=1'
        summaries=[dict(r) for r in conn.execute('''SELECT s.*,l.start_time FROM learning_lesson_summaries s
          JOIN lessons l ON l.id=s.lesson_id AND l.user_id=s.user_id
          WHERE s.user_id=?'''+published+' ORDER BY l.start_time DESC LIMIT 50',(uid,))]
        errors=[dict(r) for r in conn.execute('SELECT * FROM learning_error_journal WHERE user_id=? ORDER BY updated_at DESC,id DESC LIMIT 200',(uid,))]
        plans=[]
        for row in conn.execute('SELECT * FROM learning_study_plans WHERE user_id=? ORDER BY id',(uid,)):
            plan=dict(row);plan['steps']=[dict(r) for r in conn.execute('SELECT id,title,status FROM learning_plan_steps WHERE plan_id=? ORDER BY sort_order,id',(row['id'],))]
            count=len(plan['steps']);done=sum(x['status']=='DONE' for x in plan['steps'])
            plan['progress_percent']=round(done/count*100) if count else 0;plans.append(plan)
        waiting=[dict(r) for r in conn.execute("SELECT * FROM learning_wait_requests WHERE user_id=? AND status='ACTIVE' ORDER BY preferred_date,id",(uid,))]
        offers=[dict(r) for r in conn.execute('''SELECT o.*,w.subject,w.timezone FROM learning_slot_offers o
          JOIN learning_wait_requests w ON w.id=o.request_id WHERE w.user_id=?
          ORDER BY o.start_at DESC LIMIT 50''',(uid,))]
        lessons=[]
        if teacher:
            lessons=[dict(r) for r in conn.execute('SELECT id,start_time,lesson_status FROM lessons WHERE user_id=? ORDER BY start_time DESC LIMIT 50',(uid,))]
        return {'student':student,'summaries':summaries,'errors':errors,'plans':plans,'waiting':waiting,'offers':offers,'lessons':lessons}
    finally: conn.close()


def save_summary(uid, data):
    ensure_tables();uid=int(uid);lid=int(data.get('lesson_id'));topics=text(data.get('topics'),4000,True)
    achievement=text(data.get('achievement'));next_step=text(data.get('next_step'));published=data.get('published',False)
    if not isinstance(published,bool): raise ValueError('invalid_published')
    conn=connect()
    try:
        if not conn.execute('SELECT id FROM lessons WHERE id=? AND user_id=?',(lid,uid)).fetchone(): raise PermissionError('lesson_not_found')
        conn.execute('''INSERT INTO learning_lesson_summaries VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(lesson_id) DO UPDATE SET topics=excluded.topics,achievement=excluded.achievement,
          next_step=excluded.next_step,published=excluded.published,updated_at=excluded.updated_at''',
          (lid,uid,topics,achievement,next_step,int(published),stamp()));conn.commit()
        return {'status':'ok'}
    finally: conn.close()


def save_error(uid, data):
    ensure_tables();uid=int(uid);state=str(data.get('status') or 'OPEN').upper()
    if state not in {'OPEN','PRACTICING','RESOLVED'}: raise ValueError('invalid_status')
    subject=_subject(data.get('subject'));topic=text(data.get('topic'),200,True)
    description=text(data.get('description'),4000,True);practice=text(data.get('practice'));now=stamp();conn=connect()
    try:
        _user(conn,uid)
        if data.get('id'):
            changed=conn.execute('''UPDATE learning_error_journal SET subject=?,topic=?,description=?,practice=?,status=?,updated_at=?
              WHERE id=? AND user_id=?''',(subject,topic,description,practice,state,now,int(data['id']),uid)).rowcount
            if not changed: raise PermissionError('error_not_found')
        else:
            conn.execute('''INSERT INTO learning_error_journal(user_id,subject,topic,description,practice,status,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?)''',(uid,subject,topic,description,practice,state,now,now))
        conn.commit();return {'status':'ok'}
    finally: conn.close()


def save_plan(uid, data):
    ensure_tables();uid=int(uid);subject=_subject(data.get('subject'));target=text(data.get('target'),1000,True)
    target_date=text(data.get('target_date'),10) or None
    if target_date: date.fromisoformat(target_date)
    steps=data.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=50: raise ValueError('invalid_steps')
    values=[]
    for step in steps:
        if not isinstance(step,dict): raise ValueError('invalid_steps')
        title=text(step.get('title'),500,True);state=str(step.get('status') or 'TODO').upper()
        if state not in {'TODO','IN_PROGRESS','DONE'}: raise ValueError('invalid_status')
        values.append((title,state))
    conn=connect()
    try:
        _user(conn,uid)
        conn.execute('''INSERT INTO learning_study_plans(user_id,subject,target,target_date,updated_at) VALUES(?,?,?,?,?)
          ON CONFLICT(user_id,subject) DO UPDATE SET target=excluded.target,target_date=excluded.target_date,updated_at=excluded.updated_at''',(uid,subject,target,target_date,stamp()))
        pid=conn.execute('SELECT id FROM learning_study_plans WHERE user_id=? AND subject=?',(uid,subject)).fetchone()['id']
        conn.execute('DELETE FROM learning_plan_steps WHERE plan_id=?',(pid,))
        conn.executemany('INSERT INTO learning_plan_steps(plan_id,title,status,sort_order) VALUES(?,?,?,?)',[(pid,t,s,i) for i,(t,s) in enumerate(values)])
        conn.commit();return {'status':'ok','plan_id':pid}
    finally: conn.close()


def add_wait(uid, data):
    ensure_tables();uid=int(uid);subject=_subject(data.get('subject'));day=date.fromisoformat(str(data.get('preferred_date')))
    zone=ZoneInfo(str(data.get('timezone') or 'Europe/Moscow'))
    lo=datetime.strptime(str(data.get('preferred_from')),'%H:%M').strftime('%H:%M')
    hi=datetime.strptime(str(data.get('preferred_to')),'%H:%M').strftime('%H:%M')
    if lo>=hi or day<datetime.now(zone).date(): raise ValueError('invalid_time_window')
    if datetime.combine(day,datetime.strptime(hi,'%H:%M').time(),zone)<=datetime.now(zone): raise ValueError('invalid_time_window')
    note=text(data.get('note'),1000);conn=connect()
    try:
        _user(conn,uid)
        duplicate=conn.execute("SELECT id FROM learning_wait_requests WHERE user_id=? AND subject=? AND preferred_date=? AND preferred_from=? AND preferred_to=? AND timezone=? AND status='ACTIVE'",(uid,subject,day.isoformat(),lo,hi,zone.key)).fetchone()
        if duplicate:return {'status':'ok','id':duplicate['id']}
        cur=conn.execute('''INSERT INTO learning_wait_requests(user_id,subject,preferred_date,preferred_from,preferred_to,timezone,note,created_at)
          VALUES(?,?,?,?,?,?,?,?)''',(uid,subject,day.isoformat(),lo,hi,zone.key,note,stamp()));conn.commit()
        return {'status':'ok','id':cur.lastrowid}
    finally: conn.close()


def close_wait(uid, request_id):
    ensure_tables();conn=connect()
    try:
        rid=int(request_id)
        if not conn.execute('SELECT id FROM learning_wait_requests WHERE id=? AND user_id=?',(rid,int(uid))).fetchone(): raise PermissionError('request_not_found')
        conn.execute("UPDATE learning_wait_requests SET status='CLOSED' WHERE id=?",(rid,))
        conn.execute("UPDATE learning_slot_offers SET status='WITHDRAWN' WHERE request_id=? AND status IN ('OFFERED','ACCEPTED')",(rid,))
        conn.commit();return {'status':'ok'}
    finally: conn.close()


def _slot(start_at, duration):
    start=datetime.fromisoformat(str(start_at).replace('Z','+00:00'))
    if start.tzinfo is None: raise ValueError('timezone_required')
    duration=int(duration)
    if not 30<=duration<=180 or start<=datetime.now(timezone.utc) or start.second or start.microsecond: raise ValueError('invalid_slot')
    return start.astimezone(timezone.utc),duration


def _matches(row,start,duration):
    local=start.astimezone(ZoneInfo(row['timezone']));end=local+timedelta(minutes=duration)
    return local.date().isoformat()==row['preferred_date'] and end.date()==local.date() and row['preferred_from']<=local.strftime('%H:%M') and end.strftime('%H:%M')<=row['preferred_to']


def _assert_available(conn, start, duration):
    import database
    from web_backend.availability_guard import assert_available
    from core.lesson_time import lesson_timezone
    zone=lesson_timezone()
    local=start.astimezone(zone).replace(tzinfo=None);end=local+timedelta(minutes=duration)
    assert_available(local,end,conn=conn)
    for held in conn.execute("SELECT start_at,duration_minutes FROM learning_slot_offers WHERE status='ACCEPTED'"):
        held_start=datetime.fromisoformat(held['start_at']);held_end=held_start+timedelta(minutes=held['duration_minutes'])
        if held_start<start+timedelta(minutes=duration) and held_end>start:raise ValueError('slot_unavailable')
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='group_lessons'").fetchone():
        hit=conn.execute("SELECT 1 FROM group_lessons WHERE start_time<? AND end_time>? AND status NOT IN ('CANCELLED','QUORUM_FAILED','COMPLETED') LIMIT 1",(end.isoformat(),local.isoformat())).fetchone()
        if hit:raise ValueError('slot_unavailable')


def candidates(start_at, duration, subject):
    ensure_tables();start,duration=_slot(start_at,duration);subject=_subject(subject);conn=connect()
    try:
        _assert_available(conn,start,duration)
        rows=conn.execute("SELECT w.*,u.name FROM learning_wait_requests w JOIN users u ON u.id=w.user_id WHERE w.status='ACTIVE' AND w.subject=? ORDER BY w.created_at,w.id",(subject,)).fetchall()
        return [dict(r) for r in rows if _matches(r,start,duration)]
    finally: conn.close()


def waiting_overview():
    ensure_tables();conn=connect()
    try:
        rows=[dict(r) for r in conn.execute("SELECT w.*,u.name FROM learning_wait_requests w JOIN users u ON u.id=w.user_id WHERE w.status='ACTIVE' ORDER BY w.preferred_date,w.created_at LIMIT 300")]
        for row in rows:
            row['offers']=[dict(r) for r in conn.execute('SELECT id,start_at,duration_minutes,status FROM learning_slot_offers WHERE request_id=? ORDER BY id DESC',(row['id'],))]
        return rows
    finally: conn.close()


def offer(request_id, start_at, duration):
    ensure_tables();start,duration=_slot(start_at,duration);conn=connect();rid=int(request_id)
    try:
        row=conn.execute("SELECT * FROM learning_wait_requests WHERE id=? AND status='ACTIVE'",(rid,)).fetchone()
        if not row: raise PermissionError('request_not_found')
        if not _matches(row,start,duration): raise ValueError('slot_outside_preferences')
        _assert_available(conn,start,duration)
        inserted=conn.execute('''INSERT INTO learning_slot_offers(request_id,start_at,duration_minutes,created_at) VALUES(?,?,?,?)
          ON CONFLICT(request_id,start_at) DO NOTHING''',(rid,start.isoformat(timespec='seconds'),duration,stamp()))
        conn.commit()
        if inserted.rowcount:
            try:
                from web_backend import push_events
                push_events.student_and_parents(int(row['user_id']),'Есть свободное окно для занятия','Откройте учебный план и проверьте предложенное время.','/app/?tab=profile','/app/parent/',f'learning-offer-{rid}-{start.isoformat()}',{'type':'schedule'})
            except Exception:pass
        return {'status':'ok'}
    finally: conn.close()


def respond_offer(uid, offer_id, response):
    if response not in {'ACCEPTED','DECLINED'}: raise ValueError('invalid_response')
    ensure_tables();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('''SELECT o.*,w.status AS request_status FROM learning_slot_offers o JOIN learning_wait_requests w ON w.id=o.request_id
          WHERE o.id=? AND w.user_id=?''',(int(offer_id),int(uid))).fetchone()
        if not row: raise PermissionError('offer_not_found')
        if row['status']==response:return {'status':'ok'}
        if row['status']!='OFFERED' or row['request_status']!='ACTIVE' or datetime.fromisoformat(row['start_at'])<=datetime.now(timezone.utc):raise ValueError('offer_unavailable')
        if response=='ACCEPTED':_assert_available(conn,datetime.fromisoformat(row['start_at']),row['duration_minutes'])
        conn.execute("UPDATE learning_slot_offers SET status=? WHERE id=? AND status='OFFERED'",(response,int(offer_id)))
        if response=='ACCEPTED':
            start=datetime.fromisoformat(row['start_at']);end=start+timedelta(minutes=row['duration_minutes'])
            for other in conn.execute("SELECT id,start_at,duration_minutes FROM learning_slot_offers WHERE status='OFFERED'").fetchall():
                os=datetime.fromisoformat(other['start_at'])
                if os<end and os+timedelta(minutes=other['duration_minutes'])>start:conn.execute("UPDATE learning_slot_offers SET status='WITHDRAWN' WHERE id=?",(other['id'],))
        conn.commit();return {'status':'ok','booking':'teacher_confirmation_required'}
    finally: conn.close()


def material_search(uid, query):
    from web_backend.library import list_materials
    rows=list_materials(user_id=uid,search=text(query,200),limit=100)
    return [{'id':r['id'],'title':r['title'],'description':r.get('description'),'subject':r.get('subject'),
             'url':'/api/'+('teacher' if uid is None else 'student')+'/material/file?id='+str(r['id'])} for r in rows]


# BEGIN ADELIA FIRST LESSON PLAN 20261025
_overview_without_first_visit = overview
def overview(user_id, teacher=False):
    result = _overview_without_first_visit(user_id, teacher=teacher)
    if teacher:
        from web_backend.first_lesson_context import first_visit
        result['first_visit'] = first_visit(user_id)
    return result
# END ADELIA FIRST LESSON PLAN 20261025
