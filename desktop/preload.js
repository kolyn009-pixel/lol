'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('adeliaDesktop', Object.freeze({
  platform: process.platform,
  desktop: true,
  openLessonTool: (kind, url) => ipcRenderer.invoke('adelia:lesson-tool', { kind, url }),
  endLessonWorkspace: () => ipcRenderer.invoke('adelia:end-lesson-workspace')
}));
