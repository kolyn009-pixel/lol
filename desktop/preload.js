'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('adeliaDesktop', Object.freeze({
  platform: process.platform,
  desktop: true,
  openLessonTool: (kind, url) => ipcRenderer.invoke('adelia:lesson-tool', { kind, url }),
  endLessonWorkspace: () => ipcRenderer.invoke('adelia:end-lesson-workspace'),
  openRoute: (route, id = '') => ipcRenderer.invoke('adelia:open-route', { route, id }),
  getPreferences: () => ipcRenderer.invoke('adelia:desktop-prefs'),
  setCloseToTray: value => ipcRenderer.invoke('adelia:set-close-to-tray', !!value)
}));
