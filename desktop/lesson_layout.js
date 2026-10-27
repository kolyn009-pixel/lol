'use strict';
const { app, BrowserWindow, ipcMain, screen, globalShortcut } = require('electron');
const fs = require('fs');
const path = require('path');

const MODES = new Set(['together','board-focus','mini-video','hide-video','dual-screen','teacher-room']);
const SHORTCUTS = {
  board: 'CommandOrControl+Shift+B',
  video: 'CommandOrControl+Shift+V',
  together: 'CommandOrControl+Shift+L',
  dual: 'CommandOrControl+Shift+D',
};
let watcher = null;
let lastPairKey = '';
let activeMode=null;

function prefsPath(){ return path.join(app.getPath('userData'),'desktop-prefs.json'); }
function readPrefs(){ try{return JSON.parse(fs.readFileSync(prefsPath(),'utf8'))}catch(_){return{}} }
function writePrefs(next){ try{fs.mkdirSync(path.dirname(prefsPath()),{recursive:true});fs.writeFileSync(prefsPath(),JSON.stringify(next),'utf8')}catch(_){} return next; }
function preferredMode(){ const m=String(readPrefs().lessonLayout||'together'); return MODES.has(m)?m:'together'; }
function rememberMode(mode){ const p=readPrefs();p.lessonLayout=mode;writePrefs(p); }
function findWindow(prefix){ return BrowserWindow.getAllWindows().find(w=>!w.isDestroyed()&&String(w.getTitle()||'').startsWith(prefix))||null; }
function meeting(){return BrowserWindow.getAllWindows().find(w=>!w.isDestroyed()&&w.adeliaLessonKind==='meeting')||findWindow('Телемост — Аделия');}
function board(){return BrowserWindow.getAllWindows().find(w=>!w.isDestroyed()&&w.adeliaLessonKind==='board')||findWindow('Доска — Аделия');}
function displayFor(...wins){ const win=wins.find(Boolean);return win?screen.getDisplayMatching(win.getBounds()):screen.getPrimaryDisplay(); }
function displayDistance(a,b){const ax=a.workArea.x+a.workArea.width/2,ay=a.workArea.y+a.workArea.height/2,bx=b.workArea.x+b.workArea.width/2,by=b.workArea.y+b.workArea.height/2;return Math.hypot(ax-bx,ay-by)}
function lessonDisplays(){
  const all=screen.getAllDisplays();
  const primary=displayFor(board(),meeting());
  if(all.length<2)return {primary,secondary:null};
  const secondary=all.filter(d=>d.id!==primary.id).sort((a,b)=>displayDistance(primary,a)-displayDistance(primary,b))[0]||null;
  return {primary,secondary};
}
function safeShow(win){ if(!win||win.isDestroyed())return;if(win.isMinimized())win.restore();win.show(); }
function clearTop(win){ if(!win||win.isDestroyed())return;try{win.setAlwaysOnTop(false)}catch(_){} }
function setTop(win){ if(!win||win.isDestroyed())return;try{win.setAlwaysOnTop(true,'floating')}catch(_){try{win.setAlwaysOnTop(true)}catch(__){}} }
let savedCabinet=null;
function cabinet(){return BrowserWindow.getAllWindows().find(w=>{if(w.isDestroyed())return false;try{const u=new URL(w.webContents.getURL());return u.origin==='https://adeliatutor.ru'&&(u.pathname.startsWith('/teacher')||u.pathname==='/app/teacher.html');}catch{return false;}})||null;}
function roomBounds(area){const gap=8,right=Math.min(560,Math.max(420,Math.round(area.width*.32))),left=area.width-right-gap,video=Math.max(270,Math.min(380,Math.round(area.height*.45)));return {board:{x:area.x,y:area.y,width:left,height:area.height},video:{x:area.x+left+gap,y:area.y,width:right,height:video},context:{x:area.x+left+gap,y:area.y+video+gap,width:right,height:area.height-video-gap}};}
function contextMode(win,on){if(!win||win.isDestroyed())return;
 win.webContents.executeJavaScript(`document.documentElement.classList.toggle('adelia-lesson-context-mode',${!!on})`,true).catch(()=>{});
 const css='html.adelia-lesson-context-mode .teacher-shell>aside,html.adelia-lesson-context-mode .teacher-shell main>header,html.adelia-lesson-context-mode #app>:not(#lessonContextBlock){display:none!important}html.adelia-lesson-context-mode .teacher-shell{display:block!important}html.adelia-lesson-context-mode .teacher-shell main{margin:0!important;padding:12px!important;width:auto!important;min-width:0!important}html.adelia-lesson-context-mode #lessonContextBlock .lesson-context-grid{display:block!important}html.adelia-lesson-context-mode #lessonContextBlock .lesson-context-side,html.adelia-lesson-context-mode #lessonContextBlock .lesson-chat-card{display:none!important}';
 if(on&&!win.adeliaContextStyle){win.adeliaContextStyle='pending';win.webContents.insertCSS(css,{cssOrigin:'user'}).then(key=>{win.adeliaContextStyle=key;}).catch(()=>{win.adeliaContextStyle=null;});}
 if(!on&&win.adeliaContextStyle&&win.adeliaContextStyle!=='pending'){win.webContents.removeInsertedCSS(win.adeliaContextStyle).catch(()=>{});win.adeliaContextStyle=null;}
 if(on&&!win.adeliaContextReload){win.adeliaContextReload=true;win.webContents.on('did-finish-load',()=>{win.adeliaContextStyle=null;if(savedCabinet?.win===win)contextMode(win,true);});}
}
function restoreCabinet(){if(!savedCabinet)return;const {win,bounds,min}=savedCabinet;savedCabinet=null;if(!win.isDestroyed()){contextMode(win,false);win.setMinimumSize(...min);win.setBounds(bounds);}}
function apply(mode,remember=true){
  const room=require('./lesson_room').getActive();if(room?.active)return room.setMode(mode);
  mode=MODES.has(mode)?mode:'together';
  const m=meeting(),b=board();
  if(mode!=='teacher-room')restoreCabinet();
  if(!m&&!b){restoreCabinet();return state();}
  const displays=lessonDisplays();
  const area=displays.primary.workArea;
  const gap=10;
  clearTop(m);clearTop(b);

  if(mode==='teacher-room'&&cabinet()&&area.width>=1100&&area.height>=650){
    const c=cabinet(),r=roomBounds(area);if(!savedCabinet)savedCabinet={win:c,bounds:c.getBounds(),min:c.getMinimumSize()};
    if(c.isMaximized())c.unmaximize();c.setMinimumSize(380,250);safeShow(c);c.setBounds(r.context);contextMode(c,true);
    if(b){if(b.isMaximized())b.unmaximize();b.setMinimumSize(400,300);safeShow(b);b.setBounds(r.board);}
    if(m){if(m.isMaximized())m.unmaximize();m.setMinimumSize(380,250);safeShow(m);m.setBounds(r.video);}
    c.focus();
  }else if(mode==='teacher-room'){return apply('together',remember);
  }else if(mode==='dual-screen'&&displays.secondary){
    const boardArea=displays.primary.workArea,videoArea=displays.secondary.workArea;
    if(b){safeShow(b);b.setBounds({x:boardArea.x,y:boardArea.y,width:boardArea.width,height:boardArea.height});}
    if(m){safeShow(m);m.setBounds({x:videoArea.x,y:videoArea.y,width:videoArea.width,height:videoArea.height});}
    if(b)b.focus();else if(m)m.focus();
  }else if(mode==='hide-video'){
    if(m&&!m.isDestroyed())m.hide();
    if(b){safeShow(b);b.setBounds({x:area.x,y:area.y,width:area.width,height:area.height});b.focus();}
  }else if(mode==='mini-video'){
    if(b){safeShow(b);b.setBounds({x:area.x,y:area.y,width:area.width,height:area.height});}
    if(m){safeShow(m);const width=Math.min(360,Math.max(300,Math.round(area.width*.24)));const height=Math.min(240,Math.max(190,Math.round(width*.64)));m.setBounds({x:area.x+area.width-width-18,y:area.y+area.height-height-18,width,height});setTop(m);}
    if(b)b.focus();
  }else if(mode==='board-focus'){
    if(area.width>=1050){
      const videoWidth=Math.max(270,Math.floor((area.width-gap)*.24));const boardWidth=area.width-gap-videoWidth;
      if(m){safeShow(m);m.setBounds({x:area.x,y:area.y,width:videoWidth,height:area.height});}
      if(b){safeShow(b);b.setBounds({x:area.x+videoWidth+gap,y:area.y,width:boardWidth,height:area.height});b.focus();}
    }else{
      const videoHeight=Math.max(180,Math.floor((area.height-gap)*.22));
      if(m){safeShow(m);m.setBounds({x:area.x,y:area.y,width:area.width,height:videoHeight});}
      if(b){safeShow(b);b.setBounds({x:area.x,y:area.y+videoHeight+gap,width:area.width,height:area.height-videoHeight-gap});b.focus();}
    }
  }else{
    if(area.width>=1280){
      const videoWidth=Math.floor((area.width-gap)*.44);
      if(m){safeShow(m);m.setBounds({x:area.x,y:area.y,width:videoWidth,height:area.height});}
      if(b){safeShow(b);b.setBounds({x:area.x+videoWidth+gap,y:area.y,width:area.width-videoWidth-gap,height:area.height});b.focus();}
    }else{
      const videoHeight=Math.floor((area.height-gap)*.42);
      if(m){safeShow(m);m.setBounds({x:area.x,y:area.y,width:area.width,height:videoHeight});}
      if(b){safeShow(b);b.setBounds({x:area.x,y:area.y+videoHeight+gap,width:area.width,height:area.height-videoHeight-gap});b.focus();}
    }
  }
  activeMode=mode;
  if(remember)rememberMode(mode==='dual-screen'&&!displays.secondary?'together':mode);
  return state(mode==='dual-screen'&&!displays.secondary?'together':mode);
}
function toggleVideo(){const room=require('./lesson_room').getActive();if(room?.active)return room.toggleVideo();const m=meeting();if(!m)return state();if(m.isVisible())return apply('hide-video');const restore=preferredMode()==='hide-video'?'together':preferredMode();return apply(restore);}
function state(mode){
  const room=require('./lesson_room').getActive();if(room?.active)return room.state();
  const m=meeting(),b=board(),displays=lessonDisplays();
  return {active:!!(m||b),meetingOpen:!!m,meetingVisible:!!(m&&m.isVisible()),boardOpen:!!b,boardVisible:!!(b&&b.isVisible()),mode:mode||activeMode||preferredMode(),displayCount:screen.getAllDisplays().length,dualScreenAvailable:!!displays.secondary,shortcuts:SHORTCUTS};
}
function registerShortcuts(){
  for(const accelerator of Object.values(SHORTCUTS))globalShortcut.unregister(accelerator);
  try{globalShortcut.register(SHORTCUTS.board,()=>apply('board-focus'))}catch(_){}
  try{globalShortcut.register(SHORTCUTS.video,()=>toggleVideo())}catch(_){}
  try{globalShortcut.register(SHORTCUTS.together,()=>apply('together'))}catch(_){}
  try{globalShortcut.register(SHORTCUTS.dual,()=>apply('dual-screen'))}catch(_){}
}
function watchWindows(){watcher=setInterval(()=>{const m=meeting(),b=board();const key=`${m?m.id:0}:${b?b.id:0}`;if(key!==lastPairKey){lastPairKey=key;if(m||b)setTimeout(()=>apply(cabinet()&&!readPrefs().lessonLayout?'teacher-room':preferredMode(),false),250);else restoreCabinet()}},900);}
function install(){
  app.whenReady().then(()=>{ipcMain.handle('adelia:lesson-layout',(_event,mode)=>apply(String(mode||'')));ipcMain.handle('adelia:lesson-toggle-video',()=>toggleVideo());ipcMain.handle('adelia:lesson-layout-state',()=>state());registerShortcuts();watchWindows();});
  app.on('before-quit',()=>{if(watcher)clearInterval(watcher);watcher=null;for(const accelerator of Object.values(SHORTCUTS))globalShortcut.unregister(accelerator);});
}
module.exports={install,apply,state,SHORTCUTS,roomBounds};
