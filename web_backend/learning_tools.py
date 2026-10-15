"""Small learning workflows using existing identity and notification services."""
from datetime import datetime,timedelta
import database
from core.lesson_time import lesson_timezone

def ensure_tables():
    c=database.connect()
    try:
        c.executescript('''CREATE TABLE IF NOT EXISTS learning_lesson_topics(lesson_id INTEGER PRIMARY KEY,topic TEXT NOT NULL DEFAULT '',formula_id INTEGER,FOREIGN KEY(lesson_id) REFERENCES lessons(id));
        CREATE TABLE IF NOT EXISTS learning_help_requests(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,homework_id INTEGER,formula_id INTEGER,topic TEXT NOT NULL DEFAULT '',question TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'OPEN',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE INDEX IF NOT EXISTS idx_learning_help_user ON learning_help_requests(user_id,status);
        ''');c.commit()
    finally:c.close()

def request_help(uid,data):
    uid=int(uid);question=str(data.get('question') or '').strip();topic=str(data.get('topic') or '').strip()
    if not 3<=len(question)<=2000 or len(topic)>180:raise ValueError('invalid_question')
    hid=int(data['homework_id']) if data.get('homework_id') else None;fid=int(data['formula_id']) if data.get('formula_id') else None
    if hid:
        from web_backend import student_homework
        
        if not student_homework.detail(hid,uid):raise PermissionError('homework_not_found')
    if fid:
        from web_backend.formula_book import formula_detail
        if not formula_detail(fid,uid):raise ValueError('formula_not_found')
    ensure_tables();c=database.connect();now=datetime.now(lesson_timezone()).isoformat(timespec='seconds')
    try:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT id FROM learning_help_requests WHERE user_id=? AND COALESCE(homework_id,0)=? AND COALESCE(formula_id,0)=? AND question=? AND status='OPEN'",(uid,hid or 0,fid or 0,question)).fetchone()
        if row:return {'status':'ok','id':int(row['id']),'already_sent':True}
        cur=c.execute('INSERT INTO learning_help_requests(user_id,homework_id,formula_id,topic,question,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(uid,hid,fid,topic,question,now,now));rid=int(cur.lastrowid);c.commit()
    finally:c.close()
    try:
        from web_backend import push_events
        push_events.teachers('Ученику нужна помощь','Откройте вопросы по заданиям и формулам.','/teacher/',f'learning-help-{rid}',{'type':'homework','help_id':rid})
    except Exception:pass
    return {'status':'ok','id':rid,'already_sent':False}

def list_help(uid=None):
    ensure_tables();c=database.connect()
    try:
        if uid is None:return [dict(r) for r in c.execute("SELECT h.*,u.name FROM learning_help_requests h JOIN users u ON u.id=h.user_id WHERE h.status='OPEN' ORDER BY h.created_at LIMIT 200")]
        return [dict(r) for r in c.execute('SELECT * FROM learning_help_requests WHERE user_id=? ORDER BY id DESC LIMIT 50',(int(uid),))]
    finally:c.close()

def close_help(request_id):
    ensure_tables();c=database.connect()
    try:c.execute("UPDATE learning_help_requests SET status='RESOLVED',updated_at=? WHERE id=?",(database.now_iso(),int(request_id)));c.commit();return {'status':'ok'}
    finally:c.close()

def week_summary():
    from web_backend.teacher_portal import dashboard
    d=dashboard();from web_backend import finance_reporting
    week=d.get('week') or {}
    finance=finance_reporting.dashboard(start=week['start'],end=week['end']) if week.get('start') and week.get('end') else finance_reporting.dashboard(period='week')
    return {'finance':{'paid':finance['paid'],'lessons':finance['lessons']},'week':d.get('week',{}),'stats':d.get('stats',{}),'pending_reviews':len(d.get('pending_reviews') or []),'help_waiting':len(list_help())}
