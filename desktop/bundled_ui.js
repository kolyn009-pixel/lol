'use strict';
const {app}=require('electron'),fs=require('fs'),path=require('path');
const manifest=require('./bundled_ui_manifest');
const root=path.join(__dirname,'role_assets');
let installed=false;
function source(name){return fs.readFileSync(path.join(root,name),'utf8')}
function roleFor(pathname){
  if(pathname.startsWith('/teacher'))return 'teacher';
  if(pathname.startsWith('/app/parent'))return 'parent';
  if(pathname.startsWith('/app'))return 'student';
  return null;
}
async function inject(win){
 if(!win||win.isDestroyed())return;
 let u;try{u=new URL(win.webContents.getURL())}catch{return}
 const origin=new URL(process.env.ADELIA_DESKTOP_URL||'https://adeliatutor.ru/app/').origin;
 if(u.origin!==origin)return;
 const role=roleFor(u.pathname);if(!role||!manifest[role])return;
 const marker='__adeliaBundledUi_'+role;
 const done=await win.webContents.executeJavaScript(`Boolean(window.${marker})`,true).catch(()=>true);
 if(done)return;
 await win.webContents.executeJavaScript(`window.${marker}=true`,true);
 for(const name of manifest[role].css)await win.webContents.insertCSS(source(name));
 for(const name of manifest[role].js)await win.webContents.executeJavaScript(source(name),true);
}
function install(){
 if(installed)return;installed=true;
 app.on('browser-window-created',(_e,win)=>win.webContents.on('did-finish-load',()=>inject(win).catch(e=>console.warn('[desktop-ui]',e.message))));
}
module.exports={install};
