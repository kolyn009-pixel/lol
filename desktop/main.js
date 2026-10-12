'use strict';
const { app, BrowserWindow, shell, session, dialog, ipcMain, screen, Tray, Menu, nativeImage } = require('electron');
const { autoUpdater } = require('electron-updater');
const fs = require('fs');
const path = require('path');

const APP_URL = process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/app/';
const APP_ORIGIN = new URL(APP_URL).origin;
const CHILD_ORIGINS = new Set(['https://telemost.yandex.ru']);
const BOARD_HOSTS = new Set(['myboard.io', 'www.myboard.io']);
const UPDATE_CHECK_MS = 4 * 60 * 60 * 1000;
const UPDATE_CHANNEL = process.env.ADELIA_UPDATE_CHANNEL === 'stable' ? 'stable' : 'beta';
const UPDATE_TARGET = process.platform === 'win32' ? 'win-x64' : (process.platform === 'darwin' ? `macos-${process.arch}` : `linux-${process.arch}`);
const UPDATE_BASE_URL = `https://adeliatutor.ru/desktop-updates/${UPDATE_CHANNEL}/${UPDATE_TARGET}/`;
const PROTOCOL = 'adelia';
let mainWindow = null;
let updateTimer = null;
let updateBusy = false;
let meetingWindow = null;
let boardWindow = null;
let deviceCheckWindow = null;
let deviceCheckLessonId = '';
let aboutWindow = null;
let updateState = { status:'idle' };
let tray = null;
let isQuitting = false;
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
function prefsWithDefaults() { return { closeToTray: true, ...readPrefs() }; }
function savePref(key, value) { const prefs = prefsWithDefaults(); prefs[key] = value; writePrefs(prefs); refreshTrayMenu(); return prefs; }
function visibleBounds(bounds) {
  if (!bounds || !Number.isFinite(bounds.x) || !Number.isFinite(bounds.y) || !Number.isFinite(bounds.width) || !Number.isFinite(bounds.height)) return null;
  const displays = screen.getAllDisplays();
  const visible = displays.some(d => {
    const a=d.workArea;
    const ix=Math.max(0,Math.min(bounds.x+bounds.width,a.x+a.width)-Math.max(bounds.x,a.x));
    const iy=Math.max(0,Math.min(bounds.y+bounds.height,a.y+a.height)-Math.max(bounds.y,a.y));
    return ix>=160 && iy>=120;
  });
  return visible ? bounds : null;
}
function savedMainBounds() {
  const b=visibleBounds(readPrefs().mainWindowBounds);
  if (!b) return null;
  return {
    x:Math.round(b.x),y:Math.round(b.y),
    width:Math.max(900,Math.round(b.width)),height:Math.max(620,Math.round(b.height))
  };
}
function rememberMainBounds(win) {
  if (!win || win.isDestroyed() || win.isMinimized() || win.isMaximized() || win.isFullScreen()) return;
  const p=prefsWithDefaults();
  p.mainWindowBounds=win.getBounds();
  writePrefs(p);
}
function offlinePage() { return 'data:text/html;charset=utf-8,' + encodeURIComponent(`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Аделия — нет сети</title><style>body{margin:0;font-family:system-ui;background:#f7f5fb;color:#241f2b;display:grid;place-items:center;min-height:100vh}.card{max-width:480px;padding:32px;border:1px solid #e5def0;border-radius:24px;background:#fff;box-shadow:0 14px 50px #2c234015}.logo{font-size:30px}.muted{color:#756e80;line-height:1.5}button{border:0;border-radius:14px;padding:12px 18px;background:#7048d8;color:#fff;font:inherit;font-weight:700;cursor:pointer}</style><div class="card"><div class="logo">💜 Аделия</div><h1>Нет подключения к интернету</h1><p class="muted">Кабинет не смог подключиться к adeliatutor.ru. Проверьте интернет и попробуйте ещё раз.</p><button onclick="location.href='${APP_URL}'">Повторить</button></div></html>`); }

