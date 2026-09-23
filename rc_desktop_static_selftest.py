from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DESKTOP = ROOT / "desktop"
WEB = ROOT / "web"
errors = []


def require(ok, label):
    if not ok:
        errors.append(label)


def read(path):
    return path.read_text(encoding="utf-8")


pkg = json.loads(read(DESKTOP / "package.json"))
main = read(DESKTOP / "main.js")
bootstrap = read(DESKTOP / "bootstrap.js")
preload = read(DESKTOP / "preload.js")
workspace = read(DESKTOP / "lesson_workspace.js")
role = read(DESKTOP / "role_startup.js")
network = read(DESKTOP / "network_ux.js")
system = read(DESKTOP / "system_polish.js")
ux = read(DESKTOP / "desktop_ux.js")
layout = read(DESKTOP / "lesson_layout.js")
start_js = read(DESKTOP / "start.js")
start_html = read(DESKTOP / "start.html")
start_css = read(DESKTOP / "start.css")
offline = read(DESKTOP / "offline.html")
icon_sync = read(DESKTOP / "generate_assets.js")
student = read(WEB / "index.html")
teacher = read(WEB / "teacher.html")
parent = read(WEB / "parent" / "index.html")
landing = read(WEB / "landing.js")
landing_html = read(WEB / "landing.html")
individual = read(WEB / "teacher_lesson_flow.js")
group = read(WEB / "teacher_group_live12.js")
event = read(WEB / "teacher_event_live13.js")
telemost_settings = read(WEB / "teacher_telemost_settings.js")
teacher_dashboard = read(WEB / "teacher_dashboard_week.js")
teacher_dashboard_css = read(WEB / "teacher_dashboard_week.css")
teacher_portal = read(ROOT / "web_backend" / "teacher_portal.py")
parent_manifest_text = read(WEB / "parent" / "manifest.webmanifest")
parent_manifest = json.loads(parent_manifest_text)

require(pkg.get("version") == "0.3.0-beta.1", "desktop package version")
require(pkg.get("main") == "bootstrap.js", "desktop bootstrap entry")
build = pkg.get("build") or {}
require(build.get("appId") == "ru.adeliatutor.desktop", "stable app id")
require(build.get("asar") is True, "asar enabled")
require((pkg.get("devDependencies") or {}).get("electron") == "38.0.0", "Electron pinned")
require((pkg.get("devDependencies") or {}).get("electron-builder") == "26.0.12", "electron-builder pinned")
require((pkg.get("dependencies") or {}).get("electron-updater") == "6.6.2", "electron-updater pinned")
publish = build.get("publish") or []
require(
    bool(publish)
    and publish[0].get("provider") == "generic"
    and str(publish[0].get("url") or "").startswith("https://adeliatutor.ru/desktop-updates/")
    and publish[0].get("channel") == "beta"
    and "UPDATE_CHANNEL" in main
    and "UPDATE_TARGET" in main
    and "desktop-updates/${UPDATE_CHANNEL}/${UPDATE_TARGET}/" in main
    and "setFeedURL" in main,
    "trusted update endpoint",
)
protocols = build.get("protocols") or []
require(bool(protocols) and "adelia" in (protocols[0].get("schemes") or []), "adelia deep-link protocol registered")
require("nsis" in ((build.get("win") or {}).get("target") or []), "Windows NSIS target")
mac_targets = (build.get("mac") or {}).get("target") or []
require("dmg" in mac_targets and "zip" in mac_targets, "macOS DMG + ZIP targets")
scripts = pkg.get("scripts") or {}
require(scripts.get("sync:icon") == "node generate_assets.js", "canonical icon sync script")
require("npm run sync:icon" in scripts.get("selftest", ""), "selftest syncs canonical icon")
require("npm run sync:icon" in scripts.get("dist:win", ""), "Windows build syncs canonical icon")
require("--arm64" in scripts.get("dist:mac:arm64", ""), "macOS Apple Silicon build")
require("--x64" in scripts.get("dist:mac:x64", ""), "macOS Intel build")
require((build.get("nsis") or {}).get("createDesktopShortcut") is True, "Windows desktop shortcut")
require(any(x.get("path") == "/Applications" for x in ((build.get("dmg") or {}).get("contents") or [])), "macOS drag-to-Applications installer")

