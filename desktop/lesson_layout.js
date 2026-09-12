'use strict';
const { app, BrowserWindow, ipcMain, screen, globalShortcut } = require('electron');
const fs = require('fs');
const path = require('path');

const MODES = new Set(['together','board-focus','mini-video','hide-video']);
const SHORTCUTS = {
  board: 'CommandOrControl+Shift+B',
  video: 'CommandOrControl+Shift+V',
  together: 'CommandOrControl+Shift+L',
};
let watcher = null;
let lastPairKey = '';

function prefsPath(){ return path.join(app.getPath('userData'),'desktop-prefs.json'); }
function readPrefs(){ try{return JSON.parse(fs.readFileSync(prefsPath(),'utf8'))}catch(_){return{}} }
function writePrefs(next){ try{fs.mkdirSync(path.dirname(prefsPath()),{recursive:true});fs.writeFileSync(prefsPath(),JSON.stringify(next),'utf8')}catch(_){} return next; }
function preferredMode(){ const m=String(readPrefs().lessonLayout||'together'); return MODES.has(m)?m:'together'; }
function rememberMode(mode){ const p=readPrefs();p.lessonLayout=mode;writePrefs(p); }
function findWindow(prefix){ return BrowserWindow.getAllWindows().find(w=>!w.isDestroyed()&&String(w.getTitle()||'').startsWith(prefix))||null; }
function meeting(){ return findWindow('Телемост — Аделия'); }
function board(){ return findWindow('Доска — Аделия'); }
function displayFor(...wins){
  const win=wins.find(Boolean);
  return win?screen.getDisplayMatching(win.getBounds()):screen.getPrimaryDisplay();
}
function safeShow(win){ if(!win||win.isDestroyed())return;if(win.isMinimized())win.restore();win.show(); }
function clearTop(win){ if(!win||win.isDestroyed())return;try{win.setAlwaysOnTop(false)}catch(_){} }
function setTop(win){ if(!win||win.isDestroyed())return;try{win.setAlwaysOnTop(true,'floating')}catch(_){try{win.setAlwaysOnTop(true)}catch(__){}} }
function apply(mode,remember=true){
  mode=MODES.has(mode)?mode:'together';
  const m=meeting(),b=board();
  if(!m&&!b)return state();
  const area=displayFor(b,m).workArea;
  const gap=10;
  clearTop(m);clearTop(b);

  if(mode==='hide-video'){
    if(m&&!m.isDestroyed())m.hide();
    if(b){safeShow(b);b.setBounds({x:area.x,y:area.y,width:area.width,height:area.height});b.focus();}
  }else if(mode==='mini-video'){
    if(b){safeShow(b);b.setBounds({x:area.x,y:area.y,width:area.width,height:area.height});}
    if(m){
      safeShow(m);
      const width=Math.min(360,Math.max(300,Math.round(area.width*.24)));
      const height=Math.min(240,Math.max(190,Math.round(width*.64)));
      m.setBounds({x:area.x+area.width-width-18,y:area.y+area.height-height-18,width,height});
      setTop(m);
    }
    if(b)b.focus();
  }else if(mode==='board-focus'){
    if(area.width>=1050){
      const videoWidth=Math.max(270,Math.floor((area.width-gap)*.24));
      const boardWidth=area.width-gap-videoWidth;
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
  if(remember)rememberMode(mode);
  return state(mode);
}
function toggleVideo(){
  const m=meeting();
  if(!m)return state();
  if(m.isVisible())return apply('hide-video');
  const restore=preferredMode()==='hide-video'?'together':preferredMode();
  return apply(restore);
}
function state(mode){
  const m=meeting(),b=board();
  return {
    active:!!(m||b),
    meetingOpen:!!m,
    meetingVisible:!!(m&&m.isVisible()),
    boardOpen:!!b,
    boardVisible:!!(b&&b.isVisible()),
    mode:mode||preferredMode(),
    shortcuts:SHORTCUTS,
  };
}
function registerShortcuts(){
  for(const accelerator of Object.values(SHORTCUTS))globalShortcut.unregister(accelerator);
  try{globalShortcut.register(SHORTCUTS.board,()=>apply('board-focus'))}catch(_){}
  try{globalShortcut.register(SHORTCUTS.video,()=>toggleVideo())}catch(_){}
  try{globalShortcut.register(SHORTCUTS.together,()=>apply('together'))}catch(_){}
}
function watchWindows(){
  watcher=setInterval(()=>{
    const m=meeting(),b=board();
    const key=`${m?m.id:0}:${b?b.id:0}`;
    if(key!==lastPairKey){
      lastPairKey=key;
      if(m||b)setTimeout(()=>apply(preferredMode(),false),250);
    }
  },900);
}
function install(){
  app.whenReady().then(()=>{
    ipcMain.handle('adelia:lesson-layout',(_event,mode)=>apply(String(mode||'')));
    ipcMain.handle('adelia:lesson-toggle-video',()=>toggleVideo());
    ipcMain.handle('adelia:lesson-layout-state',()=>state());
    registerShortcuts();
    watchWindows();
  });
  app.on('before-quit',()=>{
    if(watcher)clearInterval(watcher);watcher=null;
    for(const accelerator of Object.values(SHORTCUTS))globalShortcut.unregister(accelerator);
  });
}
module.exports={install,apply,state,SHORTCUTS};
