(function(){
  let deferredPrompt=null;
  const standalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const ios=()=>/iphone|ipad|ipod/i.test(navigator.userAgent)&&!window.MSStream;
  const notificationSupported=()=>typeof window.Notification!=='undefined'&&typeof Notification.requestPermission==='function';
  const permission=()=>notificationSupported()?Notification.permission:'unsupported';
  const DISMISSED_KEY='adelia_notification_prompt_dismissed_v1';

  function injectNotificationStyles(){
    if(document.getElementById('adeliaNotificationStyles'))return;
    const s=document.createElement('style');s.id='adeliaNotificationStyles';s.textContent=`
      .adelia-notify-card{position:fixed;left:max(14px,env(safe-area-inset-left));right:max(14px,env(safe-area-inset-right));bottom:max(14px,calc(env(safe-area-inset-bottom) + 10px));z-index:2147483000;max-width:560px;margin:0 auto;padding:16px;border-radius:22px;background:rgba(255,255,255,.97);border:1px solid rgba(104,71,245,.16);box-shadow:0 18px 60px rgba(38,27,72,.2);backdrop-filter:blur(18px);font-family:inherit;color:#211b2d}
      .adelia-notify-card h3{margin:0 0 6px;font-size:17px;line-height:1.2}.adelia-notify-card p{margin:0;color:#756e80;font-size:13px;line-height:1.45}.adelia-notify-actions{display:flex;gap:9px;margin-top:13px}.adelia-notify-actions button{min-height:42px;border-radius:13px;padding:0 14px;font:inherit;font-weight:800;cursor:pointer}.adelia-notify-enable{flex:1;border:0;background:#7048d8;color:#fff}.adelia-notify-later{border:1px solid #e7e1ef;background:#fff;color:#625a6c}.adelia-notify-note{display:block;margin-top:8px;color:#938b9d;font-size:11px;line-height:1.35}
      @media(max-width:520px){.adelia-notify-card{padding:15px}.adelia-notify-actions{flex-direction:column}.adelia-notify-actions button{width:100%}}
    `;document.head.appendChild(s);
  }
  function removeNotificationCard(){document.getElementById('adeliaNotificationCard')?.remove()}
  function dismissed(){try{return localStorage.getItem(DISMISSED_KEY)==='1'}catch(_){return false}}
  function markDismissed(){try{localStorage.setItem(DISMISSED_KEY,'1')}catch(_){}}
  function notificationCopy(){
    if(ios()&&!standalone())return {title:'Включить уведомления Аделии',text:'На iPhone уведомления доступны после установки Аделии на экран «Домой».',action:'Как установить',mode:'install',note:'После установки откройте Аделию с домашнего экрана — там появится системный запрос.'};
    return {title:'Не пропускайте занятия и оплату',text:'Разрешите Аделии присылать уведомления о занятиях, домашних заданиях и важных изменениях.',action:'Включить уведомления',mode:'permission',note:'Разрешение можно изменить позже в настройках устройства.'};
  }
  async function requestNotifications(){
    if(ios()&&!standalone())return {status:'install_required'};
    if(!notificationSupported())return {status:'unsupported'};
    if(Notification.permission!=='default')return {status:Notification.permission};
    try{
      const result=await Notification.requestPermission();
      window.dispatchEvent(new CustomEvent('adelia:notification-permission',{detail:{permission:result}}));
      return {status:result};
    }catch(err){return {status:'error',error:String(err&&err.message||err)}}
  }
  function showNotificationCard(force=false){
    if(document.getElementById('adeliaNotificationCard'))return;
    if(!force&&dismissed())return;
    if(notificationSupported()&&Notification.permission!=='default')return;
    if(!notificationSupported()&&!(ios()&&!standalone()))return;
    injectNotificationStyles();
    const copy=notificationCopy();
    const root=document.createElement('section');root.id='adeliaNotificationCard';root.className='adelia-notify-card';root.setAttribute('role','dialog');root.setAttribute('aria-label',copy.title);
    root.innerHTML=`<h3>🔔 ${copy.title}</h3><p>${copy.text}</p><div class="adelia-notify-actions"><button type="button" class="adelia-notify-enable">${copy.action}</button><button type="button" class="adelia-notify-later">Позже</button></div><small class="adelia-notify-note">${copy.note}</small>`;
    root.querySelector('.adelia-notify-later').onclick=()=>{markDismissed();removeNotificationCard()};
    root.querySelector('.adelia-notify-enable').onclick=async()=>{
      if(copy.mode==='install'){
        const result=await window.AdeliaPWA.install();
        if(result?.message)alert(result.message);
        return;
      }
      const result=await requestNotifications();
      if(result.status==='granted')removeNotificationCard();
      else if(result.status==='denied'){markDismissed();removeNotificationCard()}
    };
    document.body.appendChild(root);
  }

  window.AdeliaPWA={
    isStandalone:standalone,
    isIOS:ios,
    canInstall:()=>!!deferredPrompt||(!standalone()&&ios()),
    notificationPermission:permission,
    requestNotifications,
    showNotificationPrompt:()=>showNotificationCard(true),
    async install(){
      if(standalone())return {status:'installed'};
      if(!deferredPrompt){
        if(ios())return {status:'manual',message:'В Safari нажмите «Поделиться», затем «На экран Домой».'};
        return {status:'unavailable'};
      }
      const prompt=deferredPrompt;deferredPrompt=null;
      await prompt.prompt();
      const choice=await prompt.userChoice.catch(()=>null);
      window.dispatchEvent(new CustomEvent('adelia:pwa-state'));
      return {status:choice?.outcome||'dismissed'};
    }
  };
  window.addEventListener('beforeinstallprompt',event=>{
    event.preventDefault();deferredPrompt=event;
    window.dispatchEvent(new CustomEvent('adelia:pwa-state'));
  });
  window.addEventListener('appinstalled',()=>{
    deferredPrompt=null;
    window.dispatchEvent(new CustomEvent('adelia:pwa-state'));
  });
  if('serviceWorker' in navigator){
    window.addEventListener('load',()=>{
      navigator.serviceWorker.register('/app/service-worker.js',{scope:'/app/'}).then(reg=>{
        if(reg.waiting)reg.waiting.postMessage({type:'SKIP_WAITING'});
      }).catch(err=>console.warn('PWA service worker:',err));
    });
    navigator.serviceWorker.addEventListener('controllerchange',()=>window.dispatchEvent(new CustomEvent('adelia:pwa-state')));
  }
  window.addEventListener('load',()=>setTimeout(()=>showNotificationCard(false),1800));
})();
