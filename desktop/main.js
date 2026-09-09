'use strict';
const { app, BrowserWindow, shell, session, dialog, ipcMain, screen } = require('electron');
const { autoUpdater } = require('electron-updater');
const fs = require('fs');
const path = require('path');

const APP_URL = process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/';
const APP_ORIGIN = new URL(APP_URL).origin;
const CHILD_ORIGINS = new Set(['https://telemost.yandex.ru']);
const BOARD_HOSTS = new Set(['myboard.io', 'www.myboard.io']);
const UPDATE_CHECK_MS = 4 * 60 * 60 * 1000;
let mainWindow = null;
let updateTimer = null;
let updateBusy = false;
let meetingWindow = null;
let boardWindow = null;
const lessonWindows = new Set();

function parsed(url) { try { return new URL(url); } catch (_) { return null; } }
function originOf(url) { const u = parsed(url); return u ? u.origin : ''; }
function trustedApp(url) { return originOf(url) === APP_ORIGIN; }
function trustedChild(url) { return CHILD_ORIGINS.has(originOf(url)); }
function trustedBoard(url) { const u = parsed(url); return !!u && u.protocol === 'https:' && BOARD_HOSTS.has(u.hostname); }
function safeExternal(url) { const u = parsed(url); return !!u && ['https:', 'mailto:'].includes(u.protocol); }
function openExternalSafe(url) { if (safeExternal(url)) shell.openExternal(url).catch(() => {}); }
function prefsPath() { return path.join(app.getPath('userData'), 'desktop-prefs.json'); }
function readPrefs() { try { return JSON.parse(fs.readFileSync(prefsPath(), 'utf8')); } catch (_) { return {}; } }
function writePrefs(prefs) { try { fs.mkdirSync(path.dirname(prefsPath()), { recursive: true }); fs.writeFileSync(prefsPath(), JSON.stringify(prefs), 'utf8'); } catch (_) {} }
function offlinePage() { return 'data:text/html;charset=utf-8,' + encodeURIComponent(`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Аделия — нет сети</title><style>body{margin:0;font-family:system-ui;background:#f7f5fb;color:#241f2b;display:grid;place-items:center;min-height:100vh}.card{max-width:480px;padding:32px;border:1px solid #e5def0;border-radius:24px;background:#fff;box-shadow:0 14px 50px #2c234015}.logo{font-size:30px}.muted{color:#756e80;line-height:1.5}button{border:0;border-radius:14px;padding:12px 18px;background:#7048d8;color:#fff;font:inherit;font-weight:700;cursor:pointer}</style><div class="card"><div class="logo">💜 Аделия</div><h1>Нет подключения к интернету</h1><p class="muted">Кабинет не смог подключиться к adeliatutor.ru. Проверьте интернет и попробуйте ещё раз.</p><button onclick="location.href='${APP_URL}'">Повторить</button></div></html>`); }

async function maybeOfferAutostart() {
  if (!app.isPackaged) return;
  const prefs = readPrefs(); if (prefs.autostartAsked) return;
  const result = await dialog.showMessageBox(mainWindow || undefined, { type:'question', title:'Запускать Аделию вместе с компьютером?', message:'Хотите, чтобы Аделия автоматически запускалась при входе в Windows или macOS?', detail:'Это необязательно. Настройку можно изменить позже в системе.', buttons:['Да, запускать','Нет'], defaultId:0, cancelId:1, noLink:true });
  const enabled = result.response === 0;
  app.setLoginItemSettings({ openAtLogin: enabled, openAsHidden: false });
  writePrefs({ ...prefs, autostartAsked:true, autostartEnabled:enabled });
}

