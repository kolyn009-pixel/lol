"""Tracked external-homework flow for sites such as RESHU EGE / RESHU OGE.

The website tracks when a student opens an assigned external variant through our
redirect, can later ask whether it is completed, and records the student's
answer. Completion events are exposed to the teacher inbox with the original
variant URL. We do not claim access to third-party result data unless a supported
API is configured separately.
"""
from urllib.parse import urlparse
from database import connect, now_iso

SUPPORTED_PROVIDERS={
    'reshuege.ru':'RESHU_EGE',
    'math.reshuege.ru':'RESHU_EGE',
    'phys-ege.sdamgia.ru':'RESHU_EGE',
    'chem-ege.sdamgia.ru':'RESHU_EGE',
    'reshuoge.ru':'RESHU_OGE',
    'math-oge.sdamgia.ru':'RESHU_OGE',
    'phys-oge.sdamgia.ru':'RESHU_OGE',
    'chem-oge.sdamgia.ru':'RESHU_OGE',
}


def ensure_tables():
    conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS external_homework_links(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      homework_id INTEGER NOT NULL,
      provider TEXT NOT NULL DEFAULT 'EXTERNAL',
      external_url TEXT NOT NULL,
      title TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(homework_id),
      FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS external_homework_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      homework_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      event_type TEXT NOT NULL,
      source_channel TEXT NOT NULL DEFAULT 'WEB',
      created_at TEXT NOT NULL,
      metadata_json TEXT,
      FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS external_homework_state(
      homework_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      first_opened_at TEXT,
      last_opened_at TEXT,
      reminder_due_at TEXT,
      reminder_sent_at TEXT,
      student_status TEXT,
      student_status_at TEXT,
      teacher_notified_at TEXT,
      PRIMARY KEY(homework_id,user_id),
      FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_ext_hw_reminder ON external_homework_state(reminder_due_at,reminder_sent_at,student_status);
    """);conn.commit();conn.close()


def detect_provider(url):
    host=(urlparse(str(url or '')).hostname or '').lower()
    return SUPPORTED_PROVIDERS.get(host,'EXTERNAL')


def attach_external_link(homework_id,url,title=None):
    ensure_tables();provider=detect_provider(url);conn=connect();conn.execute("""INSERT INTO external_homework_links(homework_id,provider,external_url,title,created_at) VALUES(?,?,?,?,?) ON CONFLICT(homework_id) DO UPDATE SET provider=excluded.provider,external_url=excluded.external_url,title=excluded.title""",(int(homework_id),provider,str(url).strip(),str(title or '').strip() or None,now_iso()));conn.commit();conn.close();return {'status':'ok','provider':provider}


def get_external_link(homework_id):
    ensure_tables();conn=connect();row=conn.execute("SELECT * FROM external_homework_links WHERE homework_id=?",(int(homework_id),)).fetchone();conn.close();return dict(row) if row else None


def mark_opened(homework_id,user_id,reminder_due_at=None,source_channel='WEB'):
    ensure_tables();now=now_iso();conn=connect();link=conn.execute("SELECT 1 FROM external_homework_links WHERE homework_id=?",(int(homework_id),)).fetchone();owner=conn.execute("SELECT 1 FROM homework WHERE id=? AND user_id=?",(int(homework_id),int(user_id))).fetchone()
    if not link or not owner:conn.close();raise PermissionError('homework_not_found')
    conn.execute("INSERT INTO external_homework_events(homework_id,user_id,event_type,source_channel,created_at) VALUES(?,?,?,?,?)",(int(homework_id),int(user_id),'OPENED',str(source_channel or 'WEB').upper(),now))
    conn.execute("""INSERT INTO external_homework_state(homework_id,user_id,first_opened_at,last_opened_at,reminder_due_at) VALUES(?,?,?,?,?) ON CONFLICT(homework_id,user_id) DO UPDATE SET last_opened_at=excluded.last_opened_at,reminder_due_at=COALESCE(excluded.reminder_due_at,external_homework_state.reminder_due_at)""",(int(homework_id),int(user_id),now,now,reminder_due_at));conn.commit();conn.close();return {'status':'ok','opened_at':now}


def set_student_status(homework_id,user_id,status,source_channel='WEB'):
    ensure_tables();status=str(status or '').upper()
    if status not in {'DONE','WORKING','NEED_MORE_TIME'}:raise ValueError('invalid_status')
    now=now_iso();conn=connect();owner=conn.execute("SELECT 1 FROM homework WHERE id=? AND user_id=?",(int(homework_id),int(user_id))).fetchone()
    if not owner:conn.close();raise PermissionError('homework_not_found')
    conn.execute("""INSERT INTO external_homework_state(homework_id,user_id,student_status,student_status_at) VALUES(?,?,?,?) ON CONFLICT(homework_id,user_id) DO UPDATE SET student_status=excluded.student_status,student_status_at=excluded.student_status_at""",(int(homework_id),int(user_id),status,now))
    conn.execute("INSERT INTO external_homework_events(homework_id,user_id,event_type,source_channel,created_at) VALUES(?,?,?,?,?)",(int(homework_id),int(user_id),'STATUS_'+status,str(source_channel or 'WEB').upper(),now));conn.commit();conn.close();return {'status':'ok','student_status':status,'updated_at':now}


def reminders_due(now=None,limit=100):
    ensure_tables();now=now or now_iso();conn=connect();rows=conn.execute("""SELECT s.*,h.title,h.deadline,l.provider,l.external_url,u.name,u.telegram_id,u.max_user_id FROM external_homework_state s JOIN homework h ON h.id=s.homework_id JOIN external_homework_links l ON l.homework_id=s.homework_id JOIN users u ON u.id=s.user_id WHERE s.first_opened_at IS NOT NULL AND s.student_status IS NULL AND s.reminder_due_at IS NOT NULL AND s.reminder_due_at<=? AND s.reminder_sent_at IS NULL ORDER BY s.reminder_due_at LIMIT ?""",(str(now),int(limit))).fetchall();conn.close();return [dict(r) for r in rows]


def mark_reminder_sent(homework_id,user_id):
    ensure_tables();conn=connect();conn.execute("UPDATE external_homework_state SET reminder_sent_at=? WHERE homework_id=? AND user_id=?",(now_iso(),int(homework_id),int(user_id)));conn.commit();conn.close()


def teacher_completion_feed(limit=100):
    ensure_tables();conn=connect();rows=conn.execute("""SELECT s.homework_id,s.user_id,s.student_status,s.student_status_at,s.teacher_notified_at,h.title,h.deadline,l.provider,l.external_url,u.name FROM external_homework_state s JOIN homework h ON h.id=s.homework_id JOIN external_homework_links l ON l.homework_id=s.homework_id JOIN users u ON u.id=s.user_id WHERE s.student_status IS NOT NULL ORDER BY datetime(s.student_status_at) DESC LIMIT ?""",(int(limit),)).fetchall();conn.close();return [dict(r) for r in rows]
