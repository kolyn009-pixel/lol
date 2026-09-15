"""Per-student group subscription reservation helpers.

The legacy reservation helper checked only lesson_id, which meant the first
student reserved a lesson and every other student in the same group could be
reported as already reserved. These helpers scope idempotency to the student's
own subscription and refund every reservation for a cancelled lesson.
"""
from __future__ import annotations

import database
from web_backend import group_finance


def reserve_for_student(lesson_id,user_id):
    group_finance.ensure_schema();lid=int(lesson_id);uid=int(user_id);c=database.connect()
    lesson=c.execute("SELECT group_id FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not lesson:
        c.close();raise ValueError("group_lesson_not_found")
    existing=c.execute("""SELECT l.subscription_id
                            FROM group_subscription_ledger l
                            JOIN group_subscriptions s ON s.id=l.subscription_id
                           WHERE l.lesson_id=? AND l.reason='LESSON_RESERVE'
                             AND s.user_id=? AND s.group_id=?
                           ORDER BY l.id DESC LIMIT 1""",(lid,uid,int(lesson["group_id"]))).fetchone()
    if existing:
        c.close();return {"status":"already_reserved","subscription_id":int(existing["subscription_id"])}
    sub=group_finance._active_subscription_row(c,int(lesson["group_id"]),uid)
    if not sub:
        c.close();raise ValueError("group_subscription_unavailable")
    sid=int(sub["id"]);now=database.now_iso()
    cur=c.execute("UPDATE group_subscriptions SET lessons_remaining=lessons_remaining-1,updated_at=? WHERE id=? AND lessons_remaining>0",(now,sid))
    if not cur.rowcount:
        c.close();raise ValueError("group_subscription_unavailable")
    c.execute("INSERT INTO group_subscription_ledger(subscription_id,lesson_id,delta,reason,created_at) VALUES(?,?,-1,'LESSON_RESERVE',?)",(sid,lid,now))
    remaining=max(0,int(sub["lessons_remaining"])-1)
    if remaining<=0:c.execute("UPDATE group_subscriptions SET status='EXHAUSTED',updated_at=? WHERE id=?",(now,sid))
    c.commit();c.close();return {"status":"ok","subscription_id":sid,"lessons_remaining":remaining}


def refund_all_for_lesson(lesson_id):
    group_finance.ensure_schema();lid=int(lesson_id);c=database.connect();rows=c.execute("SELECT * FROM group_subscription_ledger WHERE lesson_id=? AND reason='LESSON_RESERVE' ORDER BY id",(lid,)).fetchall()
    if not rows:
        c.close();return {"status":"nothing_to_refund","refunded":0}
    now=database.now_iso();refunded=[]
    for row in rows:
        sid=int(row["subscription_id"])
        exists=c.execute("SELECT 1 FROM group_subscription_ledger WHERE subscription_id=? AND lesson_id=? AND reason='LESSON_REFUND'",(sid,lid)).fetchone()
        if exists:continue
        c.execute("UPDATE group_subscriptions SET lessons_remaining=lessons_remaining+1,status='ACTIVE',updated_at=? WHERE id=?",(now,sid))
        c.execute("INSERT INTO group_subscription_ledger(subscription_id,lesson_id,delta,reason,created_at) VALUES(?,?,1,'LESSON_REFUND',?)",(sid,lid,now))
        refunded.append(sid)
    c.commit();c.close();return {"status":"ok" if refunded else "already_refunded","refunded":len(refunded),"subscription_ids":refunded}