function trackLessonWindow(win, kind) {
  lessonWindows.add(win);
  win.on('closed', () => {
    lessonWindows.delete(win);
    if (kind === 'meeting' && meetingWindow === win) meetingWindow = null;
    if (kind === 'board' && boardWindow === win) boardWindow = null;
  });
  return win;
}
function hardenNavigation(win, allowed) {
  win.webContents.setWindowOpenHandler(({ url }) => { if (allowed(url)) { win.loadURL(url); return { action:'deny' }; } openExternalSafe(url); return { action:'deny' }; });
  win.webContents.on('will-navigate', (event, url) => { if (!allowed(url)) { event.preventDefault(); openExternalSafe(url); } });
}
function focusExisting(win) { if (!win || win.isDestroyed()) return false; if (win.isMinimized()) win.restore(); win.show(); win.focus(); return true; }
function lessonDisplay() {
  if (mainWindow && !mainWindow.isDestroyed()) return screen.getDisplayMatching(mainWindow.getBounds());
  return screen.getPrimaryDisplay();
}
function tileLessonWindows() {
  if (!meetingWindow || meetingWindow.isDestroyed() || !boardWindow || boardWindow.isDestroyed()) return;
  const area = lessonDisplay().workArea;
  const gap = 8;
  if (area.width >= 1280) {
    const leftWidth = Math.floor((area.width - gap) * 0.46);
    const rightWidth = area.width - gap - leftWidth;
    meetingWindow.setBounds({ x: area.x, y: area.y, width: leftWidth, height: area.height });
    boardWindow.setBounds({ x: area.x + leftWidth + gap, y: area.y, width: rightWidth, height: area.height });
  } else {
    const topHeight = Math.floor((area.height - gap) * 0.45);
    const bottomHeight = area.height - gap - topHeight;
    meetingWindow.setBounds({ x: area.x, y: area.y, width: area.width, height: topHeight });
    boardWindow.setBounds({ x: area.x, y: area.y + topHeight + gap, width: area.width, height: bottomHeight });
  }
  meetingWindow.show(); boardWindow.show(); boardWindow.focus();
}
function openMeetingWindow(url) {
  if (!trustedChild(url)) return false;
  if (focusExisting(meetingWindow)) { meetingWindow.loadURL(url); tileLessonWindows(); return true; }
  meetingWindow = trackLessonWindow(new BrowserWindow({ width:1050, height:760, minWidth:560, minHeight:400, title:'Телемост — Аделия', backgroundColor:'#ffffff', webPreferences:{ partition:'persist:adelia-lesson', contextIsolation:true, nodeIntegration:false, sandbox:true, webSecurity:true, backgroundThrottling:false } }), 'meeting');
  hardenNavigation(meetingWindow, trustedChild); meetingWindow.loadURL(url); tileLessonWindows(); return true;
}
function openBoardWindow(url) {
  if (!trustedBoard(url)) return false;
  if (focusExisting(boardWindow)) { boardWindow.loadURL(url); tileLessonWindows(); return true; }
  boardWindow = trackLessonWindow(new BrowserWindow({ width:1050, height:760, minWidth:560, minHeight:400, title:'Доска — Аделия', backgroundColor:'#ffffff', webPreferences:{ partition:'persist:adelia-board', contextIsolation:true, nodeIntegration:false, sandbox:true, webSecurity:true, backgroundThrottling:true } }), 'board');
  hardenNavigation(boardWindow, trustedBoard); boardWindow.loadURL(url); tileLessonWindows(); return true;
}
function closeLessonWindows() { for (const win of [...lessonWindows]) if (!win.isDestroyed()) win.close(); lessonWindows.clear(); meetingWindow=null; boardWindow=null; }

