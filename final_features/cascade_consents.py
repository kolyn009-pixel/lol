from __future__ import annotations

from datetime import datetime
import database
from final_features import cascade_shift


def ensure_schema():
    c = database.connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cascade_shift_consents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      plan_id INTEGER NOT NULL,
      student_id INTEGER NOT NULL,
      lesson_id INTEGER NOT NULL,
      proposed_start TEXT NOT NULL,
      proposed_end TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'PENDING',
      created_at TEXT NOT NULL,
      responded_at TEXT,
      UNIQUE(plan_id, student_id, lesson_id),
      FOREIGN KEY(plan_id) REFERENCES cascade_shift_plans(id) ON DELETE CASCADE,
      FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_cascade_consents_student
      ON cascade_shift_consents(student_id,status,created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_cascade_consents_plan
      ON cascade_shift_consents(plan_id,status);
    """)
    c.commit(); c.close()


def create_for_approved_plan(plan_id):
    """Create consent rows only after the teacher has explicitly approved the analyzed plan."""
    ensure_schema()
    plan = cascade_shift.get_plan(int(plan_id))
    if not plan:
        raise ValueError('plan_not_found')
    if plan['status'] != 'APPROVED':
        raise PermissionError('teacher_approval_required')
    now = datetime.now().isoformat(timespec='seconds')
    moves = [m for m in (plan['plan'].get('moves') or []) if m.get('role') == 'displaced']
    c = database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        for m in moves:
            c.execute("""
              INSERT INTO cascade_shift_consents(plan_id,student_id,lesson_id,proposed_start,proposed_end,status,created_at)
              VALUES(?,?,?,?,?,'PENDING',?)
              ON CONFLICT(plan_id,student_id,lesson_id) DO NOTHING
            """, (int(plan_id), int(m['user_id']), int(m['lesson_id']), m['to_start'], m['to_end'], now))
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
    return {'status': 'ok', 'plan_id': int(plan_id), 'requested_consents': len(moves)}


def incoming(student_id):
    ensure_schema(); c = database.connect()
    rows = c.execute("""
      SELECT cc.*,l.start_time AS original_start,l.end_time AS original_end
      FROM cascade_shift_consents cc
      JOIN lessons l ON l.id=cc.lesson_id
      JOIN cascade_shift_plans p ON p.id=cc.plan_id
      WHERE cc.student_id=? AND cc.status='PENDING' AND p.status='APPROVED'
      ORDER BY cc.created_at DESC
    """, (int(student_id),)).fetchall(); c.close()
    return [dict(r) for r in rows]


def respond(student_id, consent_id, accepted):
    ensure_schema()
    if not isinstance(accepted, bool):
        raise ValueError('invalid_accepted')
    c = database.connect()
    row = c.execute("SELECT * FROM cascade_shift_consents WHERE id=? AND student_id=?", (int(consent_id), int(student_id))).fetchone()
    if not row:
        c.close(); raise PermissionError('consent_not_found')
    if row['status'] != 'PENDING':
        c.close(); raise ValueError('consent_already_resolved')
    now = datetime.now().isoformat(timespec='seconds')
    new_status = 'ACCEPTED' if accepted else 'DECLINED'
    c.execute("UPDATE cascade_shift_consents SET status=?,responded_at=? WHERE id=?", (new_status, now, int(consent_id)))
    if not accepted:
        c.execute("UPDATE cascade_shift_plans SET status='DECLINED',invalidated_reason='student_declined' WHERE id=? AND status='APPROVED'", (int(row['plan_id']),))
    c.commit(); c.close()
    return {'status': 'ok', 'consent_id': int(consent_id), 'accepted': accepted, 'plan_id': int(row['plan_id'])}


def summary(plan_id):
    ensure_schema(); c=database.connect()
    rows=c.execute("SELECT status,COUNT(*) AS n FROM cascade_shift_consents WHERE plan_id=? GROUP BY status",(int(plan_id),)).fetchall();c.close()
    counts={r['status']:int(r['n']) for r in rows}
    total=sum(counts.values())
    return {
      'plan_id':int(plan_id),
      'total':total,
      'pending':counts.get('PENDING',0),
      'accepted':counts.get('ACCEPTED',0),
      'declined':counts.get('DECLINED',0),
      'all_accepted': total > 0 and counts.get('ACCEPTED',0) == total,
    }


def ready_for_final_apply(plan_id):
    plan=cascade_shift.get_plan(int(plan_id))
    if not plan or plan['status']!='APPROVED':return False
    s=summary(plan_id)
    return s['total'] == 0 or s['all_accepted']
