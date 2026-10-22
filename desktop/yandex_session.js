'use strict';
// The lesson session never receives the Adelia preload or account credentials.
const { BrowserWindow, session, shell, dialog } = require('electron');
const AUTH_HOSTS = new Set(['telemost.yandex.ru', 'passport.yandex.ru', 'passport.yandex.com', 'id.yandex.ru', 'id.yandex.com', 'oauth.yandex.ru', 'oauth.yandex.com']);
const PARTITION = 'persist:adelia-lesson';
function allowed(raw) {
  try { const u = new URL(raw); return u.protocol === 'https:' && !u.username && !u.password && AUTH_HOSTS.has(u.hostname) && (!u.port || u.port === '443'); } catch { return false; }
}
function isMeeting(raw) { try { return allowed(raw) && new URL(raw).hostname === 'telemost.yandex.ru'; } catch { return false; } }
function configureSession() {
  const s = session.fromPartition(PARTITION);
  // Use the bundled Chromium's normal web UA for compatibility with Yandex web.
  s.setUserAgent(s.getUserAgent().replace(/\s+(?:Electron|adelia-desktop|Аделия)\/[^\s]+/gi, ''));
  return s;
}
function attach(win, initialUrl) {
  let target = initialUrl, timer = null, reporting = false;
  const clear = () => { if (timer) clearTimeout(timer); timer = null; };
  const external = raw => { if (allowed(raw)) return shell.openExternal(raw); return Promise.resolve(); };
  async function failure() {
    clear(); if (win.isDestroyed() || reporting) return;
    reporting = true;
    try {
      const result = await dialog.showMessageBox(win, { type:'warning', title:'Подключение к Телемосту', message:'Телемост не завершил загрузку.', detail:'Можно повторить подключение или открыть эту встречу в браузере. Вход в Яндекс выполняется на странице Яндекса.', buttons:['Повторить','Открыть в браузере','Закрыть'], defaultId:0, cancelId:2, noLink:true });
      if (win.isDestroyed()) return;
      if (result.response === 0) win.loadURL(target).catch(failure);
      else if (result.response === 1) { await external(target); win.close(); }
      else win.close();
    } finally { reporting = false; }
  }
  win.webContents.on('will-navigate', (event, url) => { if (!allowed(url)) event.preventDefault(); });
  win.webContents.on('will-redirect', (event, url) => { if (!allowed(url)) event.preventDefault(); });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!allowed(url)) return { action:'deny' };
    return { action:'allow', overrideBrowserWindowOptions:{ width:620, height:780, parent:win, autoHideMenuBar:true, webPreferences:{ partition:PARTITION, contextIsolation:true, nodeIntegration:false, sandbox:true, webSecurity:true } } };
  });
  win.webContents.on('did-create-window', child => attach(child, child.webContents.getURL() || target));
  win.webContents.on('did-start-navigation', (_event, url, _inPlace, isMainFrame) => {
    if (!isMainFrame) return;
    if (isMeeting(url)) target = url;
    clear(); timer = setTimeout(failure, 30000);
  });
  win.webContents.on('did-stop-loading', clear);
  win.webContents.on('did-fail-load', (_event, code, _description, _url, isMainFrame) => { if (isMainFrame && code !== -3) failure(); });
  win.webContents.on('render-process-gone', failure);
  win.on('closed', clear);
  return win;
}
module.exports = { allowed, isMeeting, configureSession, attach, PARTITION };
