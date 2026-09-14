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

    if(method!=='GET'){
      cache.clear();
      return nativeFetch(input,init);
    }

    const ttl=CACHE_TTL[path];
    if(!ttl)return nativeFetch(input,init);

    const now=Date.now();
    const hit=cache.get(path);
    if(hit&&now-hit.time<ttl){
      return new Response(hit.body,{status:hit.status,statusText:hit.statusText,headers:new Headers(hit.headers)});
    }

    const response=await nativeFetch(input,init);
    if(response.ok){
      const clone=response.clone();
      const body=await clone.text();
      cache.set(path,{time:now,body,status:response.status,statusText:response.statusText,headers:[...response.headers.entries()]});
    }
    return response;
  };

  function standalone(){
    return window.matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  }
  function isiOS(){return /iphone|ipad|ipod/i.test(navigator.userAgent)}
  function isMac(){return /Macintosh|Mac OS X/i.test(navigator.userAgent)}
  function isEdge(){return /Edg\//.test(navigator.userAgent)}
  function isChrome(){return /Chrome\//.test(navigator.userAgent)&&!isEdge()}

  function style(){
    if(document.getElementById('adelia-install-style'))return;
    const s=document.createElement('style');
    s.id='adelia-install-style';
    s.textContent=`
      .adelia-install-bar{position:fixed;left:50%;bottom:82px;z-index:90;transform:translateX(-50%);width:min(560px,calc(100% - 28px));display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid rgba(112,72,216,.18);border-radius:18px;background:rgba(255,255,255,.96);box-shadow:0 14px 40px rgba(38,24,79,.16);backdrop-filter:blur(18px)}
      .adelia-install-bar[hidden]{display:none!important}.adelia-install-copy{min-width:0;flex:1}.adelia-install-copy b{display:block;font-size:14px;color:#24183f}.adelia-install-copy small{display:block;margin-top:2px;color:#746d82;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.adelia-install-btn{border:0;border-radius:13px;background:#7048d8;color:#fff;padding:10px 14px;font:inherit;font-weight:800;cursor:pointer;white-space:nowrap}.adelia-install-close{border:0;background:transparent;color:#817a8e;font-size:20px;cursor:pointer;padding:4px}.adelia-install-modal{position:fixed;inset:0;z-index:120;display:grid;place-items:end center;background:rgba(20,14,34,.38);padding:18px}.adelia-install-modal[hidden]{display:none}.adelia-install-card{width:min(520px,100%);background:#fff;border-radius:22px;padding:20px;box-shadow:0 20px 70px rgba(0,0,0,.22)}.adelia-install-card h3{margin:0 0 8px}.adelia-install-card p{margin:0 0 14px;color:#625b70;line-height:1.5}.adelia-install-card button{width:100%;border:0;border-radius:14px;padding:12px;font:inherit;font-weight:800;background:#7048d8;color:#fff;cursor:pointer}@media(min-width:900px){.adelia-install-bar{bottom:24px;left:auto;right:24px;transform:none;width:420px}}
      body.adelia-auth-screen .adelia-install-bar{display:none!important}
    `;
    document.head.appendChild(s);
  }

  function modal(message){
    let wrap=document.getElementById('adelia-install-modal');
    if(!wrap){
      wrap=document.createElement('div');
      wrap.id='adelia-install-modal';
      wrap.className='adelia-install-modal';
      wrap.innerHTML='<div class="adelia-install-card"><h3>Установка Аделии</h3><p id="adelia-install-message"></p><button type="button">Понятно</button></div>';
      wrap.querySelector('button').addEventListener('click',()=>wrap.hidden=true);
      wrap.addEventListener('click',e=>{if(e.target===wrap)wrap.hidden=true});
      document.body.appendChild(wrap);
    }
    wrap.querySelector('#adelia-install-message').textContent=message;
    wrap.hidden=false;
  }

  async function install(){
    if(standalone()){modal('Аделия уже установлена на этом устройстве.');return}
    const api=window.AdeliaPWA;
    if(api&&typeof api.install==='function'){
      try{
        const result=await api.install();
        if(result&&result.status==='accepted')return;
        if(result&&result.status==='installed')return;
        if(result&&result.status==='manual')return modal(result.message||'В Safari нажмите «Поделиться» → «На экран Домой».');
        if(result&&result.status==='dismissed')return;
      }catch(e){console.warn('Adelia install:',e)}
    }
    if(isiOS())return modal('В Safari нажмите «Поделиться», затем «На экран Домой».');
    if(isMac()&&!isChrome()&&!isEdge())return modal('На Mac откройте Аделию в Chrome или Edge и нажмите эту кнопку ещё раз. В Safari можно использовать «Файл → Добавить в Dock», если пункт доступен.');
    if(isChrome()||isEdge())return modal('Браузер пока не выдал системное окно установки. Обновите страницу один раз и нажмите «Установить» снова. Если кнопка установки есть справа в адресной строке — можно нажать её.');
    modal('Для установки на компьютер откройте Аделию в Chrome или Edge.');
  }

  function mount(){
    style();
    if(!document.getElementById('adelia-install-bar')){
      const bar=document.createElement('div');
      bar.id='adelia-install-bar';
      bar.className='adelia-install-bar';
      bar.innerHTML='<div class="adelia-install-copy"><b>Аделия как приложение</b><small>Работает с рабочего стола без лишних вкладок</small></div><button class="adelia-install-btn" type="button">Установить</button><button class="adelia-install-close" type="button" aria-label="Скрыть">×</button>';
      bar.querySelector('.adelia-install-btn').addEventListener('click',install);
      bar.querySelector('.adelia-install-close').addEventListener('click',()=>{bar.hidden=true;sessionStorage.setItem('adelia-install-dismissed','1')});
      document.body.appendChild(bar);
    }
    const bar=document.getElementById('adelia-install-bar');
    bar.hidden=standalone()||sessionStorage.getItem('adelia-install-dismissed')==='1';
  }

  document.addEventListener('click',e=>{
    const target=e.target.closest('[data-install-adelia]');
    if(!target)return;
    e.preventDefault();
    install();
  },true);

  window.addEventListener('adelia:pwa-state',mount);
  window.addEventListener('appinstalled',()=>{const b=document.getElementById('adelia-install-bar');if(b)b.hidden=true});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
