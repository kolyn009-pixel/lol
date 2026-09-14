#!/usr/bin/env python3
"""Read-only/static functional gate for the Teacher clean release candidate.

This intentionally does not touch the production database. Runtime API calls that
need teacher authentication are checked later by the isolated server smoke.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]

def text(path):
    return (ROOT / path).read_text(encoding="utf-8")

def require(data, markers, label):
    for marker in markers:
        if marker not in data:
            raise AssertionError(f"{label}: missing {marker!r}")

teacher_html = text("web/teacher.html")
api_v7 = text("web_backend/api_v7.py")
groups_js = text("web/teacher_groups.js")
messages_js = text("web/teacher_messages_stage10.js")
schedule_js = text("web/teacher_schedule_settings.js")
formula_js = text("web/teacher_formulas.js")
formula_repair = text("web_backend/formula_schema_repair.py")
v5_runtime = text("web/teacher_v5_runtime.js")
clean_sections = text("web/teacher_clean_sections.css")
manifest = json.loads(text("web/teacher-manifest.webmanifest"))

require(teacher_html, [
    'data-view="dashboard"', 'data-view="schedule"', 'data-view="students"',
    'data-view="groups"', 'data-view="homework"', 'data-view="reviews"',
    'data-view="messages"', 'data-view="payments"', 'data-view="library"',
    'data-view="formulas"', 'data-view="finance"', 'data-view="analytics"',
    'data-view="health"', '/app/teacher_clean.css', '/app/teacher_clean_sections.css',
    '/app/teacher_clean_runtime.js', '/app/teacher_clean_router.js',
    '/app/teacher_groups.js', '/app/teacher_formulas.js'
], "teacher shell")

require(clean_sections, [
    '.msg-shell', '.msg-thread', '.msg-compose', '.finance-head', '.finance-kpis',
    '.finance-grid', '.v4-page-head', '.v4-group-grid', '.v4-group-card'
], "teacher clean sections")

require(api_v7, [
    'path == "/api/teacher/groups"', 'path == "/api/teacher/group/create"',
    "formula_schema_repair.ensure_schema()",
    'path == "/api/teacher/google-calendar/status"',
    'path == "/api/teacher/google-calendar/connect"'
], "api v7")

require(groups_js, [
    "'/teacher/groups'", "'/teacher/group/create'", 'id="groupCreateTop"',
    'id="groupCreateForm"', 'name="weekday"', 'name="start_time"',
    'name="duration_minutes"'
], "groups UI")

require(messages_js, [
    "const stop=()=>", "state.visible=false", "clearInterval(state.timer)",
    "view.dataset.view!=='messages'", "window.addEventListener('beforeunload',stop)"
], "messages lifecycle")

require(schedule_js, [
    "button[data-view=\"schedule\"]", "e.stopImmediatePropagation()", "openEditor()",
    "'/teacher/working-hours'"
], "schedule navigation")

require(formula_js, [
    "window.teacherFormulas=handbook", "'/teacher/formulas?", "'/teacher/formula'",
    "'/teacher/formula-import/upload'"
], "formula UI")

require(formula_repair, [
    "CREATE TABLE IF NOT EXISTS formula_book", "PRAGMA table_info(formula_book)",
    "ALTER TABLE formula_book ADD COLUMN", "CREATE TABLE IF NOT EXISTS formula_favorites"
], "formula schema repair")

if "new MutationObserver" in v5_runtime:
    raise AssertionError("teacher v5 runtime still contains continuous MutationObserver")

if manifest.get("start_url") != "/teacher/":
    raise AssertionError("teacher manifest start_url is not /teacher/")
if manifest.get("scope") != "/teacher/":
    raise AssertionError("teacher manifest scope is not /teacher/")
if manifest.get("display") != "standalone":
    raise AssertionError("teacher manifest is not standalone")

for forbidden in [
    "teacher_runtime_hotfix.js", "teacher_desktop_v2.js", "teacher_stage2_workspace.js",
    "teacher_stage3_learning.js", "teacher_stage4_workspace.js", "teacher_stage5_polish.js",
    "stage11_runtime.js"
]:
    if forbidden in teacher_html:
        raise AssertionError(f"old teacher runtime returned: {forbidden}")

print("TEACHER_CLEAN_FUNCTIONAL_GATE=PASS")
