'use strict';
const { contextBridge } = require('electron');
contextBridge.exposeInMainWorld('adeliaDesktop', Object.freeze({
  platform: process.platform,
  desktop: true
}));
