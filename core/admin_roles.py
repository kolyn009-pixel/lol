from datetime import datetime
import database
from .schema import ensure_schema

OWNER_ID = None


def initialize(owner_id: int):
    global OWNER_ID
    OWNER_ID = int(owner_id)
    ensure_schema()
    conn = database.connect()
    conn.execute("""
        INSERT OR IGNORE INTO admin_accounts
        (telegram_id, display_name, role, active, created_at, created_by)
        VALUES (?, ?, 'OWNER', 1, ?, ?)
    """, (OWNER_ID, "Владелец", datetime.now().isoformat(timespec="seconds"), OWNER_ID))
    conn.execute("UPDATE admin_accounts SET role='OWNER', active=1 WHERE telegram_id=?", (OWNER_ID,))
    conn.commit(); conn.close()


def is_owner(telegram_id):
    return telegram_id is not None and OWNER_ID is not None and int(telegram_id) == OWNER_ID


def is_admin_id(telegram_id):
    if telegram_id is None:
        return False
    if is_owner(telegram_id):
        return True
    ensure_schema()
    conn = database.connect()
    row = conn.execute("SELECT 1 FROM admin_accounts WHERE telegram_id=? AND active=1", (int(telegram_id),)).fetchone()
    conn.close()
    return bool(row)


def role_for(telegram_id):
    if is_owner(telegram_id):
        return "OWNER"
    conn = database.connect()
    row = conn.execute("SELECT role FROM admin_accounts WHERE telegram_id=? AND active=1", (int(telegram_id),)).fetchone()
    conn.close()
    return row["role"] if row else None


def touch(telegram_id):
    if telegram_id is None: return
    conn = database.connect()
    conn.execute("UPDATE admin_accounts SET last_seen_at=? WHERE telegram_id=?", (datetime.now().isoformat(timespec="seconds"), int(telegram_id)))
    conn.commit(); conn.close()


def list_admins():
    conn = database.connect()
    rows = conn.execute("SELECT * FROM admin_accounts WHERE active=1 ORDER BY CASE role WHEN 'OWNER' THEN 0 ELSE 1 END, created_at").fetchall()
    conn.close(); return [dict(r) for r in rows]


def add_admin(telegram_id, display_name, actor_id):
    if not is_owner(actor_id):
        raise PermissionError("Only owner can add administrators")
    telegram_id = int(telegram_id)
    if telegram_id == OWNER_ID: return
    conn = database.connect()
    conn.execute("""
      INSERT INTO admin_accounts(telegram_id, display_name, role, active, created_at, created_by)
      VALUES(?, ?, 'ADMIN', 1, ?, ?)
      ON CONFLICT(telegram_id) DO UPDATE SET display_name=excluded.display_name, role='ADMIN', active=1
    """, (telegram_id, display_name or f"Admin {telegram_id}", datetime.now().isoformat(timespec="seconds"), int(actor_id)))
    conn.commit(); conn.close()


def revoke_admin(telegram_id, actor_id):
    if not is_owner(actor_id):
        raise PermissionError("Only owner can revoke administrators")
    telegram_id = int(telegram_id)
    if telegram_id == OWNER_ID:
        raise ValueError("Owner cannot be revoked")
    conn = database.connect(); conn.execute("UPDATE admin_accounts SET active=0 WHERE telegram_id=?", (telegram_id,)); conn.commit(); conn.close()


def is_tester(telegram_id):
    if telegram_id is None:
        return False
    conn = database.connect_prod() if hasattr(database, "connect_prod") else database.connect()
    try:
        row = conn.execute("SELECT role,active FROM admin_accounts WHERE telegram_id=?", (int(telegram_id),)).fetchone()
        return bool(row and int(row["active"] or 0) == 1 and str(row["role"]) == "TESTER")
    finally:
        conn.close()

def make_tester(telegram_id, display_name, actor_id):
    if not is_owner(actor_id):
        raise PermissionError("Only owner can appoint testers")
    telegram_id = int(telegram_id)
    if telegram_id == OWNER_ID:
        raise ValueError("Owner does not need tester role")
    conn = database.connect_prod() if hasattr(database, "connect_prod") else database.connect()
    conn.execute("""
      INSERT INTO admin_accounts(telegram_id,display_name,role,active,created_at,created_by)
      VALUES(?,?, 'TESTER',1,?,?)
      ON CONFLICT(telegram_id) DO UPDATE SET display_name=excluded.display_name,role='TESTER',active=1
    """, (telegram_id, display_name or f"Tester {telegram_id}", datetime.now().isoformat(timespec="seconds"), int(actor_id)))
    conn.commit(); conn.close()

def make_admin(telegram_id, actor_id):
    if not is_owner(actor_id):
        raise PermissionError("Only owner can change tester role")
    conn = database.connect_prod() if hasattr(database, "connect_prod") else database.connect()
    conn.execute("UPDATE admin_accounts SET role='ADMIN',active=1 WHERE telegram_id=?", (int(telegram_id),))
    conn.commit(); conn.close()
