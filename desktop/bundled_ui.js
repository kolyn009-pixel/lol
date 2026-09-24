'use strict';
const {app}=require('electron'),fs=require('fs'),path=require('path');
const manifest=require('./bundled_ui_manifest');
const root=path.join(__dirname,'role_assets');
let installed=false;
function source(name){return fs.readFileSync(path.join(root,name),'utf8')}
function roleFor(pathname){
  if(pathname.startsWith('/teacher')||pathname==='/app/teacher.html')return 'teacher';
  if(pathname.startsWith('/app/parent'))return 'parent';
  if(pathname.startsWith('/app'))return 'student';
  return null;
}
async function inject(win){
 if(!win||win.isDestroyed())return false;
 let u;try{u=new URL(win.webContents.getURL())}catch{return false}
 const origin=new URL(process.env.ADELIA_DESKTOP_URL||'https://adeliatutor.ru/app/').origin;
 if(u.origin!==origin)return false;
 const role=roleFor(u.pathname);if(!role||!manifest[role])return false;
 const marker='__adeliaBundledUi_'+role;
 const done=await win.webContents.executeJavaScript(`Boolean(window.${marker})`,true).catch(()=>false);
 if(done)return true;
 await win.webContents.executeJavaScript(`document.documentElement.classList.add('adelia-desktop','adelia-desktop-${role}');document.body&&document.body.classList.add('adelia-desktop','adelia-desktop-${role}')`,true);
 for(const name of manifest[role].css)await win.webContents.insertCSS(source(name));
 for(const name of manifest[role].js)await win.webContents.executeJavaScript(source(name),true);
 if(role==='teacher')await win.webContents.executeJavaScript(`
   if(!window.__adeliaDesktopTeacherRouteGuard){
     window.__adeliaDesktopTeacherRouteGuard=true;
     window.addEventListener('click',function(event){
       const button=event.target&&event.target.closest&&event.target.closest('[data-view]');
       if(!button)return;
       const view=button.dataset.view;
       const render=view==='groups'?window.teacherGroups:view==='health'?window.teacherHealth:null;
       if(typeof render!=='function')return;
       event.preventDefault();
       event.stopImmediatePropagation();
       document.querySelectorAll('aside nav button[data-view]').forEach(function(item){item.classList.toggle('active',item.dataset.view===view)});
       document.body.classList.remove('menu-open','v4-menu-open');
       Promise.resolve(render()).catch(function(error){
         const app=document.querySelector('#app');
         if(app)app.innerHTML='<section class="error">Раздел не загрузился. Обновите страницу и попробуйте ещё раз.</section>';
         console.warn('[desktop-route]',error&&error.message||error);
       });
     },true);
   }
 `,true);
 await win.webContents.executeJavaScript(`window.${marker}=true;window.dispatchEvent(new CustomEvent('adelia:desktop-ui-ready',{detail:{role:'${role}'}}))`,true);
 return true;
}
function scheduleInject(win){
 const run=()=>inject(win).catch(e=>{console.warn('[desktop-ui]',e.message);return false});
 run().then(ok=>{if(!ok&&!win.isDestroyed())setTimeout(run,250)});
 if(!win.isDestroyed())setTimeout(run,900);
}
function install(){
 if(installed)return;installed=true;
 app.on('browser-window-created',(_e,win)=>{
   win.webContents.on('did-finish-load',()=>scheduleInject(win));
   win.webContents.on('did-navigate-in-page',()=>scheduleInject(win));
 });
}
module.exports={install};
