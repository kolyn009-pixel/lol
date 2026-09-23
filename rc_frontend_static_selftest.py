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
require("data-book-student" in teacher_dashboard, "Today dashboard lost teacher booking action")
require("/api/teacher/lesson/create" in runtime, "teacher quick booking endpoint missing from runtime")
require("teacher-book-student" in runtime, "teacher quick booking control missing")

student_app = text(WEB / "app.js")
student_auth = text(WEB / "auth_flow_v2.js")
student_css = text(WEB / "student_clean.css")
teacher_formulas = text(WEB / "teacher_formulas.js")
student_formulas = text(WEB / "student_formulas.js")

require("cdn.jsdelivr.net" not in teacher_html, "teacher boot still depends on external CDN")
require("cdn.jsdelivr.net" not in student_html, "student boot still depends on external CDN")
require("AbortController" in teacher_core and "NETWORK_TIMEOUT" in teacher_core, "teacher API timeout/fallback missing")
require("AbortController" in teacher_dashboard and "NETWORK_TIMEOUT" in teacher_dashboard, "teacher dashboard timeout/fallback missing")
require("ensureKatex" in teacher_formulas and "setTimeout(()=>finish(false),3500)" in teacher_formulas, "teacher KaTeX is not optional/lazy")
require("ensureKatex" in student_formulas and "setTimeout(()=>finish(false),3500)" in student_formulas, "student KaTeX is not optional/lazy")
require("adelia-login-gateway" in student_app, "student/parent auth gateway missing")
require("chooseStudent" in student_app and "chooseParent" in student_app, "student/parent role choices missing")
require("href=\"/teacher/\"" in student_app, "teacher entry link missing from auth gateway")
require("prefers-reduced-motion:reduce" in student_css, "auth gateway reduced-motion fallback missing")
require("window.authMode==='gateway'" in student_auth, "auth v2 does not respect role gateway")

parent_html = text(WEB / "parent" / "index.html")
parent_app = text(WEB / "parent" / "app.js")
parent_sw = text(WEB / "parent" / "service-worker.js")
student_sw = text(WEB / "service-worker.js")
require("parent_v5.css" in parent_html, "parent mobile shell stylesheet is not linked")
require("parent_clean.css" in parent_sw and "parent_v5.css" in parent_sw and "parent_v5.js" in parent_sw, "parent PWA shell cache is incomplete")
require("AbortController" in parent_app and "NETWORK_TIMEOUT" in parent_app, "parent API timeout/retry UX missing")
require("NETWORK_LIMIT_MS" in parent_sw and "boundedFetch" in parent_sw, "parent service worker network wait is unbounded")
require("NETWORK_LIMIT_MS" in student_sw and "boundedFetch" in student_sw, "student service worker network wait is unbounded")
require("Promise.race([fetch(request)" in student_sw and "Promise.race([boundedFetch(request)" not in student_sw, "student service worker boundedFetch is recursive")
require("AbortController" in student_boot, "student authenticated boot network wait is unbounded")
require("AbortController" in student_auth and "NETWORK_TIMEOUT" in student_auth, "student auth network wait is unbounded")
student_pwa = text(WEB / "pwa.js")
parent_pwa = text(WEB / "parent" / "pwa.js")
require("SW_VERSION" in student_pwa and "updateViaCache:'none'" in student_pwa and "controllerchange" in student_pwa, "student stale PWA recovery missing")
require("SW_VERSION" in parent_pwa and "updateViaCache:'none'" in parent_pwa and "controllerchange" in parent_pwa, "parent stale PWA recovery missing")
require("20260922-mobile-recovery1" in student_html, "student mobile recovery assets are not cache-busted")
require("20260922-mobile-recovery1" in parent_html, "parent mobile recovery assets are not cache-busted")

manual_booking = text(ROOT / "web_backend" / "teacher_manual_booking.py")
api_v7 = text(ROOT / "web_backend" / "api_v7.py")
require("create_admin_lesson" in manual_booking, "teacher manual booking bypasses canonical lesson creation")
require("sync_lesson" in manual_booking, "teacher manual booking lost integration sync")
require("mirror_messengers=True" in manual_booking, "teacher manual booking does not mirror notifications")
require("/api/teacher/lesson/create" in api_v7, "teacher manual booking API route missing")

lesson_link_delivery = text(ROOT / "web_backend" / "lesson_link_delivery.py")
lesson_join = text(ROOT / "web_backend" / "lesson_join.py")
channel_delivery = text(ROOT / "vk_adapter" / "channel_delivery.py")
require("channels=['TELEGRAM','VK']" in lesson_link_delivery, "website lesson start does not fan out links to Telegram and VK")
require("send_teacher_vk" in lesson_link_delivery, "teacher VK delivery confirmation missing")
require('"delivery":delivery' in lesson_join, "website lesson start does not expose channel delivery result")
require("def send_teacher_vk" in channel_delivery, "teacher VK delivery helper missing")

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

finance_ui = text(WEB / "teacher_finance.js")
finance_api = text(ROOT / "web_backend" / "stage8_api.py")
finance_reporting = text(ROOT / "web_backend" / "finance_reporting.py")
require("✓ Занятие оплачено" in finance_ui and "/teacher/finance/lesson/paid" in finance_ui, "teacher mark-paid control missing")
require("/api/teacher/finance/lesson/paid" in finance_api, "teacher mark-paid API route missing")
require("def mark_lesson_paid" in finance_reporting and "confirm_manual_lesson_payment" in finance_reporting, "teacher mark-paid action bypasses canonical payment lifecycle")
require("_closed_by_exception" in trial_slots, "public trial slots ignore day-close exceptions")
onboarding_slots = text(ROOT / "web_backend" / "onboarding_schedule_options.py")
require("_closed_by_exception" in onboarding_slots, "onboarding slots ignore day-close exceptions")

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
