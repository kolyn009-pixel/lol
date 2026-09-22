'use strict';
const { app, BrowserWindow, ipcMain, globalShortcut, nativeImage, net, Notification } = require('electron');
const fs = require('fs');
const path = require('path');

const APP_URL = process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/app/';
const PREFS_FILE = 'desktop-prefs.json';
const HOTKEY = 'CommandOrControl+Shift+A';
let reconnectTimer = null;
let dashboardState = { nextLesson: null, unreadMessages: 0, activeHomework: 0 };
let notifiedLessonId = null;
let notifiedMessageCount = 0;

function prefsPath() { return path.join(app.getPath('userData'), PREFS_FILE); }
function readPrefs() {
  try { return JSON.parse(fs.readFileSync(prefsPath(), 'utf8')); }
  catch (_) { return {}; }
}
function defaults() {
  return {
    closeToTray: true,
    notificationsEnabled: false,
    notificationsChoiceMade: false,
    autostartEnabled: !!app.getLoginItemSettings().openAtLogin,
    hotkeyEnabled: true,
    ...readPrefs(),
  };
}
function writePrefs(next) {
  try {
    fs.mkdirSync(path.dirname(prefsPath()), { recursive: true });
    fs.writeFileSync(prefsPath(), JSON.stringify(next), 'utf8');
  } catch (_) {}
  return next;
}
function mainWindow() {
  return BrowserWindow.getAllWindows().find(w => !w.isDestroyed() && w.getTitle().includes('Аделия')) || BrowserWindow.getAllWindows()[0] || null;
}
function showMain() {
  const win = mainWindow();
  if (!win || win.isDestroyed()) return false;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
  return true;
}
function badgeIcon(count) {
  const text = count > 99 ? '99+' : String(count);
  const width = text.length > 2 ? 40 : 32;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="32"><rect width="100%" height="32" rx="16" fill="#ef4444"/><text x="50%" y="21" text-anchor="middle" font-family="Segoe UI,Arial" font-size="15" font-weight="700" fill="white">${text}</text></svg>`;
  return nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`);
}
function maybeNotify(previous,state) {
  const prefs=defaults();
  if(!prefs.notificationsEnabled||!Notification.isSupported())return;
  const lesson=state.nextLesson;
  if(lesson&&lesson.id&&lesson.start_time){
    const diff=Math.round((new Date(lesson.start_time).getTime()-Date.now())/60000);
    if(diff>=0&&diff<=15&&String(notifiedLessonId)!==String(lesson.id)){
      notifiedLessonId=lesson.id;
      const n=new Notification({title:'Скоро занятие',body:`${lesson.name||'Ученик'} · ${lesson.subject||'Занятие'} через ${diff} мин`});
      n.on('click',()=>{showMain();app.emit('adelia-open-route','home')});n.show();
    }
  }
  const unread=Math.max(0,Number(state.unreadMessages||0)),before=Math.max(0,Number(previous.unreadMessages||0));
  if(unread>before&&unread>notifiedMessageCount){
    notifiedMessageCount=unread;
    const n=new Notification({title:'Новое сообщение в Аделии',body:unread===1?'Есть новое сообщение от ученика.':`Непрочитанных сообщений: ${unread}`});
    n.on('click',()=>{showMain();app.emit('adelia-open-route','chat')});n.show();
  }
  if(unread===0)notifiedMessageCount=0;
}
function updateWindowIndicators(state) {
  const previous={...dashboardState};
  dashboardState = { ...dashboardState, ...state };
  maybeNotify(previous,dashboardState);
  const win = mainWindow();
  if (!win || win.isDestroyed()) return;
  const unread = Math.max(0, Number(dashboardState.unreadMessages || 0));
  if (process.platform === 'win32' && typeof win.setOverlayIcon === 'function') {
    win.setOverlayIcon(unread ? badgeIcon(unread) : null, unread ? `${unread} непрочитанных сообщений` : '');
  }
  const lesson = dashboardState.nextLesson;
  if (lesson && lesson.start_time) {
    const diff = Math.round((new Date(lesson.start_time).getTime() - Date.now()) / 60000);
    if (diff >= 0 && diff <= 30) win.setTitle(`Аделия · ${lesson.subject || 'Занятие'} через ${diff} мин`);
    else win.setTitle('Аделия');
  } else win.setTitle('Аделия');
}
function registerHotkey(enabled) {
  globalShortcut.unregister(HOTKEY);
  if (!enabled) return false;
  try { return globalShortcut.register(HOTKEY, () => showMain()); }
  catch (_) { return false; }
}
function applyPrefs(prefs) {
  app.setLoginItemSettings({ openAtLogin: !!prefs.autostartEnabled, openAsHidden: false });
  registerHotkey(!!prefs.hotkeyEnabled);
  app.emit('adelia-notifications-enabled', !!prefs.notificationsEnabled);
  return prefs;
}
async function onlineCheck() {
  try {
    const r = await net.fetch(APP_URL, { method: 'HEAD', cache: 'no-store' });
    return !!r && r.status < 500;
  } catch (_) { return false; }
}
function startReconnectLoop() {
  if (reconnectTimer) return;
  reconnectTimer = setInterval(async () => {
    const win = mainWindow();
    if (!win || win.isDestroyed()) return;
    const current = win.webContents.getURL();
    if (!current.startsWith('data:text/html')) return;
    if (await onlineCheck()) win.loadURL(APP_URL).catch(() => {});
  }, 5000);
}
function installIpc() {
  ipcMain.handle('adelia:ux-state', () => ({ preferences: defaults(), dashboard: dashboardState, hotkey: HOTKEY }));
  ipcMain.handle('adelia:dashboard-state', (_event, state) => { updateWindowIndicators(state && typeof state==='object'?state:{}); return dashboardState; });
  ipcMain.handle('adelia:set-notifications', (_event, value) => {
    const prefs = writePrefs({ ...defaults(), notificationsEnabled: !!value, notificationsChoiceMade: true });
    applyPrefs(prefs); return prefs;
  });
  ipcMain.handle('adelia:set-autostart', (_event, value) => {
    const prefs = writePrefs({ ...defaults(), autostartEnabled: !!value });
    applyPrefs(prefs); return prefs;
  });
  ipcMain.handle('adelia:set-hotkey', (_event, value) => {
    const prefs = writePrefs({ ...defaults(), hotkeyEnabled: !!value });
    applyPrefs(prefs); return { ...prefs, hotkeyRegistered: globalShortcut.isRegistered(HOTKEY) };
  });
  ipcMain.handle('adelia:show-main', () => showMain());
}
function install() {
  app.on('adelia-dashboard-state', updateWindowIndicators);
  app.whenReady().then(() => {
    applyPrefs(defaults());
    installIpc();
    startReconnectLoop();
    setTimeout(async()=>{
      const prefs=defaults();
      if(prefs.notificationsChoiceMade)return;
      const win=mainWindow();
      const result=await require('electron').dialog.showMessageBox(win||undefined,{type:'info',title:'Уведомления Аделии',message:'Включить уведомления Аделии?',detail:'Аделия сможет напоминать о ближайших занятиях, новых сообщениях, домашней работе и важных изменениях расписания.',buttons:['Включить','Не сейчас'],defaultId:0,cancelId:1,noLink:true});
      const enabled=result.response===0;
      const next=writePrefs({...defaults(),notificationsEnabled:enabled,notificationsChoiceMade:true});
      applyPrefs(next);
      if(enabled&&Notification.isSupported())new Notification({title:'Аделия',body:'Уведомления включены. Важные события теперь не потеряются.'}).show();
    },1800);
  });
  app.on('before-quit', () => {
    if (reconnectTimer) clearInterval(reconnectTimer);
    reconnectTimer = null;
    globalShortcut.unregister(HOTKEY);
  });
}

module.exports = { install, defaults, HOTKEY };
