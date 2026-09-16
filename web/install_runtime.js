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
    try{const u=new URL(reqUrl,location.origin);path=u.pathname+u.search}catch{}
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
      .adelia-install-bar{position:fixed;left:50%;bottom:82px;z-index:90;transform:translateX(-50%);width:min(600px,calc(100% - 24px));display:grid;grid-template-columns:46px minmax(0,1fr) auto auto;align-items:center;gap:11px;padding:11px 12px;border:1px solid rgba(112,72,216,.18);border-radius:19px;background:rgba(255,255,255,.97);box-shadow:0 16px 44px rgba(38,24,79,.17);backdrop-filter:blur(18px)}.adelia-install-bar[hidden]{display:none!important}.adelia-install-icon{display:grid;place-items:center;width:46px;height:46px;border-radius:15px;background:linear-gradient(145deg,#7450e8,#8f72f2);color:#fff;font-size:22px;box-shadow:0 8px 20px rgba(112,72,216,.24)}.adelia-install-copy{min-width:0}.adelia-install-copy b{display:block;font-size:14px;color:#24183f}.adelia-install-copy small{display:block;margin-top:3px;color:#746d82;font-size:11px;line-height:1.3}.adelia-install-btn{border:0;border-radius:13px;background:#7048d8;color:#fff;padding:10px 13px;font:inherit;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}.adelia-install-close{border:0;background:transparent;color:#817a8e;font-size:20px;cursor:pointer;padding:4px}.adelia-install-modal{position:fixed;inset:0;z-index:120;display:grid;place-items:end center;background:rgba(20,14,34,.42);padding:14px}.adelia-install-modal[hidden]{display:none}.adelia-install-card{width:min(590px,100%);max-height:min(760px,calc(100dvh - 28px));overflow:auto;background:#fff;border-radius:26px;padding:20px;box-shadow:0 24px 80px rgba(0,0,0,.26)}.adelia-install-hero{display:flex;align-items:center;gap:13px;padding:4px 2px 16px}.adelia-install-hero-icon{display:grid;place-items:center;flex:0 0 52px;width:52px;height:52px;border-radius:16px;background:linear-gradient(145deg,#7048d8,#9b82f5);color:#fff;font-size:26px}.adelia-install-card h3{margin:0 0 5px;font-size:22px;letter-spacing:-.02em}.adelia-install-card p{margin:0;color:#625b70;line-height:1.5}.adelia-install-note{margin:12px 0 0!important;padding:11px 12px;border-radius:14px;background:#f5f1ff;color:#5c4b85!important;font-size:12px}.adelia-install-steps{display:grid;gap:9px;margin:16px 0}.adelia-install-step{display:grid;grid-template-columns:38px 1fr;gap:11px;align-items:start;padding:12px;border:1px solid #eee9f5;border-radius:16px;background:#fbf9ff}.adelia-install-step b{display:grid;place-items:center;width:38px;height:38px;border-radius:12px;background:#ede7ff;color:#7048d8}.adelia-install-step span{padding-top:7px;color:#443b51;line-height:1.45}.adelia-install-card button{width:100%;border:0;border-radius:14px;padding:13px;font:inherit;font-weight:800;background:#7048d8;color:#fff;cursor:pointer}.adelia-install-secondary{margin-top:8px!important;background:#f1edf8!important;color:#5e5272!important}.adelia-install-help{display:block;margin-top:12px;text-align:center;color:#80768d;font-size:11px;line-height:1.45}@media(min-width:900px){.adelia-install-bar{bottom:24px;left:auto;right:24px;transform:none;width:470px}}@media(max-width:520px){.adelia-install-bar{grid-template-columns:40px minmax(0,1fr) auto;bottom:max(76px,calc(70px + env(safe-area-inset-bottom)));gap:9px}.adelia-install-icon{width:40px;height:40px;border-radius:13px;font-size:19px}.adelia-install-copy small{white-space:normal}.adelia-install-close{position:absolute;right:5px;top:-30px;width:28px;height:28px;border-radius:50%;background:#fff;box-shadow:0 6px 18px rgba(0,0,0,.12)}.adelia-install-btn{padding:10px 11px}.adelia-install-card{padding:17px;border-radius:24px}}body.adelia-auth-screen .adelia-install-bar{display:none!important}
    `;document.head.appendChild(s);
  }

  function guide(){
    if(isiOS())return {icon:'',title:'Установить Аделию на iPhone',intro:'Установка делается через Safari и после этого Аделия открывается как обычное приложение.',note:'Важно: если ссылка открылась во встроенном браузере Telegram/VK, нажмите «Открыть в Safari» и продолжайте там.',steps:['Откройте adeliatutor.ru/app/ в Safari.','Нажмите кнопку «Поделиться» — квадрат со стрелкой вверх.','В меню прокрутите вниз и выберите «На экран Домой».','Нажмите «Добавить» в правом верхнем углу.','Запустите Аделию с нового значка на экране Домой.','В Аделии разрешите уведомления, когда появится запрос.']};
    if(isAndroid())return {icon:'🤖',title:'Установить Аделию на Android',intro:'Лучше всего использовать Chrome — тогда Аделия устанавливается как отдельное приложение.',note:'Если пункта установки нет, сначала откройте сайт именно в Chrome, а не внутри Telegram/VK.',steps:['Откройте adeliatutor.ru/app/ в Chrome.','Нажмите меню ⋮ справа сверху.','Выберите «Установить приложение» или «Добавить на главный экран».','Подтвердите установку.','Запустите Аделию с появившегося значка.','Разрешите уведомления о занятиях, ДЗ и оплате.']};
    return {icon:'💻',title:'Установить Аделию',intro:'На компьютере Аделия может работать как отдельное приложение без вкладки браузера.',note:'Chrome и Edge дают самый предсказуемый вариант установки.',steps:['Откройте Аделию в Chrome или Edge.','Нажмите значок установки в адресной строке либо откройте меню браузера.','Выберите «Установить Аделию».','Подтвердите установку и закрепите приложение при желании.']};
  }

  function modal(message,asGuide=false){
    let wrap=document.getElementById('adelia-install-modal');if(!wrap){wrap=document.createElement('div');wrap.id='adelia-install-modal';wrap.className='adelia-install-modal';wrap.addEventListener('click',e=>{if(e.target===wrap)wrap.hidden=true});document.body.appendChild(wrap)}
    if(asGuide){const g=guide();wrap.innerHTML=`<div class="adelia-install-card"><div class="adelia-install-hero"><div class="adelia-install-hero-icon">${g.icon}</div><div><h3>${g.title}</h3><p>${g.intro}</p></div></div><p class="adelia-install-note">${g.note}</p><div class="adelia-install-steps">${g.steps.map((x,i)=>`<div class="adelia-install-step"><b>${i+1}</b><span>${x}</span></div>`).join('')}</div><button type="button" data-install-close>Понятно, установить</button><button type="button" class="adelia-install-secondary" data-install-copy>Скопировать адрес Аделии</button><small class="adelia-install-help">После установки запускайте Аделию именно с иконки на экране телефона — так корректнее работают полноэкранный режим и push-уведомления.</small></div>`;wrap.querySelector('[data-install-copy]').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.origin+'/app/');wrap.querySelector('[data-install-copy]').textContent='Адрес скопирован ✓'}catch(_){}})}else wrap.innerHTML=`<div class="adelia-install-card"><div class="adelia-install-hero"><div class="adelia-install-hero-icon">💜</div><div><h3>Установка Аделии</h3><p>${message}</p></div></div><button type="button" data-install-close>Понятно</button></div>`;
    wrap.querySelector('[data-install-close]').addEventListener('click',()=>wrap.hidden=true);wrap.hidden=false;
  }

  async function install(){
    if(standalone())return modal('Аделия уже установлена на этом устройстве. Запускайте её с иконки приложения.');
    const api=window.AdeliaPWA;
    if(api&&typeof api.install==='function'&&!isiOS())try{const result=await api.install();if(result&&['accepted','installed'].includes(result.status))return;if(result&&result.status==='dismissed')return modal('',true)}catch(e){console.warn('Adelia install:',e)}
    if(isiOS()||isAndroid())return modal('',true);
    if(isMac()&&!isChrome()&&!isEdge())return modal('На Mac откройте Аделию в Chrome или Edge. В Safari также можно использовать «Файл → Добавить в Dock», если этот пункт доступен.');
    if(isChrome()||isEdge())return modal('Если системное окно не появилось, нажмите значок установки справа в адресной строке или откройте меню браузера → «Установить Аделию».');
    modal('',true);
  }

  function mount(){style();if(!document.getElementById('adelia-install-bar')){const bar=document.createElement('div');bar.id='adelia-install-bar';bar.className='adelia-install-bar';bar.innerHTML='<div class="adelia-install-icon">↧</div><div class="adelia-install-copy"><b>Установить Аделию на телефон</b><small>Пошаговая инструкция для iPhone и Android</small></div><button class="adelia-install-btn" type="button">Инструкция</button><button class="adelia-install-close" type="button" aria-label="Скрыть">×</button>';bar.querySelector('.adelia-install-btn').addEventListener('click',install);bar.querySelector('.adelia-install-close').addEventListener('click',()=>{bar.hidden=true;sessionStorage.setItem('adelia-install-dismissed','1')});document.body.appendChild(bar)}const bar=document.getElementById('adelia-install-bar');bar.hidden=standalone()||sessionStorage.getItem('adelia-install-dismissed')==='1'}
  document.addEventListener('click',e=>{const target=e.target.closest('[data-install-adelia]');if(!target)return;e.preventDefault();install()},true);
  window.AdeliaInstall={open:install,guide};window.addEventListener('adelia:pwa-state',mount);window.addEventListener('appinstalled',()=>{const b=document.getElementById('adelia-install-bar');if(b)b.hidden=true});if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
