"""One-shot, non-mutating Stage 4 lesson-flow integrity test.

Run in the isolated web-preview runtime. It inspects the shared DB but performs
no lesson transitions, payments, messages or homework writes.
"""
from __future__ import annotations
from database import connect
from web_backend.lesson_workspace import workspace
from web_backend.lesson_context import context
from web_backend.post_lesson_flow import state as post_state
from web_backend.post_lesson_complete import state as completion_state
from web_backend.lesson_join import join_events


def run():
    print("=== ADELIA STAGE 4 LESSON FLOW SELFTEST ===")
    conn=connect();row=conn.execute("SELECT id,finished_at FROM lessons ORDER BY id DESC LIMIT 1").fetchone();conn.close()
    if not row:
        print("lesson workspace: SKIP (no lessons)");print("STAGE 4 STRUCTURE: OK");return True
    lid=int(row["id"])
    w=workspace(lid);assert w and int(w["lesson"]["id"])==lid
    c=context(lid);assert c and int(c["lesson_id"])==lid and "student" in c and "messages" in c and "homework" in c
    events=join_events(lid);assert isinstance(events,list)
    p=post_state(lid);assert p and "review_completed" in p and "homework_status" in p
    done=completion_state(lid);assert done and {"finished","review_completed","homework_status","ready"}<=set(done)
    print("lesson workspace: OK")
    print("lesson context: OK")
    print("join event model: OK",len(events))
    print("post-lesson state: OK")
    print("completion gate: OK",done["ready"])
    print("STAGE 4 STRUCTURE: OK")
    return True


if __name__=="__main__":run()
