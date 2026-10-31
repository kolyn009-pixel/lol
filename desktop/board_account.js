'use strict';
const {BrowserWindow,dialog}=require('electron');
const {configure}=require('./meeting_browser');
const MOYA=new Set(['https://app.moyadoska.com','https://moyadoska.com','https://www.moyadoska.com']);
const MYBOARD=new Set(['https://myboard.io','https://www.myboard.io']);
// Observed MoyaDoska web sign-in providers, exact HTTPS origins only.
const PROVIDERS=new Set(['https://oauth.yandex.ru','https://passport.yandex.ru','https://id.yandex.ru','https://passport.yandex.com','https://id.yandex.com','https://id.vk.com','https://login.vk.com']);
function origin(raw){try{return new URL(raw).origin}catch{return ''}}
function target(url){const o=origin(url);if(MOYA.has(o))return 'https://app.moyadoska.com/';if(MYBOARD.has(o))return o+'/';return null;}
function allowed(url,boardUrl){const base=origin(boardUrl),o=origin(url);return MOYA.has(base)?MOYA.has(o)||PROVIDERS.has(o):MYBOARD.has(base)&&MYBOARD.has(o);}
function guard(contents,boardUrl){
 for(const event of ['will-navigate','will-redirect'])contents.on(event,(e,url)=>{if(!allowed(url,boardUrl))e.preventDefault();});
 contents.setWindowOpenHandler(({url})=>allowed(url,boardUrl)?{action:'allow',overrideBrowserWindowOptions:{width:620,height:740,webPreferences:{partition:'persist:adelia-board',contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}}}:{action:'deny'});
 contents.on('did-create-window',popup=>{configure(popup.webContents);guard(popup.webContents,boardUrl);});
}
async function open(parent,boardUrl,onClose){
 const url=target(boardUrl);if(!url||parent.isDestroyed())return null;
 const answer=await dialog.showMessageBox(parent,{type:'question',message:'Войти в аккаунт доски или зарегистрироваться?',detail:'Откроется кабинет сервиса доски. После закрытия окна доска обновится с вашим аккаунтом. Сначала дождитесь сохранения текущих изменений.',buttons:['Открыть аккаунт доски','Отмена'],defaultId:1,cancelId:1});
 if(answer.response!==0)return null;
 const win=new BrowserWindow({parent,modal:true,width:1000,height:760,minWidth:620,minHeight:500,title:'Аккаунт доски — Аделия',autoHideMenuBar:true,webPreferences:{partition:'persist:adelia-board',contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
 configure(win.webContents);guard(win.webContents,boardUrl);
 win.on('closed',()=>{if(!parent.isDestroyed())onClose?.();});
 try{await win.loadURL(url);}catch(e){if(!win.isDestroyed())win.close();throw e;}
 return win;
}
module.exports={open,allowed,target};
