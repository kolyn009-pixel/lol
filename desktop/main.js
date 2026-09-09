'use strict';
const { app, BrowserWindow, shell, session, dialog } = require('electron');
const path = require('path');

const APP_URL = process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/';
const APP_ORIGIN = new URL(APP_URL).origin;
const CHILD_ORIGINS = new Set(['https://telemost.yandex.ru']);
let mainWindow = null;
const lessonWindows = new Set();

function originOf(url) {
  try { return new URL(url).origin; } catch (_) { return ''; }
}
function trustedApp(url) { return originOf(url) === APP_ORIGIN; }
function trustedChild(url) { return CHILD_ORIGINS.has(originOf(url)); }
function offlinePage() {
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Аделия — нет сети</title><style>body{margin:0;font-family:system-ui;background:#f7f5fb;color:#241f2b;display:grid;place-items:center;min-height:100vh}.card{max-width:480px;padding:32px;border:1px solid #e5def0;border-radius:24px;background:#fff;box-shadow:0 14px 50px #2c234015}.logo{font-size:30px}.muted{color:#756e80;line-height:1.5}button{border:0;border-radius:14px;padding:12px 18px;background:#7048d8;color:#fff;font:inherit;font-weight:700;cursor:pointer}</style><div class="card"><div class="logo">💜 Аделия</div><h1>Нет подключения к интернету</h1><p class="muted">Кабинет не смог подключиться к adeliatutor.ru. Проверьте интернет и попробуйте ещё раз.</p><button onclick="location.href='${APP_URL}'">Повторить</button></div></html>`);
}

function openLessonWindow(url) {
  const win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 760,
    minHeight: 540,
    title: 'Урок — Аделия',
    parent: mainWindow || undefined,
    backgroundColor: '#ffffff',
    webPreferences: {
      partition: 'persist:adelia-lesson',
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true
    }
  });
  lessonWindows.add(win);
  win.on('closed', () => lessonWindows.delete(win));
  win.webContents.setWindowOpenHandler(({ url: childUrl }) => {
    if (trustedChild(childUrl)) { win.loadURL(childUrl); return { action: 'deny' }; }
    shell.openExternal(childUrl).catch(() => {});
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, nextUrl) => {
    if (!trustedChild(nextUrl)) { event.preventDefault(); shell.openExternal(nextUrl).catch(() => {}); }
  });
  win.loadURL(url);
  return win;
}

function closeLessonWindows() {
  for (const win of [...lessonWindows]) {
    if (!win.isDestroyed()) win.close();
  }
  lessonWindows.clear();
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 620,
    show: false,
    backgroundColor: '#ffffff',
    title: 'Аделия',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      partition: 'persist:adelia',
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false
    }
  });
  mainWindow = win;

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (trustedApp(url)) return { action: 'allow' };
    if (trustedChild(url)) { openLessonWindow(url); return { action: 'deny' }; }
    shell.openExternal(url).catch(() => {});
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!trustedApp(url)) {
      event.preventDefault();
      if (trustedChild(url)) openLessonWindow(url); else shell.openExternal(url).catch(() => {});
    }
  });
  win.webContents.on('did-fail-load', (_e, code, _desc, validatedURL, isMainFrame) => {
    if (isMainFrame && code !== -3 && trustedApp(validatedURL || APP_URL)) win.loadURL(offlinePage());
  });
  win.once('ready-to-show', () => win.show());
  win.on('closed', () => { closeLessonWindows(); if (mainWindow === win) mainWindow = null; });
  win.loadURL(APP_URL);
}

app.whenReady().then(() => {
  const mainSession = session.fromPartition('persist:adelia');
  mainSession.setPermissionRequestHandler((_wc, permission, callback) => {
    callback(['notifications'].includes(permission));
  });
  const lessonSession = session.fromPartition('persist:adelia-lesson');
  lessonSession.setPermissionRequestHandler((wc, permission, callback) => {
    const allowed = trustedChild(wc.getURL()) && ['media', 'microphone', 'camera', 'display-capture'].includes(permission);
    callback(allowed);
  });
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('before-quit', closeLessonWindows);
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
