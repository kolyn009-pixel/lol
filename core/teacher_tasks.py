from __future__ import annotations
from datetime import datetime, timedelta
import database

def initialize():
    c = database.connect()
    c.execute("""CREATE TABLE IF NOT EXISTS teacher_tasks(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      user_id INTEGER,
      due_at TEXT,
      status TEXT NOT NULL DEFAULT 'OPEN',
      priority INTEGER NOT NULL DEFAULT 2,
      source_type TEXT DEFAULT 'MANUAL',
      source_key TEXT,
      notes TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_teacher_task_source ON teacher_tasks(source_key) WHERE source_key IS NOT NULL")
    c.execute("CREATE INDEX IF NOT EXISTS idx_teacher_task_status_due ON teacher_tasks(status,due_at,priority)")
    c.commit(); c.close()

def add(title, user_id=None, due_at=None, priority=2, notes='', source_type='MANUAL', source_key=None):
    initialize(); now = datetime.now().isoformat(timespec='seconds'); c = database.connect()
    if source_key:
        row=c.execute("SELECT id FROM teacher_tasks WHERE source_key=?",(source_key,)).fetchone()
        if row:
            c.execute("UPDATE teacher_tasks SET title=?,user_id=?,due_at=?,status='OPEN',priority=?,source_type=?,notes=?,updated_at=? WHERE id=?",
                      (title,user_id,due_at,int(priority),source_type,notes,now,row['id']))
        else:
            c.execute("INSERT INTO teacher_tasks(title,user_id,due_at,status,priority,source_type,source_key,notes,created_at,updated_at) VALUES(?,?,?,'OPEN',?,?,?,?,?,?)",
                      (title,user_id,due_at,int(priority),source_type,source_key,notes,now,now))
    else:
        c.execute("INSERT INTO teacher_tasks(title,user_id,due_at,status,priority,source_type,source_key,notes,created_at,updated_at) VALUES(?,?,?,'OPEN',?,?,?,?,?,?)",
                  (title,user_id,due_at,int(priority),source_type,None,notes,now,now))
    c.commit(); c.close()

def list_open(limit=50):
    initialize(); c = database.connect()
    rows = c.execute("""SELECT t.*,u.name user_name FROM teacher_tasks t LEFT JOIN users u ON u.id=t.user_id
        WHERE t.status IN ('OPEN','DEFERRED') AND (t.due_at IS NULL OR datetime(t.due_at)<=datetime('now','+7 days'))
        ORDER BY CASE t.status WHEN 'OPEN' THEN 0 ELSE 1 END, t.priority ASC, COALESCE(t.due_at,'9999'), t.id DESC LIMIT ?""", (int(limit),)).fetchall()
    c.close(); return rows

def get(task_id):
    initialize(); c = database.connect(); r = c.execute("SELECT t.*,u.name user_name FROM teacher_tasks t LEFT JOIN users u ON u.id=t.user_id WHERE t.id=?", (int(task_id),)).fetchone(); c.close(); return r

def set_status(task_id, status, due_at=None):
    initialize(); c = database.connect(); c.execute("UPDATE teacher_tasks SET status=?,due_at=COALESCE(?,due_at),updated_at=? WHERE id=?", (status,due_at,datetime.now().isoformat(timespec='seconds'),int(task_id))); c.commit(); c.close()

def defer(task_id, hours=24):
    set_status(task_id, 'DEFERRED', (datetime.now()+timedelta(hours=hours)).isoformat(timespec='seconds'))

def sync_auto():
    """Maintain non-homework CRM auto tasks.

    Missed homework is intentionally excluded here: homework_watchdog owns both
    individual and group deadlines, submission reconciliation and reminders.
    """
    initialize(); c = database.connect(); now = datetime.now().isoformat(timespec='seconds'); live_keys=set()
    def upsert_auto(key,title,user_id,priority):
        live_keys.add(key)
        row=c.execute("SELECT id FROM teacher_tasks WHERE source_key=?",(key,)).fetchone()
        if row:
            c.execute("UPDATE teacher_tasks SET title=?,user_id=?,status='OPEN',priority=?,updated_at=? WHERE id=?",(title,user_id,priority,now,row['id']))
        else:
            c.execute("INSERT INTO teacher_tasks(title,user_id,status,priority,source_type,source_key,created_at,updated_at) VALUES(?,?,'OPEN',?,'AUTO',?,?,?)",(title,user_id,priority,key,now,now))
    try:
        rows = c.execute("SELECT l.id,l.user_id,u.name FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.lesson_status IN ('CONFIRMED','COMPLETED','FINISHED') AND l.payment_status IN ('AWAITING_PAYMENT','UNPAID')").fetchall()
        for r in rows: upsert_auto(f"unpaid:{r['id']}",f"Проверить оплату — {r['name']}",r['user_id'],1)
    except Exception: pass
    try:
        rows = c.execute("SELECT u.id,u.name FROM users u WHERE u.active=1 AND NOT EXISTS (SELECT 1 FROM lessons l WHERE l.user_id=u.id AND l.lesson_status!='CANCELLED' AND datetime(l.start_time)>=datetime('now'))").fetchall()
        for r in rows: upsert_auto(f"no_next:{r['id']}",f"Нет следующего занятия — {r['name']}",r['id'],2)
    except Exception: pass
    stale=c.execute("SELECT id,source_key FROM teacher_tasks WHERE source_type='AUTO' AND status IN ('OPEN','DEFERRED')").fetchall()
    for row in stale:
        if row['source_key'] and row['source_key'] not in live_keys:
            c.execute("UPDATE teacher_tasks SET status='DONE',updated_at=? WHERE id=?",(now,row['id']))
    c.commit(); c.close()
