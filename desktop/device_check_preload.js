'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('adeliaDeviceCheck',Object.freeze({
  complete:()=>ipcRenderer.invoke('adelia:device-check-complete'),
  cancel:()=>ipcRenderer.invoke('adelia:device-check-cancel')
}));