function appPath(pathname = '/', params = {}) {
  const url = new URL(APP_URL);
  url.pathname = pathname.startsWith('/') ? pathname : `/${pathname}`;
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, String(value));
  return url.toString();
}
function routeUrl(route, id) {
  const key = String(route || '').toLowerCase();
  if (key === 'home' || key === 'app') return APP_URL;
  if (key === 'chat') return appPath('/app/', { desktop: 'chat' });
  if (key === 'homework') return appPath('/app/', { desktop: 'homework', id });
  if (key === 'lesson') return appPath('/app/', { desktop: 'lesson', id });
  if (key === 'schedule') return appPath('/app/', { desktop: 'schedule' });
  if (key === 'finance') return appPath('/app/', { desktop: 'finance' });
  return APP_URL;
}
function parseDeepLink(raw) {
  const u = parsed(raw);
  if (!u || u.protocol !== `${PROTOCOL}:`) return null;
  const route = (u.hostname || u.pathname.split('/').filter(Boolean)[0] || 'home').toLowerCase();
  const parts = u.pathname.split('/').filter(Boolean);
  const id = parts[0] && route === u.hostname ? parts[0] : parts[1] || parts[0] || u.searchParams.get('id') || '';
  return { route, id, target: routeUrl(route, id) };
}
function deepLinkFromArgv(argv) { return (argv || []).find(x => typeof x === 'string' && x.toLowerCase().startsWith(`${PROTOCOL}://`)); }
function restoreMainRole() {
  try { return require('./role_startup').restoreAuthenticatedRole(); } catch (_) { return Promise.resolve(false); }
}
function showMain(target = null) {
  if (!mainWindow || mainWindow.isDestroyed()) createWindow(target);
  else {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
    if (target && trustedApp(target) && mainWindow.webContents.getURL() !== target) mainWindow.loadURL(target);
    else if (!target) restoreMainRole().catch(() => {});
  }
}
function handleDeepLink(raw) { const link = parseDeepLink(raw); if (!link) return false; showMain(link.target); return true; }

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
function closeLessonWindows(focusMain=false) {
  for (const win of [...lessonWindows]) if (!win.isDestroyed()) win.close();
  lessonWindows.clear(); meetingWindow=null; boardWindow=null;
  if (focusMain && mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show(); mainWindow.focus();
  }
}

function openDeviceCheck(lessonId='') {
  deviceCheckLessonId=String(lessonId||'');
  if (focusExisting(deviceCheckWindow)) return true;
  deviceCheckWindow=new BrowserWindow({
    width:920,height:690,minWidth:760,minHeight:600,
    parent:mainWindow&&!mainWindow.isDestroyed()?mainWindow:undefined,
    modal:false,show:false,title:'Проверка перед занятием — Аделия',
    backgroundColor:'#f5f3f8',
    webPreferences:{
      preload:path.join(__dirname,'device_check_preload.js'),
      partition:'persist:adelia-device-check',
      contextIsolation:true,nodeIntegration:false,sandbox:true,
      webSecurity:true,backgroundThrottling:false
    }
  });
  deviceCheckWindow.setMenuBarVisibility(false);
  deviceCheckWindow.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  deviceCheckWindow.webContents.on('will-navigate',event=>event.preventDefault());
  deviceCheckWindow.once('ready-to-show',()=>deviceCheckWindow&&!deviceCheckWindow.isDestroyed()&&deviceCheckWindow.show());
  deviceCheckWindow.on('closed',()=>{deviceCheckWindow=null;deviceCheckLessonId=''});
  deviceCheckWindow.loadFile(path.join(__dirname,'device_check.html'));
  return true;
}

