(function(){
  'use strict';

  const CACHE_TTL={
    '/api/auth/me':30000,
    '/api/student/dashboard':15000,
    '/api/student/profile':30000,
    '/api/student/schedule?limit=60':12000,
    '/api/student/payments':12000,
    '/api/student/homework':12000,
    '/api/student/messages?limit=100':5000
  };
  const cache=new Map();
  const nativeFetch=window.fetch.bind(window);

  window.fetch=async function(input,init={}){
    const reqUrl=typeof input==='string'?input:(input&&input.url)||'';
    const method=String(init.method||(typeof input!=='string'&&input&&input.method)||'GET').toUpperCase();
    let path=reqUrl;
    try{path=new URL(reqUrl,location.origin).pathname+new URL(reqUrl,location.origin).search}catch{}
    if(method!=='GET'){cache.clear();return nativeFetch(input,init)}
    const ttl=CACHE_TTL[path];if(!ttl)return nativeFetch(input,init);
    const now=Date.now(),hit=cache.get(path);
    if(hit&&now-hit.time<ttl)return new Response(hit.body,{status:hit.status,statusText:hit.statusText,headers:new Headers(hit.headers)});
    const response=await nativeFetch(input,init);
    if(response.ok){const clone=response.clone();const body=await clone.text();cache.set(path,{time:now,body,status:response.status,statusText:response.statusText,headers:[...response.headers.entries()]})}
    return response;
  };

  const standalone=()=>window.matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  const isiOS=()=>/iphone|ipad|ipod/i.test(navigator.userAgent);
  const isAndroid=()=>/Android/i.test(navigator.userAgent);
  const isMac=()=>/Macintosh|Mac OS X/i.test(navigator.userAgent);
  const isEdge=()=>/Edg\//.test(navigator.userAgent);
  const isChrome=()=>/Chrome\//.test(navigator.userAgent)&&!isEdge();

  function style(){
    if(document.getElementById('adelia-install-style'))return;
    const s=document.createElement('style');s.id='adelia-install-style';s.textContent=`
      .adelia-install-bar{position:fixed;left:50%;bottom:82px;z-index:90;transform:translateX(-50%);width:min(560px,calc(100% - 28px));display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid rgba(112,72,216,.18);border-radius:18px;background:rgba(255,255,255,.96);box-shadow:0 14px 40px rgba(38,24,79,.16);backdrop-filter:blur(18px)}.adelia-install-bar[hidden]{display:none!important}.adelia-install-copy{min-width:0;flex:1}.adelia-install-copy b{display:block;font-size:14px;color:#24183f}.adelia-install-copy small{display:block;margin-top:2px;color:#746d82;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.adelia-install-btn{border:0;border-radius:13px;background:#7048d8;color:#fff;padding:10px 14px;font:inherit;font-weight:800;cursor:pointer;white-space:nowrap}.adelia-install-close{border:0;background:transparent;color:#817a8e;font-size:20px;cursor:pointer;padding:4px}.adelia-install-modal{position:fixed;inset:0;z-index:120;display:grid;place-items:end center;background:rgba(20,14,34,.38);padding:18px}.adelia-install-modal[hidden]{display:none}.adelia-install-card{width:min(560px,100%);background:#fff;border-radius:24px;padding:20px;box-shadow:0 20px 70px rgba(0,0,0,.22)}.adelia-install-card h3{margin:0 0 8px}.adelia-install-card p{margin:0;color:#625b70;line-height:1.5}.adelia-install-steps{display:grid;gap:9px;margin:16px 0}.adelia-install-step{display:grid;grid-template-columns:34px 1fr;gap:10px;align-items:start;padding:11px;border-radius:15px;background:#f8f5fd}.adelia-install-step b{display:grid;place-items:center;width:34px;height:34px;border-radius:11px;background:#ede7ff;color:#7048d8}.adelia-install-step span{padding-top:6px;color:#443b51;line-height:1.4}.adelia-install-card button{width:100%;border:0;border-radius:14px;padding:12px;font:inherit;font-weight:800;background:#7048d8;color:#fff;cursor:pointer}@media(min-width:900px){.adelia-install-bar{bottom:24px;left:auto;right:24px;transform:none;width:420px}}body.adelia-auth-screen .adelia-install-bar{display:none!important}
    `;document.head.appendChild(s);
  }
  function guide(){
    if(isiOS())return {title:'Установка на iPhone / iPad',intro:'Откройте Аделию именно в Safari. Установка занимает меньше минуты.',steps:['Нажмите кнопку «Поделиться» в Safari.','Прокрутите меню и выберите «На экран Домой».','Нажмите «Добавить», затем запускайте Аделию с нового значка.','Откройте профиль Аделии и разрешите уведомления, когда появится запрос.']};
    if(isAndroid())return {title:'Установка на Android',intro:'Лучше всего устанавливать Аделию через Chrome.',steps:['Откройте меню Chrome ⋮.','Нажмите «Установить приложение» или «Добавить на главный экран».','Подтвердите установку и откройте Аделию с главного экрана.','Разрешите уведомления о занятиях, ДЗ и оплате.']};
    return {title:'Установка Аделии',intro:'Аделию можно запускать как отдельное приложение.',steps:['Откройте сайт в Chrome или Edge.','Нажмите «Установить» в адресной строке или меню браузера.','Подтвердите установку.']};
  }
  function modal(message,asGuide=false){
    let wrap=document.getElementById('adelia-install-modal');if(!wrap){wrap=document.createElement('div');wrap.id='adelia-install-modal';wrap.className='adelia-install-modal';wrap.addEventListener('click',e=>{if(e.target===wrap)wrap.hidden=true});document.body.appendChild(wrap)}
    if(asGuide){const g=guide();wrap.innerHTML=`<div class="adelia-install-card"><h3>${g.title}</h3><p>${g.intro}</p><div class="adelia-install-steps">${g.steps.map((x,i)=>`<div class="adelia-install-step"><b>${i+1}</b><span>${x}</span></div>`).join('')}</div><button type="button">Понятно</button></div>`}else wrap.innerHTML=`<div class="adelia-install-card"><h3>Установка Аделии</h3><p>${message}</p><div style="height:14px"></div><button type="button">Понятно</button></div>`;
    wrap.querySelector('button').addEventListener('click',()=>wrap.hidden=true);wrap.hidden=false;
  }
  async function install(){
    if(standalone())return modal('Аделия уже установлена на этом устройстве.');
    const api=window.AdeliaPWA;
    if(api&&typeof api.install==='function'&&!isiOS())try{const result=await api.install();if(result&&['accepted','installed','dismissed'].includes(result.status))return}catch(e){console.warn('Adelia install:',e)}
    if(isiOS()||isAndroid())return modal('',true);
    if(isMac()&&!isChrome()&&!isEdge())return modal('На Mac откройте Аделию в Chrome или Edge. В Safari также можно использовать «Файл → Добавить в Dock», если этот пункт доступен.');
    if(isChrome()||isEdge())return modal('Если системное окно не появилось, нажмите значок установки справа в адресной строке или откройте меню браузера → «Установить Аделию».');
    modal('',true);
  }
  function mount(){style();if(!document.getElementById('adelia-install-bar')){const bar=document.createElement('div');bar.id='adelia-install-bar';bar.className='adelia-install-bar';bar.innerHTML='<div class="adelia-install-copy"><b>Аделия как приложение</b><small>iPhone, Android и компьютер · инструкция внутри</small></div><button class="adelia-install-btn" type="button">Установить</button><button class="adelia-install-close" type="button" aria-label="Скрыть">×</button>';bar.querySelector('.adelia-install-btn').addEventListener('click',install);bar.querySelector('.adelia-install-close').addEventListener('click',()=>{bar.hidden=true;sessionStorage.setItem('adelia-install-dismissed','1')});document.body.appendChild(bar)}const bar=document.getElementById('adelia-install-bar');bar.hidden=standalone()||sessionStorage.getItem('adelia-install-dismissed')==='1'}
  document.addEventListener('click',e=>{const target=e.target.closest('[data-install-adelia]');if(!target)return;e.preventDefault();install()},true);
  window.AdeliaInstall={open:install,guide};window.addEventListener('adelia:pwa-state',mount);window.addEventListener('appinstalled',()=>{const b=document.getElementById('adelia-install-bar');if(b)b.hidden=true});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
