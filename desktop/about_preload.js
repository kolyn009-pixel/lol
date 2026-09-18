'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('adeliaAbout', Object.freeze({
  getInfo: () => ipcRenderer.invoke('adelia:about-info'),
  checkUpdates: () => ipcRenderer.invoke('adelia:about-check-updates'),
  installUpdate: () => ipcRenderer.invoke('adelia:about-install-update'),
  close: () => ipcRenderer.invoke('adelia:about-close'),
  onUpdateState: callback => {
    if (typeof callback !== 'function') return () => {};
    const fn = (_event, state) => callback(state);
    ipcRenderer.on('adelia:about-update-state', fn);
    return () => ipcRenderer.removeListener('adelia:about-update-state', fn);
  }
}));