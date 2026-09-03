from __future__ import annotations
from datetime import datetime
import database


def pending_for_student(user_id):
    c=database.connect()
    try:return c.execute("SELECT * FROM homework WHERE user_id=? AND status IN ('ASSIGNED','REVISION','SUBMITTED') ORDER BY COALESCE(deadline,'9999')",(int(user_id),)).fetchall()
    finally:c.close()

def teacher_queue():
    c=database.connect()
    try:return c.execute("SELECT h.*,u.name FROM homework h JOIN users u ON u.id=h.user_id WHERE h.status='SUBMITTED' ORDER BY h.submitted_at").fetchall()
    finally:c.close()
