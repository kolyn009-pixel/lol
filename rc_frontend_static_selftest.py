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