packaged = set(build.get("files") or [])
for name in (
    "bootstrap.js","system_polish.js","network_ux.js","offline.html",
    "lesson_workspace.js","desktop_ux.js","lesson_layout.js","role_startup.js",
    "start.html","start.css","start.js","main.js","preload.js","package.json",
    "build/icon.png",
):
    require(name in packaged, f"packaged {name}")

require("https://adeliatutor.ru/assets/icons/adelia-icon-512.png" in icon_sync, "desktop canonical icon source")
require("roundedRect" not in icon_sync, "desktop icon is not generated artwork")
require("https://adeliatutor.ru/app/" in main, "desktop opens Adelia origin")
require("contextIsolation:true" in main or "contextIsolation: true" in main, "context isolation")
require("nodeIntegration:false" in main or "nodeIntegration: false" in main, "node integration disabled")
require("sandbox:true" in main or "sandbox: true" in main, "renderer sandbox")
require("https://telemost.yandex.ru" in main, "Telemost allowlist")
require("myboard.io" in main and "trustedBoard" in main, "board HTTPS allowlist")
require("requestSingleInstanceLock" in main, "single-instance desktop app")
require("new Tray(" in main, "system tray")
require("closeToTray" in main, "configurable close-to-tray")
require("contextBridge" in preload, "minimal preload bridge")
require("openLessonTool" in preload and "endLessonWorkspace" in preload, "lesson workspace IPC exposed")
require("ipcMain.handle('adelia:lesson-tool'" in main and "ipcMain.handle('adelia:end-lesson-workspace'" in main, "lesson workspace IPC handled")
require("function isStudentCabinetUrl" in workspace and "u.pathname.startsWith('/app/parent/')" in workspace, "desktop polling scoped to student cabinet")

for marker in (
    "require('./system_polish').install()",
    "require('./network_ux').install()",
    "require('./lesson_workspace').install()",
    "require('./desktop_ux').install()",
    "require('./lesson_layout').install()",
    "require('./role_startup').install()",
):
    require(marker in bootstrap, f"bootstrap missing {marker}")

require("loadFile(path.join(__dirname,'start.html'))" in role, "role chooser loads packaged start screen")
require("'/api/auth/teacher/code'" in role, "teacher code login wired")
require("APP_ORIGIN+'/app/parent/'" in role, "parent cabinet wired")
require("APP_ORIGIN+'/api/auth/me'" in role and "role==='teacher'" in role and "role==='parent'" in role and "role==='student'" in role, "authenticated desktop role restored")
require("teacherLogin" in start_js and "openStudentLogin" in start_js and "openParentCabinet" in start_js, "role actions wired")
require("./build/icon.png" in start_html and "start.js" in start_html and "start.css" in start_html, "branded start assets linked")
require(".role" in start_css and ".intro" in start_css, "start screen styles present")
require(
    "Нет подключения" in offline
    and "Аделия" in offline
    and "автоматически" in offline
    and "Проверить подключение" in offline,
    "branded offline screen",
)
require("loadFile(offlineFile())" in network and "setInterval" in network, "offline reconnect loop")
require("removeAllListeners('update-available')" in network and "downloadUpdate" in network, "polished updater flow")
require("setUserTasks" in system, "Windows quick actions")
require("app.dock.setMenu" in system, "macOS dock actions")
require("download-progress" in system and "setProgressBar" in system, "native update progress")
require("HOTKEY = 'CommandOrControl+Shift+A'" in ux, "global Adelia hotkey")
require("setOverlayIcon" in ux, "Windows unread badge")
for mode in ("together","board-focus","mini-video","hide-video"):
    require(mode in layout, f"lesson layout mode {mode}")

