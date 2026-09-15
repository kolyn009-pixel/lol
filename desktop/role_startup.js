'use strict';
const { app, BrowserWindow, ipcMain, session, Menu } = require('electron');
const path = require('path');
const APP_ORIGIN = new URL(process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/app/').origin;
const APP_URL = APP_ORIGIN + '/app/';
let installed=false;
function mainWindow(){return BrowserWindow.getAllWindows().find(w=>!w.isDestroyed()&&w.webContents.getURL().includes(APP_ORIGIN))||BrowserWindow.getAllWindows().find(w=>!w.isDestroyed())||null}
async function sessionState(){
  try{
    const s=session.fromPartition('persist:adelia');
    const r=await s.fetch(APP_ORIGIN+'/api/auth/me',{credentials:'include',headers:{'Accept':'application/json'}});
    if(!r.ok)return null;
    const j=await r.json().catch(()=>null);
    if(!j||!j.authenticated||!j.session)return null;
    return j.session;
  }catch{return null}
}
async function showChooser(){const win=mainWindow();if(!win)return false;await win.loadFile(path.join(__dirname,'start.html'));win.setTitle('Аделия — вход');return true}
async function openStudent(mode){const win=mainWindow();if(!win)return false;if(mode==='cabinet'){await win.loadURL(APP_URL);return true}const u=new URL(APP_URL);u.searchParams.set('desktop_login',mode==='code'?'code':'password');await win.loadURL(u.toString());return true}
async function openParent(){const win=mainWindow();if(!win)return false;await win.loadURL(APP_ORIGIN+'/app/parent/');return true}
async function apiJson(route,opt={}){try{const s=session.fromPartition('persist:adelia');const r=await s.fetch(APP_ORIGIN+route,{credentials:'include',headers:{'Content-Type':'application/json','Origin':APP_ORIGIN,...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)return{ok:false,status:r.status,error:j.error||'request_failed',data:j};return{ok:true,status:r.status,data:j}}catch{return{ok:false,status:0,error:'network_error',data:{}}}}
async function teacherLogin(code){const clean=String(code||'').replace(/\D/g,'');if(clean.length!==6)return{ok:false,error:'invalid'};const r=await apiJson('/api/auth/teacher/code',{method:'POST',body:JSON.stringify({code:clean})});return r.ok?{ok:true}:{ok:false,error:r.error}}
async function openTeacher(){const win=mainWindow();if(!win)return false;await win.loadURL(APP_ORIGIN+'/teacher/');return true}
async function restoreAuthenticatedRole(){
  const auth=await sessionState();
  if(!auth)return showChooser();
  const role=String(auth.role||'').toLowerCase();
  if(role==='teacher')return openTeacher();
  if(role==='parent')return openParent();
  if(role==='student')return openStudent('cabinet');
  return showChooser();
}
async function onboardingStart(payload){const body=payload&&typeof payload==='object'?payload:{};return apiJson('/api/onboarding/start',{method:'POST',body:JSON.stringify(body)})}
async function onboardingStatus(token){return apiJson('/api/onboarding/status?token='+encodeURIComponent(String(token||'')))}
async function onboardingRegion(payload){return apiJson('/api/onboarding/region',{method:'POST',body:JSON.stringify(payload||{})})}
async function onboardingScheduleOptions(token){return apiJson('/api/onboarding/schedule-options?token='+encodeURIComponent(String(token||'')))}
async function onboardingSchedule(payload){return apiJson('/api/onboarding/schedule',{method:'POST',body:JSON.stringify(payload||{})})}
async function onboardingComplete(payload){return apiJson('/api/onboarding/complete',{method:'POST',body:JSON.stringify(payload||{})})}
function install(){if(installed)return;installed=true;app.whenReady().then(()=>{Menu.setApplicationMenu(null);ipcMain.handle('adelia:role-chooser',()=>showChooser());ipcMain.handle('adelia:teacher-login',(_e,code)=>teacherLogin(code));ipcMain.handle('adelia:student-login',(_e,mode)=>openStudent(mode));ipcMain.handle('adelia:parent-cabinet',()=>openParent());ipcMain.handle('adelia:teacher-cabinet',()=>openTeacher());ipcMain.handle('adelia:onboarding-start',(_e,p)=>onboardingStart(p));ipcMain.handle('adelia:onboarding-status',(_e,t)=>onboardingStatus(t));ipcMain.handle('adelia:onboarding-region',(_e,p)=>onboardingRegion(p));ipcMain.handle('adelia:onboarding-schedule-options',(_e,t)=>onboardingScheduleOptions(t));ipcMain.handle('adelia:onboarding-schedule',(_e,p)=>onboardingSchedule(p));ipcMain.handle('adelia:onboarding-complete',(_e,p)=>onboardingComplete(p));setTimeout(()=>{restoreAuthenticatedRole().catch(()=>showChooser())},700)}).catch(()=>{})}
module.exports={install,sessionState,restoreAuthenticatedRole};
