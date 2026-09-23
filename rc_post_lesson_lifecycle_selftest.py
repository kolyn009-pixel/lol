from pathlib import Path

ROOT = Path(__file__).resolve().parent

def read(path):
    return path.read_text(encoding="utf-8")

def require(condition, message):
    if not condition:
        raise AssertionError(message)

flow = read(ROOT / "web_backend" / "post_lesson_flow.py")
complete = read(ROOT / "web_backend" / "post_lesson_complete.py")
post_ui = read(ROOT / "web" / "teacher_post_lesson.js")
teacher = read(ROOT / "web" / "teacher.js")
dashboard = read(ROOT / "web" / "teacher_dashboard_week.js")

require("topics_for_student" in flow and "if available:" in flow, "empty-topic review fallback missing")
require("save_review(" in flow and "set_homework_status" in flow, "canonical review/homework flow missing")
require("review_required" in complete and "homework_decision_required" in complete, "post-lesson completion gates missing")
require("POST_LESSON_SUMMARY" in complete and "post_lesson.claim" in complete, "summary notification idempotency missing")
require("AdeliaPostLessonOpen" in post_ui and "active=false;lessonId=null" in post_ui, "post-lesson navigation lifecycle missing")
require("/teacher/lesson/review/complete" in post_ui and "/teacher/lesson/homework/skip" in post_ui and "/teacher/lesson/complete" in post_ui, "post-lesson canonical API wiring missing")
require("confirm(" not in post_ui and "confirm(" not in teacher, "browser confirmation returned")
require("/teacher/lesson/finish" in dashboard and "endLessonWorkspace()" in dashboard, "desktop finish handoff missing")
require("typeof window.lesson==='function')window.lesson(id)" in dashboard, "desktop finish must reopen canonical lesson/post-lesson route")
print("RC POST-LESSON LIFECYCLE SELFTEST: OK")