function buildSha() {
  return String(process.env.ADELIA_BUILD_SHA || process.env.GITHUB_SHA || require('./package.json').adeliaBuildSha || '').trim().slice(0,12) || null;
}
function sendUpdateState(next) {
  updateState={...updateState,...next};
  if (aboutWindow && !aboutWindow.isDestroyed()) aboutWindow.webContents.send('adelia:about-update-state', updateState);
  return updateState;
}
function openAboutWindow() {
  if (focusExisting(aboutWindow)) return true;
  aboutWindow=new BrowserWindow({
    width:730,height:590,minWidth:560,minHeight:520,show:false,
    parent:mainWindow&&!mainWindow.isDestroyed()?mainWindow:undefined,
    title:'Об Аделии',backgroundColor:'#f5f3f8',
    webPreferences:{preload:path.join(__dirname,'about_preload.js'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}
  });
  aboutWindow.setMenuBarVisibility(false);
  aboutWindow.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  aboutWindow.webContents.on('will-navigate',event=>event.preventDefault());
  aboutWindow.once('ready-to-show',()=>aboutWindow&&!aboutWindow.isDestroyed()&&aboutWindow.show());
  aboutWindow.on('closed',()=>{aboutWindow=null});
  aboutWindow.loadFile(path.join(__dirname,'about.html'));
  return true;
}

function trayIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" rx="9" fill="#7650d8"/><path d="M16 25S6 19.2 6 12.4C6 8.9 8.6 7 11.3 7c2 0 3.7 1 4.7 2.5C17 8 18.7 7 20.7 7 23.4 7 26 8.9 26 12.4 26 19.2 16 25 16 25Z" fill="white"/></svg>`;
  return nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`).resize({ width: 24, height: 24 });
}
function refreshTrayMenu() {
  if (!tray || tray.isDestroyed()) return;
  const prefs = prefsWithDefaults();
  tray.setContextMenu(Menu.buildFromTemplate([
    { label:'Открыть Аделию', click:()=>showMain(APP_URL) },
    { label:'Ближайшее занятие', click:()=>showMain(routeUrl('schedule')) },
    { label:'Сообщения', click:()=>showMain(routeUrl('chat')) },
    { label:'Домашние задания', click:()=>showMain(routeUrl('homework')) },
    { type:'separator' },
    { label:'Сворачивать в трей при закрытии', type:'checkbox', checked:!!prefs.closeToTray, click:item=>savePref('closeToTray', !!item.checked) },
    { label:'Об Аделии и обновления', click:()=>openAboutWindow() },
    { label:'Сообщить о проблеме', click:()=>{ try { require('./diagnostics').openReportWindow(); } catch (_) {} } },
    { type:'separator' },
    { label:'Выйти из Аделии', click:()=>{ isQuitting=true; app.quit(); } }
  ]));
}
function createTray() {
  if (tray && !tray.isDestroyed()) return;
  tray = new Tray(trayIcon());
  tray.setToolTip('Аделия');
  tray.on('click',()=>showMain(APP_URL));
  tray.on('double-click',()=>showMain(APP_URL));
  refreshTrayMenu();
}

function setupAutoUpdates() {
  autoUpdater.autoDownload=false; autoUpdater.autoInstallOnAppQuit=true;
  autoUpdater.channel=UPDATE_CHANNEL;
  autoUpdater.allowPrerelease=UPDATE_CHANNEL==='beta';
  autoUpdater.setFeedURL({provider:'generic',url:UPDATE_BASE_URL,channel:UPDATE_CHANNEL});
  autoUpdater.on('checking-for-update',()=>sendUpdateState({status:'checking'}));
  autoUpdater.on('update-not-available',()=>sendUpdateState({status:'current'}));
  autoUpdater.on('download-progress',info=>sendUpdateState({status:'downloading',percent:Number(info.percent||0)}));
  autoUpdater.on('error',err=>sendUpdateState({status:'error',message:err&&err.message?String(err.message).slice(0,180):'Не удалось проверить обновления.'}));
  if (!app.isPackaged) { sendUpdateState({status:'current'}); return; }
  autoUpdater.on('update-available', async info => { sendUpdateState({status:'available',version:info.version}); if(updateBusy)return; updateBusy=true; try { const result=await dialog.showMessageBox(mainWindow||undefined,{type:'info',title:'Доступно обновление Аделии',message:`Доступна новая версия ${info.version}.`,detail:'Скачать обновление сейчас? Можно продолжать пользоваться приложением во время загрузки.',buttons:['Скачать','Позже'],defaultId:0,cancelId:1,noLink:true}); if(result.response===0) await autoUpdater.downloadUpdate(); } catch(_){} finally{updateBusy=false;} });
  autoUpdater.on('update-downloaded', async info => { sendUpdateState({status:'downloaded',version:info.version,percent:100}); const result=await dialog.showMessageBox(mainWindow||undefined,{type:'info',title:'Обновление готово',message:`Версия ${info.version} загружена.`,detail:'Перезапустить Аделию и установить обновление сейчас?',buttons:['Перезапустить и обновить','Позже'],defaultId:0,cancelId:1,noLink:true}); if(result.response===0){closeLessonWindows();autoUpdater.quitAndInstall(false,true);} });
  const check=()=>{if(updateBusy||lessonWindows.size>0)return;autoUpdater.checkForUpdates().catch(()=>{});}; setTimeout(check,15000); updateTimer=setInterval(check,UPDATE_CHECK_MS);
}

function createWindow(initialUrl = null) {
  const restored=savedMainBounds();
  const win=new BrowserWindow({width:restored?.width||1280,height:restored?.height||820,...(restored?{x:restored.x,y:restored.y}:{}),minWidth:900,minHeight:620,show:false,backgroundColor:'#ffffff',title:'Аделия',webPreferences:{preload:path.join(__dirname,'preload.js'),partition:'persist:adelia',contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true,allowRunningInsecureContent:false,backgroundThrottling:false}}); mainWindow=win;
  win.webContents.setWindowOpenHandler(({url})=>{if(trustedApp(url)){win.loadURL(url);return{action:'deny'};}if(trustedChild(url)){openMeetingWindow(url);return{action:'deny'};}if(trustedBoard(url)){openBoardWindow(url);return{action:'deny'};}openExternalSafe(url);return{action:'deny'};});
  win.webContents.on('will-navigate',(event,url)=>{if(!trustedApp(url)){event.preventDefault();if(trustedChild(url))openMeetingWindow(url);else if(trustedBoard(url))openBoardWindow(url);else openExternalSafe(url);}});
  win.webContents.on('did-fail-load',(_e,code,_desc,validatedURL,isMainFrame)=>{if(isMainFrame&&code!==-3&&trustedApp(validatedURL||APP_URL))win.loadURL(offlinePage());});
  win.once('ready-to-show',()=>win.show());
  let boundsTimer=null;
  const queueBoundsSave=()=>{if(boundsTimer)clearTimeout(boundsTimer);boundsTimer=setTimeout(()=>rememberMainBounds(win),250)};
  win.on('resize',queueBoundsSave);win.on('move',queueBoundsSave);
  win.on('close',event=>{ rememberMainBounds(win); if (!isQuitting && prefsWithDefaults().closeToTray) { event.preventDefault(); win.hide(); } });
  win.on('closed',()=>{closeLessonWindows();if(mainWindow===win)mainWindow=null;});
  if (initialUrl && trustedApp(initialUrl)) win.loadURL(initialUrl);
  else win.loadFile(path.join(__dirname,'start.html'));
  return win;
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', (_event, argv) => {
    const deep = deepLinkFromArgv(argv);
    if (deep) handleDeepLink(deep); else showMain();
  });
  app.on('open-url', (event, url) => { event.preventDefault(); handleDeepLink(url); });

  app.whenReady().then(async()=>{
    if (process.platform === 'win32') app.setAppUserModelId('ru.adeliatutor.desktop');
    if (app.isPackaged) app.setAsDefaultProtocolClient(PROTOCOL);
    else if (process.defaultApp && process.argv[1]) app.setAsDefaultProtocolClient(PROTOCOL, process.execPath, [path.resolve(process.argv[1])]);

    const mainSession=session.fromPartition('persist:adelia'); mainSession.setPermissionCheckHandler(()=>false); mainSession.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
    const lessonSession=session.fromPartition('persist:adelia-lesson'); const lessonMediaAllowed=(webContents,permission,requestingOrigin)=>{const origin=requestingOrigin||(webContents?webContents.getURL():'');return trustedChild(origin)&&['media','microphone','camera'].includes(permission);}; lessonSession.setPermissionCheckHandler((wc,p,o)=>lessonMediaAllowed(wc,p,o)); lessonSession.setPermissionRequestHandler((wc,p,cb,d)=>cb(lessonMediaAllowed(wc,p,d&&d.requestingUrl)));
    const boardSession=session.fromPartition('persist:adelia-board'); boardSession.setPermissionCheckHandler(()=>false); boardSession.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
    const deviceCheckSession=session.fromPartition('persist:adelia-device-check');
    const deviceCheckMediaAllowed=(wc,permission)=>{
      const owner=deviceCheckWindow&&!deviceCheckWindow.isDestroyed()&&wc===deviceCheckWindow.webContents;
      return !!owner&&['media','microphone','camera'].includes(permission);
    };
    deviceCheckSession.setPermissionCheckHandler((wc,p)=>deviceCheckMediaAllowed(wc,p));
    deviceCheckSession.setPermissionRequestHandler((wc,p,cb)=>cb(deviceCheckMediaAllowed(wc,p)));

    ipcMain.handle('adelia:lesson-tool',(event,payload)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return false;if(!payload||typeof payload.url!=='string')return false;if(payload.kind==='meeting')return openMeetingWindow(payload.url);if(payload.kind==='board')return openBoardWindow(payload.url);return false;});
    ipcMain.handle('adelia:end-lesson-workspace',(event)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return false;closeLessonWindows(true);return true;});
    ipcMain.handle('adelia:desktop-prefs',(event)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return null;return prefsWithDefaults();});
    ipcMain.handle('adelia:set-close-to-tray',(event,value)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return null;return savePref('closeToTray',!!value);});
    ipcMain.handle('adelia:open-route',(event,payload)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return false;const route=payload&&payload.route;const id=payload&&payload.id;showMain(routeUrl(route,id));return true;});
    ipcMain.handle('adelia:device-check',(event,payload)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return false;return openDeviceCheck(payload&&payload.lessonId);});
    ipcMain.handle('adelia:device-check-complete',(event)=>{
      if(!deviceCheckWindow||event.sender!==deviceCheckWindow.webContents)return false;
      const id=deviceCheckLessonId;
      deviceCheckWindow.close();
      showMain(routeUrl('lesson',id));
      return true;
    });
    ipcMain.handle('adelia:device-check-close',(event)=>{if(!deviceCheckWindow||event.sender!==deviceCheckWindow.webContents)return false;deviceCheckWindow.close();return true;});
    ipcMain.handle('adelia:open-about',(event)=>{if(!mainWindow||event.sender!==mainWindow.webContents)return false;return openAboutWindow();});
    ipcMain.handle('adelia:about-info',(event)=>{if(!aboutWindow||event.sender!==aboutWindow.webContents)return null;return {version:app.getVersion(),channel:UPDATE_CHANNEL==='beta'?'Beta':'Stable',platform:process.platform,arch:process.arch,updateTarget:UPDATE_TARGET,buildSha:buildSha(),packaged:app.isPackaged,updateState};});
    ipcMain.handle('adelia:about-check-updates',async(event)=>{if(!aboutWindow||event.sender!==aboutWindow.webContents)return null;if(!app.isPackaged)return sendUpdateState({status:'current'});if(lessonWindows.size>0)return sendUpdateState({status:'error',message:'Завершите текущее занятие перед проверкой обновления.'});try{sendUpdateState({status:'checking'});await autoUpdater.checkForUpdates();return updateState}catch(err){return sendUpdateState({status:'error',message:err&&err.message?String(err.message).slice(0,180):'Не удалось проверить обновления.'})}});
    ipcMain.handle('adelia:about-install-update',(event)=>{if(!aboutWindow||event.sender!==aboutWindow.webContents||updateState.status!=='downloaded')return false;closeLessonWindows();autoUpdater.quitAndInstall(false,true);return true;});
    ipcMain.handle('adelia:about-close',(event)=>{if(!aboutWindow||event.sender!==aboutWindow.webContents)return false;aboutWindow.close();return true;});

    createTray();
    const startupDeep = deepLinkFromArgv(process.argv);
    createWindow(startupDeep ? parseDeepLink(startupDeep).target : null);
    if (!startupDeep) await restoreMainRole();
    await maybeOfferAutostart();
    setupAutoUpdates();
    app.on('activate',()=>showMain());
  });
}

app.on('before-quit',()=>{isQuitting=true;if(updateTimer)clearInterval(updateTimer);if(deviceCheckWindow&&!deviceCheckWindow.isDestroyed())deviceCheckWindow.destroy();if(aboutWindow&&!aboutWindow.isDestroyed())aboutWindow.destroy();closeLessonWindows();});
app.on('window-all-closed',()=>{if(process.platform==='darwin'&&isQuitting)app.quit();});

