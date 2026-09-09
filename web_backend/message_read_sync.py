"""Stage 10 read-state bridge.

While legacy CRM screens are still present, opening a unified Web dialog must also
clear the old unread flags for the same student. This keeps unread counters aligned
across the new Web inbox and existing TutorBot admin views.
"""
from __future__ import annotations

from database import connect, now_iso
from web_backend import unified_messaging as um


def mark_conversation_read(conversation_id):
    cid=int(conversation_id)
    um.ensure_tables()
    conn=connect()
    conv=conn.execute('SELECT student_id FROM unified_conversations WHERE id=?',(cid,)).fetchone()
    conn.close()
    if not conv:raise ValueError('conversation_not_found')
    uid=int(conv['student_id'])
    result=um.mark_read(cid)
    stamp=now_iso();conn=connect()
    try:
        # Legacy CRM message counter.
        conn.execute("""
          UPDATE crm_student_messages
          SET status='READ',read_at=COALESCE(read_at,?)
          WHERE student_id=? AND direction='IN' AND read_at IS NULL
        """,(stamp,uid))
        # Legacy teacher inbox items created by Telegram/VK/Web chat bridges.
        conn.execute("""
          UPDATE teacher_inbox
          SET status='CLOSED',closed_at=COALESCE(closed_at,?)
          WHERE student_id=? AND status='OPEN'
            AND subject IN ('Сообщение от ученика','Ответ ученика','Сообщение от ученика из VK','Сообщение от ученика с сайта','Срочное сообщение от ученика')
        """,(stamp,uid))
        conn.commit()
    except Exception:
        # Some isolated/test databases may not have every legacy table yet.
        conn.rollback()
    finally:conn.close()
    return {'status':result.get('status','ok'),'conversation_id':cid,'student_id':uid}
