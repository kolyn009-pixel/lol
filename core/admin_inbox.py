"""Unified admin inbox: operational notifications and requests.

Student/parent free-form messages intentionally live in a separate queue.
"""
import database
from core import event_center
from core import schema as core_schema
from automation import messaging, schema as automation_schema


def _safe_count(conn, sql, params=()):
    try:
        return int(conn.execute(sql, params).fetchone()[0] or 0)
    except Exception:
        return 0


def counts():
    core_schema.ensure_schema()
    automation_schema.initialize()
    conn=database.connect()
    try:
        data={
            'lesson_requests': _safe_count(conn,"SELECT COUNT(*) FROM lessons WHERE lesson_status='PENDING'"),
            'regular_requests': _safe_count(conn,"SELECT COUNT(*) FROM regular_schedules WHERE status='PENDING'"),
            'unpaid': _safe_count(conn,"SELECT COUNT(*) FROM lessons WHERE lesson_status='CONFIRMED' AND payment_status='AWAITING_PAYMENT'"),
            'receipts': _safe_count(conn,"SELECT COUNT(*) FROM payments WHERE status IN ('RECEIPT_SENT','RECEIVED')"),
            'homework': _safe_count(conn,"SELECT COUNT(*) FROM homework WHERE status IN ('SUBMITTED','WAITING_REVIEW')"),
            'waiting_list': _safe_count(conn,"SELECT COUNT(*) FROM waiting_list WHERE status='ACTIVE'"),
        }
    finally:
        conn.close()
    all_events=[e for e in event_center.open_events(200) if e.get('event_type')!='TEACHER_INBOX']
    system_types={'BOT_ERROR','STARTUP_BACKUP_ERROR','LEDGER_SYNC_ERROR','BACKUP_ERROR'}
    system_events=[e for e in all_events if e.get('event_type') in system_types or str(e.get('event_type','')).endswith('_ERROR')]
    events=[e for e in all_events if e not in system_events]
    data['events']=len(events)
    data['system_events']=len(system_events)
    data['total']=sum(data[k] for k in ('lesson_requests','regular_requests','unpaid','receipts','homework','waiting_list','events'))
    conn=database.connect()
    try:
        data['student_messages']=_safe_count(conn,"SELECT COUNT(*) FROM teacher_inbox WHERE status IN ('OPEN','QUEUED')")
    finally:
        conn.close()
    return data


def event_rows(limit=30):
    system_types={'BOT_ERROR','STARTUP_BACKUP_ERROR','LEDGER_SYNC_ERROR','BACKUP_ERROR'}
    return [e for e in event_center.open_events(limit*4) if e.get('event_type')!='TEACHER_INBOX' and e.get('event_type') not in system_types and not str(e.get('event_type','')).endswith('_ERROR')][:limit]
