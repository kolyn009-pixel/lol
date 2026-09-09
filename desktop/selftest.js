'use strict';
const fs = require('fs');
const path = require('path');

const root = __dirname;
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const main = fs.readFileSync(path.join(root, 'main.js'), 'utf8');
const preload = fs.readFileSync(path.join(root, 'preload.js'), 'utf8');
let failed = false;
function check(ok, label) { console.log(`${ok ? 'OK' : 'FAIL'} ${label}`); if (!ok) failed = true; }
function has(pattern) { return pattern.test(main); }

check(pkg.main === 'main.js', 'main entry');
check(pkg.build && pkg.build.appId === 'ru.adeliatutor.desktop', 'stable app id');
check(pkg.build && pkg.build.asar === true, 'asar enabled');
check(pkg.devDependencies.electron === '38.0.0', 'Electron pinned');
check(pkg.devDependencies['electron-builder'] === '26.0.12', 'electron-builder pinned');
check(pkg.dependencies && pkg.dependencies['electron-updater'] === '6.6.2', 'electron-updater pinned');
check(pkg.build.publish && pkg.build.publish[0].provider === 'generic', 'generic update provider');
check(pkg.build.publish && pkg.build.publish[0].url === 'https://adeliatutor.ru/desktop-updates/', 'trusted update endpoint');
check(Array.isArray(pkg.build.mac.target) && pkg.build.mac.target.includes('zip'), 'mac updater zip target');
check(main.includes('https://adeliatutor.ru/'), 'production HTTPS origin');
check(has(/contextIsolation\s*:\s*true/), 'context isolation');
check(has(/nodeIntegration\s*:\s*false/), 'node integration disabled');
check(has(/sandbox\s*:\s*true/), 'renderer sandbox');
check(main.includes('https://telemost.yandex.ru'), 'Telemost allowlist');
check(main.includes("myboard.io") && main.includes('trustedBoard'), 'board HTTPS allowlist');
check(has(/\['media','microphone','camera','display-capture'\]/), 'lesson media permissions explicit');
check(main.includes("persist:adelia-board") && main.includes('boardSession.setPermissionCheckHandler(()=>false)'), 'board permissions denied');
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
check(preload.includes('contextBridge'), 'minimal preload bridge');

if (failed) process.exit(1);
console.log('Desktop selftest passed.');
