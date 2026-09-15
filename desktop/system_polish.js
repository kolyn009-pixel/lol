'use strict';
const { app, BrowserWindow, Menu } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');

const ORIGIN = new URL(process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/app/').origin;
let installed = false;

function mainWindow() {
  return BrowserWindow.getAllWindows().find(w => !w.isDestroyed() && w.getTitle().includes('Аделия')) || BrowserWindow.getAllWindows()[0] || null;
}
function deep(route) { return `adelia://${route}`; }
function clearProgress() {
  const win = mainWindow();
  if (win && !win.isDestroyed()) win.setProgressBar(-1);
}
function installPlatformActions() {
  if (process.platform === 'win32') {
    app.setUserTasks([
      { program: process.execPath, arguments: deep('schedule'), iconPath: process.execPath, iconIndex: 0, title: 'Расписание', description: 'Открыть расписание Аделии' },
      { program: process.execPath, arguments: deep('homework'), iconPath: process.execPath, iconIndex: 0, title: 'Домашние задания', description: 'Открыть домашние задания' },
      { program: process.execPath, arguments: deep('chat'), iconPath: process.execPath, iconIndex: 0, title: 'Сообщения', description: 'Открыть сообщения' }
    ]).catch(() => {});
  }
  if (process.platform === 'darwin' && app.dock) {
    app.dock.setMenu(Menu.buildFromTemplate([
      { label: 'Открыть Аделию', click: () => app.emit('adelia-open-route', 'home') },
      { label: 'Расписание', click: () => app.emit('adelia-open-route', 'schedule') },
      { label: 'Домашние задания', click: () => app.emit('adelia-open-route', 'homework') },
      { label: 'Сообщения', click: () => app.emit('adelia-open-route', 'chat') }
    ]));
  }
}
function installWindowPolish() {
  app.on('browser-window-created', (_event, win) => {
    if (win.isDestroyed()) return;
    win.setTitle('Аделия');
    if (process.platform === 'darwin') {
      win.setFullScreenable(true);
      try { win.setWindowButtonVisibility(true); } catch (_) {}
    }
    win.webContents.on('did-start-loading', () => {
      if (!win.isDestroyed() && win === mainWindow()) win.setProgressBar(2, { mode: 'indeterminate' });
    });
    win.webContents.on('did-stop-loading', () => {
      if (!win.isDestroyed()) win.setProgressBar(-1);
    });
    win.webContents.on('page-title-updated', (event, title) => {
      if (!title || /chrome|electron|error/i.test(title)) {
        event.preventDefault();
        win.setTitle('Аделия');
      }
    });
  });
}
function installUpdateProgress() {
  autoUpdater.on('download-progress', info => {
    const win = mainWindow();
    if (!win || win.isDestroyed()) return;
    const fraction = Math.max(0, Math.min(1, Number(info.percent || 0) / 100));
    win.setProgressBar(fraction);
    win.setTitle(`Аделия · обновление ${Math.round(fraction * 100)}%`);
  });
  autoUpdater.on('update-downloaded', () => {
    clearProgress();
    const win = mainWindow();
    if (win && !win.isDestroyed()) win.setTitle('Аделия');
  });
  autoUpdater.on('error', () => {
    clearProgress();
    const win = mainWindow();
    if (win && !win.isDestroyed()) win.setTitle('Аделия');
  });
}
function install() {
  if (installed) return;
  installed = true;
  app.setName('Аделия');
  installWindowPolish();
  installUpdateProgress();
  app.whenReady().then(() => {
    installPlatformActions();
    if (process.platform === 'darwin' && app.dock) {
      const icon = path.join(__dirname, 'build', 'icon.png');
      try { app.dock.setIcon(icon); } catch (_) {}
    }
  }).catch(() => {});
}

module.exports = { install, ORIGIN };
