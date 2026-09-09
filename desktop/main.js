'use strict';
const { app, BrowserWindow, shell, session } = require('electron');
const path = require('path');

const APP_URL = process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/';
const APP_ORIGIN = new URL(APP_URL).origin;

function trusted(url) {
  try { return new URL(url).origin === APP_ORIGIN; } catch (_) { return false; }
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

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (trusted(url)) return { action: 'allow' };
    shell.openExternal(url).catch(() => {});
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!trusted(url)) {
      event.preventDefault();
      shell.openExternal(url).catch(() => {});
    }
  });
  win.once('ready-to-show', () => win.show());
  win.loadURL(APP_URL);
}

app.whenReady().then(() => {
  session.fromPartition('persist:adelia').setPermissionRequestHandler((_wc, permission, callback) => {
    callback(['notifications'].includes(permission));
  });
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
