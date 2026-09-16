"""Monthly included lesson allowances for selected students.

This is intentionally implemented on top of the canonical BONUS lesson balance:
there is no invoice and no paid revenue. A configured allowance is granted at
most once per calendar month and therefore works for family/free students
without special-casing their names or accounts.
"""
from __future__ import annotations

from datetime import datetime

import database


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _month_key(value=None):
    dt=value or datetime.now()
    return dt.strftime("%Y-%m")


def ensure_schema():
    conn=database.connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS student_monthly_allowances(
            user_id INTEGER PRIMARY KEY,
            lessons_per_month INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 0,
            label TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS student_monthly_allowance_grants(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            month_key TEXT NOT NULL,
            lessons_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id,month_key),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_monthly_allowance_grants_user
          ON student_monthly_allowance_grants(user_id,month_key);
    """)
    conn.commit();conn.close()


def _user(user_id):
    row=database.get_user(int(user_id))
    if not row:raise ValueError("student_not_found")
    return row


def _setting(user_id):
    ensure_schema();conn=database.connect()
    row=conn.execute("SELECT * FROM student_monthly_allowances WHERE user_id=?",(int(user_id),)).fetchone()
    conn.close();return dict(row) if row else None


def _grants(user_id,limit=12):
    ensure_schema();conn=database.connect()
    rows=conn.execute("SELECT month_key,lessons_count,created_at FROM student_monthly_allowance_grants WHERE user_id=? ORDER BY month_key DESC LIMIT ?",(int(user_id),max(1,min(int(limit),36)))).fetchall()
    conn.close();return [dict(r) for r in rows]


def grant_current_month(user_id,force=False):
    """Grant this month's configured allowance exactly once."""
    uid=int(user_id);user=_user(uid);setting=_setting(uid)
    if not setting or not int(setting.get("active") or 0):return {"status":"inactive","granted":0}
    count=int(setting.get("lessons_per_month") or 0)
    if count<=0:return {"status":"inactive","granted":0}
    month=_month_key();now=_now();conn=database.connect()
    try:
        if force:
            # Force is only useful after an operator deliberately deletes/repairs
            # a grant marker; never create duplicates by default.
            existing=conn.execute("SELECT id FROM student_monthly_allowance_grants WHERE user_id=? AND month_key=?",(uid,month)).fetchone()
            if existing:return {"status":"already_granted","granted":0,"month":month}
        try:
            conn.execute("INSERT INTO student_monthly_allowance_grants(user_id,month_key,lessons_count,created_at) VALUES(?,?,?,?)",(uid,month,count,now));conn.commit()
        except Exception:
            conn.rollback()
            existing=conn.execute("SELECT id FROM student_monthly_allowance_grants WHERE user_id=? AND month_key=?",(uid,month)).fetchone()
            if existing:return {"status":"already_granted","granted":0,"month":month}
            raise
    finally:
        conn.close()
    try:
        package_id=database.add_bonus_lessons(uid,count,user["study_goal"],user["main_subject"],reason="MONTHLY_INCLUDED")
    except Exception:
        # Do not leave a false idempotency marker if the canonical balance write failed.
        cleanup=database.connect();cleanup.execute("DELETE FROM student_monthly_allowance_grants WHERE user_id=? AND month_key=?",(uid,month));cleanup.commit();cleanup.close();raise
    return {"status":"ok","granted":count,"month":month,"package_id":package_id}


def configure(user_id,lessons_per_month,active=True,label=None,grant_now=True):
    uid=int(user_id);_user(uid);count=int(lessons_per_month)
    if count<0 or count>50:raise ValueError("invalid_lessons_per_month")
    active=1 if bool(active) and count>0 else 0;now=_now();text=str(label or "Бесплатные занятия").strip()[:80] or "Бесплатные занятия"
    ensure_schema();conn=database.connect()
    conn.execute("""INSERT INTO student_monthly_allowances(user_id,lessons_per_month,active,label,created_at,updated_at)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET lessons_per_month=excluded.lessons_per_month,active=excluded.active,label=excluded.label,updated_at=excluded.updated_at""",
                 (uid,count,active,text,now,now));conn.commit();conn.close()
    grant=None
    if active and grant_now:grant=grant_current_month(uid)
    return status(uid,ensure_grant=False,grant_result=grant)


def status(user_id,ensure_grant=True,grant_result=None):
    uid=int(user_id);_user(uid);setting=_setting(uid)
    if setting and int(setting.get("active") or 0) and ensure_grant:
        grant_result=grant_current_month(uid)
    grants=_grants(uid)
    month=_month_key();this_month=next((x for x in grants if x["month_key"]==month),None)
    return {
        "configured":bool(setting),
        "active":bool(setting and int(setting.get("active") or 0)),
        "lessons_per_month":int(setting.get("lessons_per_month") or 0) if setting else 0,
        "label":setting.get("label") if setting else None,
        "month":month,
        "granted_this_month":bool(this_month),
        "this_month":this_month,
        "recent_grants":grants,
        "grant_result":grant_result,
    }