require("openLessonTool('meeting'" in individual and "openLessonTool('board'" in individual and "endLessonWorkspace()" in individual, "individual desktop lifecycle")
require("openLessonTool('meeting'" in group and "openLessonTool('board'" in group and "endLessonWorkspace()" in group, "group desktop lifecycle")
require("openLessonTool('meeting'" in event and "openLessonTool('board'" in event and "endLessonWorkspace()" in event, "event desktop lifecycle")
require("started_at:r.started_at" in individual and "Таймер начнётся после прихода ученика" in individual, "individual factual start separation")
require("Доступ открыт — ждём первого ученика" in group, "group factual start separation")
require("Доступ открыт — ждём первого ученика" in event and "Фактический таймер ещё не запущен" in event, "event factual start separation")
for name, source in (("individual",individual),("group",group),("event",event),("telemost_settings",telemost_settings)):
    require("MutationObserver" not in source, f"no persistent MutationObserver in {name}")

require("u.board_url" in teacher_portal, "teacher dashboard exposes canonical student board URL")
require("data-desktop-tool=\"meeting\"" in teacher_dashboard and "data-desktop-tool=\"board\"" in teacher_dashboard, "Today desktop lesson tools wired")
require("openLessonTool(kind,url)" in teacher_dashboard, "Today desktop tools use existing Electron lesson workspace")
require("data-desktop-start" in teacher_dashboard and "/teacher/lesson/open-entry" in teacher_dashboard, "Today desktop direct start uses canonical open-entry")
require("data-desktop-message" in teacher_dashboard and "/teacher/message" in teacher_dashboard, "Today desktop quick message uses canonical teacher messaging")
require("data-desktop-reschedule" in teacher_dashboard and "/teacher/lesson/reschedule" in teacher_dashboard, "Today desktop reschedule uses canonical lesson action")
require("data-desktop-paid" in teacher_dashboard and "/teacher/finance/lesson/paid" in teacher_dashboard, "Today desktop paid action uses canonical payment lifecycle")
require("function desktopModal" in teacher_dashboard and "data-today-message" in teacher_dashboard and "data-today-reschedule" in teacher_dashboard, "Today desktop actions use in-app dialogs")
require("prompt(" not in teacher_dashboard, "Today desktop action center has no browser prompts")
require("confirm(" not in teacher_dashboard and "alert(" not in teacher_dashboard, "Today desktop action center has no browser confirm or alert dialogs")
require("showTodayToast" in teacher_dashboard and "today-desktop-toast" in teacher_dashboard_css, "Today desktop actions use in-app feedback")
require("today-desktop-modal" in teacher_dashboard_css and "desktop-teacher-v2" in teacher_dashboard_css, "Today dialogs are desktop scoped")
require("today-next-actions" in teacher_dashboard and "today-next-actions" in teacher_dashboard_css, "nearest lesson has desktop action center")
require("next.meeting_url" in teacher_dashboard and "next.board_url" in teacher_dashboard, "nearest lesson exposes existing Telemost and board tools")
require("desktop-teacher-v2" in teacher_dashboard_css and "desktop-lesson-tool" in teacher_dashboard_css, "Today desktop action styling isolated")

require("/app/student_clean.css" in student, "student clean shell linked")
require("/app/teacher_clean.css" in teacher and "/app/teacher_clean7.css" in teacher, "teacher clean shell linked")
require("/app/parent/parent_clean.css" in parent, "parent clean shell linked")
require("Adelia-latest-windows-x64.exe" in landing, "Windows desktop recommendation alias linked")
require(
    "Adelia-latest-windows-x64.exe" in landing_html
    and "Adelia-latest-macos-arm64.dmg" in landing_html
    and "Adelia-latest-macos-x64.dmg" in landing_html,
    "stable desktop download aliases linked",
)
require(str(parent_manifest.get("name") or "").startswith("Аделия"), "parent PWA branded Adelia")
icons = parent_manifest.get("icons") or []
require(any(x.get("src") == "/adelia-favicon-32.png" and x.get("sizes") == "32x32" for x in icons), "parent canonical 32 icon")
require(any(x.get("src") == "/adelia-apple-touch-icon-180.png" and x.get("sizes") == "180x180" for x in icons), "parent canonical 180 icon")
require("192x192" not in parent_manifest_text and "512x512" not in parent_manifest_text, "parent manifest does not fake icon sizes")

if errors:
    for error in errors:
        print("FAIL:", error)
    raise SystemExit(1)

print("RC DESKTOP STATIC SELFTEST: OK")
print("desktop package/security/update/deeplink/role/lifecycle invariants present")
