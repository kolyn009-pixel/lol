"""Stage 10 read-state bridge.

While legacy CRM screens are still present, opening a unified Web dialog must also
clear the old unread flags for the same student. This keeps unread counters aligned
across the new Web inbox and existing TutorBot admin views.
"""
from __future__ import annotations

from database import connect, now_iso
from web_backend import unified_messaging as um


def _table_exists(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(str(name),)).fetchone())


def mark_conversation_read(conversation_id):
    cid=int(conversation_id)
    um.ensure_tables()
    conn=connect();conv=conn.execute('SELECT student_id FROM unified_conversations WHERE id=?',(cid,)).fetchone();conn.close()
    if not conv:raise ValueError('conversation_not_found')
    uid=int(conv['student_id']);result=um.mark_read(cid);stamp=now_iso();conn=connect()
    try:
        if _table_exists(conn,'crm_student_messages'):
            conn.execute("""
              UPDATE crm_student_messages
              SET status='READ',read_at=COALESCE(read_at,?)
              WHERE student_id=? AND direction='IN' AND read_at IS NULL
            """,(stamp,uid))
        if _table_exists(conn,'teacher_inbox'):
            conn.execute("""
              UPDATE teacher_inbox
              SET status='CLOSED',closed_at=COALESCE(closed_at,?)
              WHERE student_id=? AND status='OPEN'
                AND subject IN ('Сообщение от ученика','Ответ ученика','Сообщение от ученика из VK','Сообщение от ученика с сайта','Срочное сообщение от ученика')
            """,(stamp,uid))
        conn.commit()
    finally:conn.close()
    return {'status':result.get('status','ok'),'conversation_id':cid,'student_id':uid}
