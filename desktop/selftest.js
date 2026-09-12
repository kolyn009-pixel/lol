'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = __dirname;
const repo = path.resolve(root, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const readRepo = p => fs.readFileSync(path.join(repo, p), 'utf8');
const pkg = JSON.parse(read('package.json'));
const main = read('main.js');
const preload = read('preload.js');
const bootstrap = read('bootstrap.js');
const workspace = read('lesson_workspace.js');
const ux = read('desktop_ux.js');
const layout = read('lesson_layout.js');
const webIndex = readRepo('web/index.html');
const desktopShell = readRepo('web/desktop_shell.js');
const desktopCss = readRepo('web/desktop_shell.css');
const groupsUi = readRepo('web/group_events_ui.js');
const groupsCss = readRepo('web/group_events_ui.css');
const polish = readRepo('web/desktop_polish.js');
const polishCss = readRepo('web/desktop_polish.css');
let failed = false;
function check(ok, label) { console.log(`${ok ? 'OK' : 'FAIL'} ${label}`); if (!ok) failed = true; }
function has(pattern) { return pattern.test(main); }
function parseJs(name, source) {
  try { new vm.Script(source, { filename: name }); check(true, `syntax ${name}`); }
  catch (e) { console.error(e.stack || e); check(false, `syntax ${name}`); }
}

for (const [name, source] of [
  ['bootstrap.js', bootstrap], ['main.js', main], ['preload.js', preload],
  ['lesson_workspace.js', workspace], ['desktop_ux.js', ux], ['lesson_layout.js', layout],
  ['web/desktop_shell.js', desktopShell], ['web/group_events_ui.js', groupsUi], ['web/desktop_polish.js', polish]
]) parseJs(name, source);

check(pkg.main === 'bootstrap.js', 'desktop bootstrap entry');
check(pkg.build && pkg.build.appId === 'ru.adeliatutor.desktop', 'stable app id');
check(pkg.build && pkg.build.asar === true, 'asar enabled');
check(pkg.devDependencies.electron === '38.0.0', 'Electron pinned');
check(pkg.devDependencies['electron-builder'] === '26.0.12', 'electron-builder pinned');
check(pkg.dependencies && pkg.dependencies['electron-updater'] === '6.6.2', 'electron-updater pinned');
check(pkg.build.publish && pkg.build.publish[0].provider === 'generic', 'generic update provider');
check(pkg.build.publish && pkg.build.publish[0].url === 'https://adeliatutor.ru/desktop-updates/', 'trusted update endpoint');
check(pkg.build.protocols && pkg.build.protocols[0].schemes.includes('adelia'), 'adelia deep link protocol registered');
check(Array.isArray(pkg.build.mac.target) && pkg.build.mac.target.includes('zip'), 'mac updater zip target');
check(pkg.build.win && pkg.build.win.target.includes('nsis'), 'Windows NSIS target');
check(pkg.build.nsis && pkg.build.nsis.createDesktopShortcut === true, 'Windows desktop shortcut');
for (const f of ['bootstrap.js','lesson_workspace.js','desktop_ux.js','lesson_layout.js','main.js','preload.js','package.json']) check(pkg.build.files.includes(f), `packaged ${f}`);

check(main.includes('https://adeliatutor.ru/app/'), 'desktop opens cabinet directly');
check(has(/contextIsolation\s*:\s*true/), 'context isolation');
check(has(/nodeIntegration\s*:\s*false/), 'node integration disabled');
check(has(/sandbox\s*:\s*true/), 'renderer sandbox');
check(main.includes('https://telemost.yandex.ru'), 'Telemost allowlist');
check(main.includes('myboard.io') && main.includes('trustedBoard'), 'board HTTPS allowlist');
check(has(/\['media','microphone','camera'\]/), 'lesson media permissions limited to camera/microphone');
check(!main.includes('display-capture'), 'screen capture permission denied by default');
check(main.includes('persist:adelia-board') && main.includes('boardSession.setPermissionCheckHandler(()=>false)'), 'board permissions denied');
check(main.includes("['https:', 'mailto:']"), 'external protocols allowlisted');
check(main.includes('did-fail-load'), 'offline fallback');
check(has(/backgroundThrottling\s*:\s*true/), 'idle cabinet background throttling');
check(has(/backgroundThrottling\s*:\s*false/), 'lesson media stays live in background');
check(main.includes('lessonWindows.size>0') || main.includes('lessonWindows.size > 0'), 'updates skipped during lessons');
check(main.includes('UPDATE_CHECK_MS = 4 * 60 * 60 * 1000'), 'low-frequency update polling');
check(main.includes('autoUpdater.autoDownload=false') || main.includes('autoUpdater.autoDownload = false'), 'updates require user consent');
check(main.includes('autoUpdater.quitAndInstall'), 'downloaded update install flow');
check(main.includes("ipcMain.handle('adelia:lesson-tool'") && preload.includes("ipcRenderer.invoke('adelia:lesson-tool'"), 'safe lesson IPC bridge');
check(main.includes("ipcMain.handle('adelia:end-lesson-workspace'") && preload.includes("ipcRenderer.invoke('adelia:end-lesson-workspace'"), 'lesson workspace close bridge');
check(main.includes('tileLessonWindows') && main.includes('screen.getDisplayMatching'), 'lesson windows tiled on active display');
check(main.includes('requestSingleInstanceLock') && main.includes("app.on('second-instance'"), 'single-instance desktop app');
check(main.includes('new Tray(') && main.includes('createTray'), 'system tray');
check(main.includes('closeToTray') && main.includes("win.on('close'"), 'configurable close-to-tray');
check(main.includes('setAsDefaultProtocolClient') && main.includes('parseDeepLink'), 'deep links handled');
check(main.includes("'chat'") && main.includes("'homework'") && main.includes("'lesson'"), 'deep link route allowlist');
check(preload.includes('contextBridge'), 'minimal preload bridge');

check(bootstrap.includes("require('./lesson_workspace').install()"), 'lesson workspace bootstrap installed');
check(bootstrap.includes("require('./desktop_ux').install()"), 'desktop UX bootstrap installed');
check(bootstrap.includes("require('./lesson_layout').install()"), 'lesson layout bootstrap installed');
check(bootstrap.includes("require('./main')"), 'main process bootstrap installed');
check(workspace.includes("fetch('/api/student/dashboard'") && workspace.includes('REMINDER_MINUTES = [15, 5]'), 'dashboard-backed 15/5 minute reminders');
check(workspace.includes('new Notification(') && workspace.includes("n.on('click'"), 'native lesson notification opens lesson');
check(workspace.includes("u.searchParams.set('desktop', 'lesson')"), 'notification targets lesson route');
check(ux.includes("HOTKEY = 'CommandOrControl+Shift+A'"), 'global Adelia hotkey');
check(ux.includes('setOverlayIcon'), 'Windows unread badge');
check(ux.includes('startReconnectLoop'), 'offline reconnect loop');
check(layout.includes("'together','board-focus','mini-video','hide-video'"), 'all lesson layout modes');
check(layout.includes("CommandOrControl+Shift+B") && layout.includes("CommandOrControl+Shift+V") && layout.includes("CommandOrControl+Shift+L"), 'lesson layout shortcuts');
check(layout.includes('rememberMode') && layout.includes('lessonLayout'), 'lesson layout persistence');
check(preload.includes('setLessonLayout') && preload.includes('toggleLessonVideo'), 'lesson layout preload bridge');

check(webIndex.includes('/app/desktop_shell.css') && webIndex.includes('/app/desktop_shell.js'), 'desktop shell web assets loaded');
check(webIndex.includes('/app/group_events_ui.css') && webIndex.includes('/app/group_events_ui.js'), 'groups/events web assets loaded');
check(webIndex.includes('/app/desktop_polish.css') && webIndex.includes('/app/desktop_polish.js'), 'desktop polish web assets loaded');
check(desktopShell.includes('window.adeliaDesktop?.desktop'), 'desktop shell isolated from browser/PWA');
check(desktopShell.includes('Ctrl K') && desktopShell.includes('desktopSearch'), 'desktop quick search');
check(desktopCss.includes('.desktop-status-strip') && desktopCss.includes('desktop-compact'), 'desktop dashboard and compact sidebar styles');
check(groupsUi.includes("api('/student/events')") && groupsUi.includes("api('/student/groups')"), 'events and groups APIs integrated');
check(groupsUi.includes("/student/event/register") && groupsUi.includes("/student/event/invite/respond"), 'event registration and invitation flow');
check(groupsUi.includes("/student/group/chat") && groupsUi.includes("/student/group-lesson/enter"), 'group chat and live entry');
check(groupsUi.includes("window.adeliaDesktop.openLessonTool('meeting'") && groupsUi.includes("window.adeliaDesktop.openLessonTool('board'"), 'group/event lesson workspace integration');
check(groupsCss.includes('.event-card') && groupsCss.includes('.group-chat'), 'groups/events responsive styles');
check(polish.includes("data-layout=\"mini-video\"") && polish.includes("data-layout=\"hide-video\""), 'lesson toolbar layout controls');
check(polish.includes('settingNotifications') && polish.includes('settingAutostart') && polish.includes('settingTray'), 'Windows settings dialog controls');
check(polishCss.includes(':focus-visible') && polishCss.includes('prefers-reduced-motion'), 'keyboard focus and reduced motion support');

if (failed) process.exit(1);
console.log('Desktop release selftest passed.');