function setupAutoUpdates() {
  if (!app.isPackaged) return;
  autoUpdater.autoDownload=false; autoUpdater.autoInstallOnAppQuit=true;
  autoUpdater.on('update-available', async info => { if(updateBusy)return; updateBusy=true; try { const result=await dialog.showMessageBox(mainWindow||undefined,{type:'info',title:'Доступно обновление Аделии',message:`Доступна новая версия ${info.version}.`,detail:'Скачать обновление сейчас? Можно продолжать пользоваться приложением во время загрузки.',buttons:['Скачать','Позже'],defaultId:0,cancelId:1,noLink:true}); if(result.response===0) await autoUpdater.downloadUpdate(); } catch(_){} finally{updateBusy=false;} });
  autoUpdater.on('update-downloaded', async info => { const result=await dialog.showMessageBox(mainWindow||undefined,{type:'info',title:'Обновление готово',message:`Версия ${info.version} загружена.`,detail:'Перезапустить Аделию и установить обновление сейчас?',buttons:['Перезапустить и обновить','Позже'],defaultId:0,cancelId:1,noLink:true}); if(result.response===0){closeLessonWindows();autoUpdater.quitAndInstall(false,true);} });
  const check=()=>{if(updateBusy||lessonWindows.size>0)return;autoUpdater.checkForUpdates().catch(()=>{});}; setTimeout(check,15000); updateTimer=setInterval(check,UPDATE_CHECK_MS);
}

function createWindow() {
  const win=new BrowserWindow({width:1280,height:820,minWidth:900,minHeight:620,show:false,backgroundColor:'#ffffff',title:'Аделия',webPreferences:{preload:path.join(__dirname,'preload.js'),partition:'persist:adelia',contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true,allowRunningInsecureContent:false,backgroundThrottling:true}}); mainWindow=win;
  win.webContents.setWindowOpenHandler(({url})=>{if(trustedApp(url)){win.loadURL(url);return{action:'deny'};}if(trustedChild(url)){openMeetingWindow(url);return{action:'deny'};}if(trustedBoard(url)){openBoardWindow(url);return{action:'deny'};}openExternalSafe(url);return{action:'deny'};});
  win.webContents.on('will-navigate',(event,url)=>{if(!trustedApp(url)){event.preventDefault();if(trustedChild(url))openMeetingWindow(url);else if(trustedBoard(url))openBoardWindow(url);else openExternalSafe(url);}});
  win.webContents.on('did-fail-load',(_e,code,_desc,validatedURL,isMainFrame)=>{if(isMainFrame&&code!==-3&&trustedApp(validatedURL||APP_URL))win.loadURL(offlinePage());});
  win.once('ready-to-show',()=>win.show()); win.on('closed',()=>{closeLessonWindows();if(mainWindow===win)mainWindow=null;}); win.loadURL(APP_URL);
}

app.whenReady().then(async()=>{
  const mainSession=session.fromPartition('persist:adelia'); mainSession.setPermissionCheckHandler(()=>false); mainSession.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  const lessonSession=session.fromPartition('persist:adelia-lesson'); const lessonMediaAllowed=(webContents,permission,requestingOrigin)=>{const origin=requestingOrigin||(webContents?webContents.getURL():'');return trustedChild(origin)&&['media','microphone','camera','display-capture'].includes(permission);}; lessonSession.setPermissionCheckHandler((wc,p,o)=>lessonMediaAllowed(wc,p,o)); lessonSession.setPermissionRequestHandler((wc,p,cb,d)=>cb(lessonMediaAllowed(wc,p,d&&d.requestingUrl)));
  const boardSession=session.fromPartition('persist:adelia-board'); boardSession.setPermissionCheckHandler(()=>false); boardSession.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  ipcMain.handle('adelia:lesson-tool',(event,payload)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return false;if(!payload||typeof payload.url!=='string')return false;if(payload.kind==='meeting')return openMeetingWindow(payload.url);if(payload.kind==='board')return openBoardWindow(payload.url);return false;});
  ipcMain.handle('adelia:end-lesson-workspace',(event)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return false;closeLessonWindows();return true;});
  createWindow(); await maybeOfferAutostart(); setupAutoUpdates(); app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)createWindow();});
});
app.on('before-quit',()=>{if(updateTimer)clearInterval(updateTimer);closeLessonWindows();}); app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit();});
