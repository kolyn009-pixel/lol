import json
from datetime import datetime
import database
from .schema import ensure_schema
from . import admin_roles


def log(action, actor_id=None, entity_type=None, entity_id=None, details=None):
    ensure_schema()
    role = admin_roles.role_for(actor_id) if actor_id else None
    payload = json.dumps(details, ensure_ascii=False, default=str) if details is not None else None
    conn = database.connect()
    conn.execute("""INSERT INTO audit_log(actor_telegram_id,actor_role,action,entity_type,entity_id,details,created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                 (actor_id, role, action, entity_type, str(entity_id) if entity_id is not None else None, payload, datetime.now().isoformat(timespec="seconds")))
    conn.commit(); conn.close()


def recent(limit=30):
    conn=database.connect(); rows=conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",(int(limit),)).fetchall(); conn.close(); return [dict(r) for r in rows]
