from datetime import datetime
import database


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def ensure_schema():
    conn = database.connect()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS admin_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL UNIQUE,
        display_name TEXT,
        role TEXT NOT NULL DEFAULT 'ADMIN',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        created_by INTEGER,
        last_seen_at TEXT
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_telegram_id INTEGER,
        actor_role TEXT,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
    CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);

    CREATE TABLE IF NOT EXISTS financial_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER NOT NULL DEFAULT 0,
        lessons_delta INTEGER NOT NULL DEFAULT 0,
        nominal INTEGER NOT NULL DEFAULT 0,
        entry_type TEXT NOT NULL,
        source_type TEXT,
        source_id TEXT,
        external_key TEXT UNIQUE,
        description TEXT,
        actor_telegram_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ledger_created ON financial_ledger(created_at);
    CREATE INDEX IF NOT EXISTS idx_ledger_user ON financial_ledger(user_id);

    CREATE TRIGGER IF NOT EXISTS financial_ledger_no_update
    BEFORE UPDATE ON financial_ledger
    WHEN NOT (
        OLD.user_id IS NOT NULL
        AND NEW.user_id IS NULL
        AND NEW.id IS OLD.id
        AND NEW.amount IS OLD.amount
        AND NEW.lessons_delta IS OLD.lessons_delta
        AND NEW.nominal IS OLD.nominal
        AND NEW.entry_type IS OLD.entry_type
        AND NEW.source_type IS OLD.source_type
        AND NEW.source_id IS OLD.source_id
        AND NEW.external_key IS OLD.external_key
        AND NEW.description IS OLD.description
        AND NEW.actor_telegram_id IS OLD.actor_telegram_id
        AND NEW.created_at IS OLD.created_at
    )
    BEGIN
      SELECT RAISE(ABORT, 'financial_ledger is immutable');
    END;
    CREATE TRIGGER IF NOT EXISTS financial_ledger_no_delete
    BEFORE DELETE ON financial_ledger
    BEGIN
      SELECT RAISE(ABORT, 'financial_ledger is immutable');
    END;

    CREATE TABLE IF NOT EXISTS admin_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        priority TEXT NOT NULL DEFAULT 'INFO',
        title TEXT NOT NULL,
        body TEXT,
        entity_type TEXT,
        entity_id TEXT,
        dedupe_key TEXT UNIQUE,
        status TEXT NOT NULL DEFAULT 'OPEN',
        created_at TEXT NOT NULL,
        resolved_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_admin_events_status ON admin_events(status, priority, created_at);

    CREATE TABLE IF NOT EXISTS system_backups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL,
        created_by INTEGER,
        size_bytes INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'OK'
    );

    CREATE TABLE IF NOT EXISTS system_diagnostics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_name TEXT NOT NULL,
        severity TEXT NOT NULL,
        ok INTEGER NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()
