'use strict';
const { app, BrowserWindow, ipcMain, session, Menu } = require('electron');
const path = require('path');
const APP_ORIGIN = new URL(process.env.ADELIA_DESKTOP_URL || 'https://adeliatutor.ru/app/').origin;
const APP_URL = APP_ORIGIN + '/app/';
let installed=false;
function mainWindow(){return BrowserWindow.getAllWindows().find(w=>!w.isDestroyed()&&w.webContents.getURL().includes(APP_ORIGIN))||BrowserWindow.getAllWindows().find(w=>!w.isDestroyed())||null}
async function hasSession(){try{const cookies=await session.fromPartition('persist:adelia').cookies.get({url:APP_ORIGIN,name:'adelia_session'});return cookies.length>0}catch{return false}}
async function showChooser(){const win=mainWindow();if(!win)return false;await win.loadFile(path.join(__dirname,'start.html'));win.setTitle('Аделия — вход');return true}
async function openStudent(mode){const win=mainWindow();if(!win)return false;const u=new URL(APP_URL);u.searchParams.set('desktop_login',mode==='code'?'code':'password');await win.loadURL(u.toString());return true}
async function teacherLogin(code){const clean=String(code||'').replace(/\D/g,'');if(clean.length!==6)return{ok:false,error:'invalid'};try{const s=session.fromPartition('persist:adelia');const r=await s.fetch(APP_ORIGIN+'/api/auth/teacher/code',{method:'POST',headers:{'Content-Type':'application/json','Origin':APP_ORIGIN},body:JSON.stringify({code:clean})});const j=await r.json().catch(()=>({}));if(!r.ok)return{ok:false,error:j.error||'invalid'};return{ok:true}}catch{return{ok:false,error:'network_error'}}}
async function openTeacher(){const win=mainWindow();if(!win)return false;await win.loadURL(APP_ORIGIN+'/teacher/');return true}
function install(){if(installed)return;installed=true;app.whenReady().then(()=>{Menu.setApplicationMenu(null);ipcMain.handle('adelia:role-chooser',()=>showChooser());ipcMain.handle('adelia:teacher-login',(_e,code)=>teacherLogin(code));ipcMain.handle('adelia:student-login',(_e,mode)=>openStudent(mode));ipcMain.handle('adelia:teacher-cabinet',()=>openTeacher());setTimeout(async()=>{if(!(await hasSession()))await showChooser()},700)}).catch(()=>{})}
module.exports={install};