'use strict';
const fs = require('fs');
const path = require('path');

const root = __dirname;
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const main = fs.readFileSync(path.join(root, 'main.js'), 'utf8');
const preload = fs.readFileSync(path.join(root, 'preload.js'), 'utf8');
let failed = false;
function check(ok, label) {
  console.log(`${ok ? 'OK' : 'FAIL'} ${label}`);
  if (!ok) failed = true;
}

check(pkg.main === 'main.js', 'main entry');
check(pkg.build && pkg.build.appId === 'ru.adeliatutor.desktop', 'stable app id');
check(pkg.build && pkg.build.asar === true, 'asar enabled');
check(pkg.devDependencies.electron === '38.0.0', 'Electron pinned');
check(pkg.devDependencies['electron-builder'] === '26.0.12', 'electron-builder pinned');
check(main.includes("https://adeliatutor.ru/"), 'production HTTPS origin');
check(main.includes('contextIsolation: true'), 'context isolation');
check(main.includes('nodeIntegration: false'), 'node integration disabled');
check(main.includes('sandbox: true'), 'renderer sandbox');
check(main.includes("https://telemost.yandex.ru"), 'Telemost allowlist');
check(main.includes("['media', 'microphone', 'camera', 'display-capture']"), 'lesson media permissions explicit');
check(main.includes('shell.openExternal'), 'untrusted links external');
check(main.includes('did-fail-load'), 'offline fallback');
check(preload.includes('contextBridge'), 'minimal preload bridge');

if (failed) process.exit(1);
console.log('Desktop selftest passed.');
