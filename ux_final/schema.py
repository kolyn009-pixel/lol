from __future__ import annotations
from datetime import datetime
import database

DEFAULT_FAVORITES = ['inbox','messages','today','search','students','book','stats']

def initialize():
    conn=database.connect()
    conn.execute('''CREATE TABLE IF NOT EXISTS admin_favorites(
      admin_id INTEGER NOT NULL,
      action_code TEXT NOT NULL,
      position INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      PRIMARY KEY(admin_id,action_code)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS admin_recent_students(
      admin_id INTEGER NOT NULL, student_id INTEGER NOT NULL, opened_at TEXT NOT NULL,
      PRIMARY KEY(admin_id,student_id)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS admin_pinned_students(
      admin_id INTEGER NOT NULL, student_id INTEGER NOT NULL, created_at TEXT NOT NULL,
      PRIMARY KEY(admin_id,student_id)
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_admin_recent_opened ON admin_recent_students(admin_id,opened_at DESC)')
    conn.commit(); conn.close()

def ensure_defaults(admin_id:int):
    initialize(); conn=database.connect()
    try:
        n=conn.execute('SELECT COUNT(*) FROM admin_favorites WHERE admin_id=?',(int(admin_id),)).fetchone()[0]
        if not n:
            now=datetime.now().isoformat(timespec='seconds')
            for pos,code in enumerate(DEFAULT_FAVORITES):
                conn.execute('INSERT OR IGNORE INTO admin_favorites(admin_id,action_code,position,created_at) VALUES(?,?,?,?)',(int(admin_id),code,pos,now))
            conn.commit()
    finally: conn.close()
