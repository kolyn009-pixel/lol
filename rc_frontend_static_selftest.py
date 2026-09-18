from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DESKTOP = ROOT / "desktop"

errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


def text(path):
    return path.read_text(encoding="utf-8")


def local_app_refs(html):
    return set(re.findall(r'(?:src|href)="/app/([^"?]+)', html))


teacher_html = text(WEB / "teacher.html")
student_html = text(WEB / "index.html")
student_boot = text(WEB / "student_boot.js")
router = text(WEB / "teacher_clean_router.js")
runtime = text(WEB / "teacher_clean_runtime.js")
lesson_flow = text(WEB / "teacher_lesson_flow.js")
teacher_core = text(WEB / "teacher.js")
teacher_dashboard = text(WEB / "teacher_dashboard_week.js")
desktop_selftest = text(DESKTOP / "selftest.js")

for name, html in (("teacher", teacher_html), ("student", student_html)):
    for ref in sorted(local_app_refs(html)):
        require((WEB / ref).is_file(), f"{name} missing /app/{ref}")

for module in re.findall(r"'([^']+\.js)'", student_boot):
    require((WEB / module).is_file(), f"student_boot missing dynamic module {module}")

require("teacher_clean_router.js" in teacher_html, "teacher clean router not linked")
require(
    teacher_html.rfind("teacher_clean_router.js") > teacher_html.rfind("teacher_v5_runtime.js"),
    "teacher clean router must load after legacy teacher runtime",
)
require("teacher_runtime_hotfix.js" not in teacher_html, "legacy teacher runtime hotfix is still linked")
require("AWAITING_PAYMENT" in runtime, "teacher runtime lost unpaid-state handling")
require("/api/teacher/lesson/payment-wait" in runtime, "teacher payment-wait action missing")
require("/teacher/lesson/open-entry" in lesson_flow, "teacher lesson flow bypasses canonical open-entry endpoint")
require("window.AdeliaTeacherRoute=route" in router, "teacher clean route entrypoint missing")
require("window.AdeliaTeacherDashboardV2" in teacher_core, "legacy teacher dashboard does not delegate to canonical dashboard")
require("window.AdeliaTeacherDashboardV2=render" in teacher_dashboard, "canonical teacher dashboard export missing")
require("window.dashboard=render" in teacher_dashboard, "canonical teacher dashboard does not own dashboard entrypoint")
require("teacher-dashboard-v2" in teacher_dashboard, "polished teacher dashboard markup missing")

teacher_messages = text(WEB / "teacher_messages_stage10.js")
student_chat = text(WEB / "student_chat.js")
stage10_api = text(ROOT / "web_backend" / "stage10_api.py")
api_v2 = text(ROOT / "web_backend" / "api_v2.py")
require("FormData" in teacher_messages and "/teacher/messages/upload" in teacher_messages, "teacher web chat media upload missing")
require("FormData" in student_chat and "/student/message-media/upload" in student_chat, "student web chat media upload missing")
require("/api/teacher/messages/upload" in stage10_api, "teacher authenticated media upload endpoint missing")
require("/api/student/message-media/upload" in api_v2, "student authenticated media upload endpoint missing")

schedule_ui = text(WEB / "teacher_schedule_settings.js")
schedule_backend = text(ROOT / "web_backend" / "teacher_schedule_settings.py")
regular_booking = text(ROOT / "web_backend" / "student_regular_booking.py")
trial_slots = text(ROOT / "web_backend" / "public_trial_slots.py")
require("begin_timezone_change" in schedule_backend, "teacher timezone begin workflow missing")
require("commit_timezone_change" in schedule_backend, "teacher timezone commit workflow missing")
require("existing_lessons_changed" in schedule_backend, "teacher timezone workflow lost existing-lesson invariant")
require("teacher_schedule_booking_paused" in schedule_backend, "teacher timezone booking pause missing")
require("teacher_schedule_booking_paused" in regular_booking, "regular booking ignores region-change pause")
require("teacher_schedule_booking_paused" in trial_slots, "trial slots ignore region-change pause")
require("whRegionOpen" in schedule_ui, "teacher region change UI entrypoint missing")
require("whRegionCommit" in schedule_ui, "teacher region change confirmation missing")
require("currentRegularEdits" in schedule_ui, "teacher region change does not expose editable regular schedules")
require("_normalize_regular_edits" in schedule_backend, "teacher region change does not validate regular schedule edits")
require("_apply_regular_edits" in schedule_backend, "teacher region change does not apply explicit regular schedule edits")
require("_convert_regular_rows_for_timezone" not in schedule_backend, "teacher region change still auto-rebases regular schedules")

for required in (
    "bootstrap.js", "main.js", "preload.js", "lesson_workspace.js",
    "desktop_ux.js", "lesson_layout.js", "role_startup.js",
    "system_polish.js", "network_ux.js", "start.js", "start.html",
    "start.css", "offline.html", "package.json",
):
    require((DESKTOP / required).is_file(), f"desktop file missing: {required}")

for required in (
    WEB / "parent" / "index.html",
    WEB / "parent" / "manifest.webmanifest",
    WEB / "teacher_lesson_flow.js",
    WEB / "teacher_group_live12.js",
    WEB / "teacher_event_live13.js",
    WEB / "teacher_telemost_settings.js",
):
    require(required.is_file(), f"desktop web dependency missing: {required.relative_to(ROOT)}")

for marker in (
    "teacher_lesson_flow.js",
    "teacher_group_live12.js",
    "teacher_event_live13.js",
    "teacher_telemost_settings.js",
):
    require(marker in desktop_selftest, f"desktop selftest lost {marker}")

if errors:
    for item in errors:
        print("FAIL:", item)
    raise SystemExit(1)

print("RC FRONTEND STATIC SELFTEST: OK")
print("teacher/student local assets, dynamic student modules, router order, payment guards and desktop dependencies present")
