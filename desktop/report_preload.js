'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('adeliaReport', Object.freeze({
  info: () => ipcRenderer.invoke('adelia:report-info'),
  export: description => ipcRenderer.invoke('adelia:report-export', { description: String(description || '') }),
  close: () => ipcRenderer.invoke('adelia:report-close'),
}));