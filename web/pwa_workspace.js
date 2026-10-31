(()=>{'use strict';
if(window.adeliaDesktop?.desktop)return;
let dismissed=false;try{dismissed=localStorage.getItem('adelia-install-hidden')==='1';}catch{}
let installEvent=null,busy=false,note='',installed=window.matchMedia?.('(display-mode: standalone)').matches||navigator.standalone===true;
const bar=document.createElement('aside');bar.className='pwa-workspace';bar.setAttribute('aria-live','polite');bar.hidden=true;
const label=document.createElement('span'),button=document.createElement('button');button.type='button';bar.append(label,button);document.body.append(bar);const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Скрыть предложение установки');close.title='Скрыть';close.onclick=()=>{dismissed=true;try{localStorage.setItem('adelia-install-hidden','1');}catch{}status();};bar.append(close);
function status(){
updatePage();button.disabled=busy;
if(!navigator.onLine){bar.hidden=false;label.textContent='Нет сети · отправка недоступна';button.textContent='Проверить';button.onclick=()=>{if(navigator.onLine)location.reload();};return;}
if(busy){bar.hidden=true;label.textContent='Ожидаем окно установки браузера…';button.textContent='Открываем…';return;}
if(note){bar.hidden=true;label.textContent=note;button.textContent='Закрыть';button.onclick=()=>{note='';status();};return;}
if(!installed&&!dismissed&&location.hash!=='#install'){bar.hidden=false;label.textContent='Аделия на вашем устройстве';button.textContent='Как установить';button.onclick=openPage;return;}
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

const devices=[['mac','Ноутбук','Mac','Safari 14 macOS'],['windows','Компьютер','Windows','Chrome или Edge'],['ios','Телефон','iPhone / iPad','Safari'],['android','Телефон','Android','Chrome']];
const guides={mac:['Откройте кабинет в Safari на macOS Sonoma 14 или новее.','Файл → Добавить в Dock.','Подтвердите название «Аделия» и нажмите «Добавить».'],windows:['Откройте кабинет в Chrome или Edge.','В Chrome: меню ⋮ → Транслировать, сохранить, поделиться → Установить страницу как приложение. В Edge найдите «Приложения» в меню.','Подтвердите установку в окне браузера.'],ios:['Откройте кабинет в Safari, вне встроенного браузера ВК или Telegram.','Нажмите «Поделиться» → «На экран Домой».','Подтвердите добавление и запускайте Аделию с нового значка.'],android:['Откройте кабинет в Chrome, вне встроенного браузера мессенджера.','Меню ⋮ → «Установить приложение» или «Добавить на главный экран».','Подтвердите действие браузера.']};
let selected=/iPhone|iPad|iPod/.test(navigator.userAgent)||navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1?'ios':/Android/.test(navigator.userAgent)?'android':/Mac/.test(navigator.platform||'')?'mac':'windows';
function openPage(){window.AdeliaTeacherMessenger?.pause?.();if(location.hash!=='#install')location.hash='install';renderPage();status();}
function renderPage(){const app=document.querySelector('#app');if(!app)return;window.AdeliaTeacherMessenger?.pause?.();const title=document.querySelector('#title');if(title)title.textContent='Установить Аделию';app.innerHTML='<section class="install-hub"><header><img src="/app/assets/icons/adelia-mark-180.png" alt=""><div><small>ВСЕГДА ПОД РУКОЙ</small><h2>Аделия на вашем устройстве</h2><p>Отдельное окно. Привычный кабинет.</p></div></header><div class="install-platforms" role="group" aria-label="Ваше устройство">'+devices.map(([key,kind,name])=>'<button type="button" data-install-device="'+key+'" aria-pressed="'+(selected===key)+'"><span aria-hidden="true">'+(kind==='Телефон'?'▯':'▱')+'</span>'+name+'</button>').join('')+'</div><article class="install-pwa"><span class="install-tag">БЕЗ СКАЧИВАНИЯ ФАЙЛОВ</span><h3>Установить из браузера</h3><p>Иконка на устройстве и запуск в отдельном окне. Для отправки сообщений нужен интернет.</p><button type="button" data-pwa-action class="primary"></button><p data-install-state role="status" aria-live="polite"></p><ol data-install-guide></ol></article><section class="install-files"><h3>Приложение для компьютера</h3><p>Выберите процессор Mac в меню  → «Об этом Mac».</p><div class="install-downloads"></div><small>Отдельные сборки приложения. Установка PWA доступна выше.</small></section></section>';
app.querySelectorAll('[data-install-device]').forEach(b=>b.onclick=()=>{selected=b.dataset.installDevice;app.querySelectorAll('[data-install-device]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));updatePage();});
const targets=[['Windows · x64','Adelia-latest-windows-x64.exe'],['Mac · Apple Silicon','Adelia-latest-macos-arm64.dmg'],['Mac · Intel','Adelia-latest-macos-x64.dmg']];const list=app.querySelector('.install-downloads');for(const [name,file] of targets){const item=document.createElement('div'),label=document.createElement('b'),state=document.createElement('span');label.textContent=name;state.textContent='Проверяем доступность…';item.append(label,state);list.append(item);const url='/desktop-updates/'+file;fetch(url,{method:'HEAD',credentials:'same-origin',cache:'no-store'}).then(r=>{const type=r.headers.get('content-type')||'',size=Number(r.headers.get('content-length'));if(!r.ok||r.redirected||/text\/html|json/i.test(type)||size<1000000||!size)throw Error();if(!item.isConnected)return;const link=document.createElement('a');link.href=url;link.textContent='Скачать · '+Math.round(size/1048576)+' МБ';link.setAttribute('download','');state.replaceWith(link);}).catch(()=>{if(item.isConnected)state.textContent='Файл пока недоступен';});}
updatePage();}
function updatePage(){const page=document.querySelector('.install-hub');if(!page)return;const b=page.querySelector('[data-pwa-action]');b.disabled=busy||installed;b.textContent=installed?'Открыто как приложение':busy?'Открываем установку…':installEvent?'Установить PWA':'Показать инструкцию';b.onclick=()=>{if(installEvent)return install();else page.querySelector('[data-install-guide]').scrollIntoView({behavior:'smooth',block:'center'});};page.querySelector('[data-install-state]').textContent=note;page.querySelector('[data-install-guide]').innerHTML=guides[selected].map(x=>'<li>'+x+'</li>').join('');}
function mountHub(){const nav=document.querySelector('.teacher-shell nav');if(nav&&!nav.querySelector('[data-install-hub]')){const b=document.createElement('button');b.type='button';b.dataset.installHub='';b.innerHTML='<span class="ico" aria-hidden="true">↧</span><span>Установить Аделию</span>';b.onclick=openPage;nav.append(b);}if(location.hash==='#install')renderPage();}
document.addEventListener('click',e=>{if(e.target.closest('[data-install-hub]')){e.preventDefault();e.stopImmediatePropagation();openPage();return;}if(e.target.closest('nav [data-view]')&&location.hash==='#install'){history.replaceState(null,'',location.pathname+location.search);status();}},true);
window.addEventListener('hashchange',()=>{if(location.hash==='#install')openPage();else status();});
let redraw=false;const app=document.querySelector('#app');if(app)new MutationObserver(()=>{if(location.hash==='#install'&&!app.querySelector('.install-hub')&&!redraw){redraw=true;requestAnimationFrame(()=>{redraw=false;if(location.hash==='#install')renderPage();});}}).observe(app,{childList:true});

mountHub();status();
})();
