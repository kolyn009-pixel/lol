'use strict';
const { app, BrowserWindow, dialog, net } = require('electron');
const path = require('path');

const APP_URL = process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/app/';
let installed = false;
let retryTimers = new WeakMap();

function isMain(win) {
  return !!win && !win.isDestroyed() && !/Телемост|Доска/.test(win.getTitle());
}
function offlineFile() { return path.join(__dirname, 'offline.html'); }
function clearRetry(win) {
  const timer = retryTimers.get(win);
  if (timer) clearInterval(timer);
  retryTimers.delete(win);
}
async function online() {
  try {
    const response = await net.fetch(APP_URL, { method: 'HEAD', cache: 'no-store' });
    return response.status > 0 && response.status < 500;
  } catch (_) { return false; }
}
function reconnect(win) {
  if (!isMain(win) || retryTimers.has(win)) return;
  const timer = setInterval(async () => {
    if (!isMain(win)) return clearRetry(win);
    if (await online()) {
      clearRetry(win);
      try {
        await require('./role_startup').restoreAuthenticatedRole();
      } catch (_) {
        win.loadFile(path.join(__dirname, 'start.html')).catch(() => {});
      }
    }
  }, 5000);
  retryTimers.set(win, timer);
}
function showOffline(win) {
  if (!isMain(win)) return;
  setImmediate(() => {
    if (!isMain(win)) return;
    win.loadFile(offlineFile()).catch(() => {});
    reconnect(win);
  });
}
function installNetworkUx() {
  app.on('browser-window-created', (_event, win) => {
    win.webContents.on('did-fail-load', (_e, code, _description, _url, isMainFrame) => {
      if (!isMainFrame || code === -3) return;
      showOffline(win);
    });
    win.webContents.on('did-finish-load', () => {
      const current = win.webContents.getURL();
      if (current.startsWith('http')) clearRetry(win);
    });
    win.on('closed', () => clearRetry(win));
  });
}
function install() {
  if (installed) return;
  installed = true;
  installNetworkUx();
  app.on('before-quit', () => {
    for (const win of BrowserWindow.getAllWindows()) clearRetry(win);
  });
}

module.exports = { install };
