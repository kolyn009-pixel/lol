(()=>{'use strict';
if(window.adeliaDesktop?.desktop)return;
let installEvent=null,busy=false,note='',installed=window.matchMedia?.('(display-mode: standalone)').matches||navigator.standalone===true;
const bar=document.createElement('aside');bar.className='pwa-workspace';bar.setAttribute('aria-live','polite');bar.hidden=true;
const label=document.createElement('span'),button=document.createElement('button');button.type='button';bar.append(label,button);document.body.append(bar);
function status(){
button.disabled=busy;
if(!navigator.onLine){bar.hidden=false;label.textContent='Нет сети · отправка недоступна';button.textContent='Проверить';button.onclick=()=>{if(navigator.onLine)location.reload();};return;}
if(busy){bar.hidden=false;label.textContent='Ожидаем окно установки браузера…';button.textContent='Открываем…';return;}
if(note){bar.hidden=false;label.textContent=note;button.textContent='Закрыть';button.onclick=()=>{note='';status();};return;}
if(installEvent&&!installed){bar.hidden=false;label.textContent='Аделия под рукой';button.textContent='Установить';button.onclick=install;return;}
bar.hidden=true;
}
async function install(){
if(busy||!installEvent)return;
// A browser install event can be used only once, even after cancellation.
const event=installEvent;installEvent=null;busy=true;note='';let timeout;
try{
// Invoke synchronously inside the click handler to retain user activation.
const prompt=event.prompt();status();
const result=await Promise.race([(async()=>{await prompt;return await event.userChoice;})(),new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('install_timeout')),15000);})]);
if(result?.outcome==='accepted')installed=true;
else if(!installed)note='Установка отменена. Чтобы повторить, обновите страницу.';
}catch{if(!installed)note='Браузер не открыл установку. Проверьте значок установки в адресной строке или меню браузера.';}
finally{clearTimeout(timeout);busy=false;status();}
}
window.addEventListener('beforeinstallprompt',e=>{if(installed)return;e.preventDefault();installEvent=e;note='';status();});
window.addEventListener('appinstalled',()=>{installed=true;installEvent=null;note='';busy=false;status();});
window.addEventListener('offline',status);
window.addEventListener('online',()=>{note='Связь восстановлена';status();});
status();
})();
