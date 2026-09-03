from __future__ import annotations
from datetime import datetime
import database


def initialize():
    conn=database.connect()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS crm_student_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        direction TEXT NOT NULL,
        sender_admin_id INTEGER,
        target TEXT NOT NULL DEFAULT 'STUDENT',
        body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'SENT',
        scheduled_for TEXT,
        created_at TEXT NOT NULL,
        sent_at TEXT,
        payment_method_id INTEGER,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_crm_msg_student ON crm_student_messages(student_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS student_pinned_notes(
        student_id INTEGER PRIMARY KEY,
        note TEXT NOT NULL,
        updated_by INTEGER,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS student_agreements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        valid_until TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_student_agreements ON student_agreements(student_id, active, created_at DESC);

    CREATE TABLE IF NOT EXISTS crm_settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_by INTEGER,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS billing_offers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        program_id INTEGER,
        minutes INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        discount_percent REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_by INTEGER,
        created_at TEXT NOT NULL,
        sent_at TEXT,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS crm_undo_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER,
        action_type TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        before_json TEXT,
        after_json TEXT,
        undo_sql TEXT,
        undo_params_json TEXT,
        status TEXT NOT NULL DEFAULT 'AVAILABLE',
        created_at TEXT NOT NULL,
        undone_at TEXT
    );
    ''')
    now=datetime.now().isoformat(timespec='seconds')
    # Backward-compatible columns for the messenger UX.
    cols={r['name'] for r in conn.execute('PRAGMA table_info(crm_student_messages)').fetchall()}
    for name,definition in [('inbox_id','INTEGER'),('delivered_at','TEXT'),('read_at','TEXT')]:
        if name not in cols:
            conn.execute(f'ALTER TABLE crm_student_messages ADD COLUMN {name} {definition}')
    offer_cols={r['name'] for r in conn.execute('PRAGMA table_info(billing_offers)').fetchall()}
    if 'payment_method_id' not in offer_cols:
        conn.execute('ALTER TABLE billing_offers ADD COLUMN payment_method_id INTEGER')

    defaults={'quiet_start':'22:00','quiet_end':'09:00','quiet_enabled':'1','reception_enabled':'1','reception_start':'09:00','reception_end':'21:00','reception_days':'0,1,2,3,4,5,6','urgent_enabled':'0'}
    for k,v in defaults.items():
        conn.execute('INSERT OR IGNORE INTO crm_settings(key,value,updated_at) VALUES(?,?,?)',(k,v,now))
    conn.commit();conn.close()
