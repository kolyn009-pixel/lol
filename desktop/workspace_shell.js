'use strict';
const { app, BrowserWindow, Menu, screen } = require('electron');
const fs = require('fs');
const path = require('path');

const APP_ORIGIN = new URL(process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/app/').origin;
const STATE_FILE = 'workspace-window.json';
let saveTimer = null;

function statePath(){ return path.join(app.getPath('userData'),STATE_FILE); }
function readState(){ try{return JSON.parse(fs.readFileSync(statePath(),'utf8'))||{}}catch(_){return{}} }
function writeState(value){ try{fs.mkdirSync(path.dirname(statePath()),{recursive:true});fs.writeFileSync(statePath(),JSON.stringify(value),'utf8')}catch(_){} }
function validBounds(bounds){
  if(!bounds||!Number.isFinite(bounds.x)||!Number.isFinite(bounds.y)||!Number.isFinite(bounds.width)||!Number.isFinite(bounds.height))return false;
  if(bounds.width<900||bounds.height<620)return false;
  return screen.getAllDisplays().some(d=>{
    const a=d.workArea;
    return bounds.x<a.x+a.width-100&&bounds.x+bounds.width>a.x+100&&bounds.y<a.y+a.height-80&&bounds.y+bounds.height>a.y+80;
  });
}
function isMain(win){
  if(!win||win.isDestroyed())return false;
  try{const u=new URL(win.webContents.getURL());return u.origin===APP_ORIGIN}catch(_){return false}
}
function role(win){
  try{const u=new URL(win.webContents.getURL());if(u.pathname.startsWith('/teacher'))return'teacher';if(u.pathname.startsWith('/app/parent'))return'parent';return'student'}catch(_){return'student'}
}
function studentUrl(view){
  const u=new URL('/app/',APP_ORIGIN);
  if(view&&view!=='dashboard')u.searchParams.set('desktop',view);
  return u.toString();
}
function activateTeacherView(win,view){
  const safe=String(view||'dashboard').replace(/[^a-zA-Z0-9_-]/g,'');
  if(!safe)return false;
  win.webContents.executeJavaScript(`(()=>{const b=document.querySelector('[data-view="${safe}"]');if(!b)return false;b.click();return true})()`,true).catch(()=>{});
  return true;
}
function navigate(win,view){
  if(!isMain(win))return false;
  const r=role(win);
  if(r==='teacher')return activateTeacherView(win,view);
  if(r==='parent'){
    if(view==='dashboard'||view==='payments')win.loadURL(APP_ORIGIN+'/app/parent/').catch(()=>{});
    return true;
  }
  const map={dashboard:'',schedule:'schedule',students:'',homework:'homework',messages:'chat',payments:'finance'};
  const target=map[view];if(target===undefined)return false;
  win.loadURL(studentUrl(target)).catch(()=>{});return true;
}
function commandTemplate(win){
  const r=role(win);
  const common=[
    ['Сегодня','dashboard','CmdOrCtrl+1'],['Расписание','schedule','CmdOrCtrl+2'],
    ...(r==='teacher'?[['Ученики','students','CmdOrCtrl+3']]:[]),
    ['Домашние задания','homework','CmdOrCtrl+4'],['Сообщения','messages','CmdOrCtrl+5'],['Оплаты','payments','CmdOrCtrl+6']
  ];
  return common.map(([label,view,accelerator])=>({label,accelerator,click:()=>navigate(win,view)}));
}
function showWorkspaceMenu(win){
  if(!isMain(win))return;
  const r=role(win);
  const title=r==='teacher'?'Рабочее пространство преподавателя':r==='parent'?'Кабинет родителя':'Рабочее пространство ученика';
  Menu.buildFromTemplate([{label:title,enabled:false},{type:'separator'},...commandTemplate(win),{type:'separator'},{label:'Обновить',accelerator:'CmdOrCtrl+R',click:()=>win.webContents.reload()}]).popup({window:win});
}
function shortcutView(input){
  if(!input.control&&!input.meta)return null;
  if(input.alt||input.shift)return null;
  return ({'1':'dashboard','2':'schedule','3':'students','4':'homework','5':'messages','6':'payments'})[String(input.key||'')]||null;
}
function attach(win){
  if(!win||win.isDestroyed()||win.__adeliaWorkspaceShell)return;
  win.__adeliaWorkspaceShell=true;
  win.webContents.on('before-input-event',(event,input)=>{
    if((input.control||input.meta)&&!input.alt&&!input.shift&&String(input.key||'').toLowerCase()==='k'){
      event.preventDefault();showWorkspaceMenu(win);return;
    }
    const view=shortcutView(input);if(view){event.preventDefault();navigate(win,view)}
  });
  win.on('ready-to-show',()=>{
    if(!isMain(win))return;
    const state=readState();
    if(validBounds(state.bounds))win.setBounds(state.bounds,false);
    if(state.maximized)win.maximize();
  });
  const scheduleSave=()=>{
    if(!isMain(win)||win.isDestroyed())return;
    clearTimeout(saveTimer);saveTimer=setTimeout(()=>{
      if(win.isDestroyed())return;
      const maximized=win.isMaximized();
      const bounds=maximized?(readState().bounds||win.getNormalBounds()):win.getBounds();
      writeState({bounds,maximized});
    },300);
  };
  win.on('resize',scheduleSave);win.on('move',scheduleSave);win.on('maximize',scheduleSave);win.on('unmaximize',scheduleSave);
}
function install(){
  app.on('browser-window-created',(_event,win)=>setTimeout(()=>attach(win),0));
  app.whenReady().then(()=>BrowserWindow.getAllWindows().forEach(attach));
  app.on('before-quit',()=>{if(saveTimer)clearTimeout(saveTimer)});
}
module.exports={install,navigate,showWorkspaceMenu};
