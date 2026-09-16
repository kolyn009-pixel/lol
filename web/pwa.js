(function(){
  let deferredPrompt=null;
  const standalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const ios=()=>/iphone|ipad|ipod/i.test(navigator.userAgent)&&!window.MSStream;
  const notificationSupported=()=>typeof window.Notification!=='undefined'&&typeof Notification.requestPermission==='function';
  const pushSupported=()=>notificationSupported()&&'serviceWorker' in navigator&&'PushManager' in window;
  const permission=()=>notificationSupported()?Notification.permission:'unsupported';
  const DISMISSED_KEY='adelia_notification_prompt_dismissed_v1';
  const api=async(url,options={})=>{const r=await fetch(url,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(options.headers||{})},...options});let d={};try{d=await r.json()}catch(_){}if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);return d};
  const b64ToBytes=value=>{const padding='='.repeat((4-value.length%4)%4);const base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/');const raw=atob(base64);return Uint8Array.from([...raw].map(ch=>ch.charCodeAt(0)))};

  async function serviceWorkerReady(){
    if(!('serviceWorker' in navigator))throw new Error('service_worker_unsupported');
    return navigator.serviceWorker.ready;
  }
  async function syncPushSubscription(){
    if(!pushSupported()||Notification.permission!=='granted')return {status:'permission_required'};
    const state=await api('/api/push/status');
    if(!state.public_key)return {status:'server_not_configured'};
    const reg=await serviceWorkerReady();
    let subscription=await reg.pushManager.getSubscription();
    if(!subscription)subscription=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(state.public_key)});
    const saved=await api('/api/push/subscribe',{method:'POST',body:JSON.stringify({subscription:subscription.toJSON()})});
    window.dispatchEvent(new CustomEvent('adelia:push-state',{detail:{status:'subscribed',subscription_id:saved.subscription_id}}));
    return {status:'subscribed',subscription_id:saved.subscription_id};
  }
  async function testPush(){
    await syncPushSubscription();
    return api('/api/push/test',{method:'POST',body:'{}'});
  }
  function injectNotificationStyles(){
    if(document.getElementById('adeliaNotificationStyles'))return;
    const s=document.createElement('style');s.id='adeliaNotificationStyles';s.textContent=`
      .adelia-notify-card{position:fixed;left:max(14px,env(safe-area-inset-left));right:max(14px,env(safe-area-inset-right));bottom:max(14px,calc(env(safe-area-inset-bottom) + 10px));z-index:2147483000;max-width:560px;margin:0 auto;padding:16px;border-radius:22px;background:rgba(255,255,255,.97);border:1px solid rgba(104,71,245,.16);box-shadow:0 18px 60px rgba(38,27,72,.2);backdrop-filter:blur(18px);font-family:inherit;color:#211b2d}
      .adelia-notify-card h3{margin:0 0 6px;font-size:17px;line-height:1.2}.adelia-notify-card p{margin:0;color:#756e80;font-size:13px;line-height:1.45}.adelia-notify-actions{display:flex;gap:9px;margin-top:13px}.adelia-notify-actions button{min-height:42px;border-radius:13px;padding:0 14px;font:inherit;font-weight:800;cursor:pointer}.adelia-notify-enable{flex:1;border:0;background:#7048d8;color:#fff}.adelia-notify-later{border:1px solid #e7e1ef;background:#fff;color:#625a6c}.adelia-notify-note{display:block;margin-top:8px;color:#938b9d;font-size:11px;line-height:1.35}.adelia-notify-error{margin-top:9px;padding:9px 10px;border-radius:12px;background:#fff5f2;color:#8e3b24;font-size:12px;line-height:1.35}
      @media(max-width:520px){.adelia-notify-card{padding:15px}.adelia-notify-actions{flex-direction:column}.adelia-notify-actions button{width:100%}}
    `;document.head.appendChild(s);
  }
  function removeNotificationCard(){document.getElementById('adeliaNotificationCard')?.remove()}
  function dismissed(){try{return localStorage.getItem(DISMISSED_KEY)==='1'}catch(_){return false}}
  function markDismissed(){try{localStorage.setItem(DISMISSED_KEY,'1')}catch(_){}}
  function reconcileNotificationCard(){
    if(!notificationSupported())return;
    if(Notification.permission==='denied')removeNotificationCard();
  }
  function notificationCopy(){
    if(ios()&&!standalone())return {title:'Включить уведомления Аделии',text:'На iPhone уведомления доступны после установки Аделии на экран «Домой».',action:'Как установить',mode:'install',note:'После установки откройте Аделию с домашнего экрана — там появится системный запрос.'};
    return {title:'Не пропускайте занятия и оплату',text:'Разрешите Аделии присылать уведомления о занятиях, домашних заданиях и важных изменениях.',action:'Включить уведомления',mode:'permission',note:'Разрешение можно изменить позже в настройках устройства.'};
  }
  function renderNotificationCard(copy,{force=false,error=''}={}){
    if(document.getElementById('adeliaNotificationCard'))removeNotificationCard();
    if(!force&&dismissed())return;
    injectNotificationStyles();
    const root=document.createElement('section');root.id='adeliaNotificationCard';root.className='adelia-notify-card';root.setAttribute('role','dialog');root.setAttribute('aria-label',copy.title);
    root.innerHTML=`<h3>🔔 ${copy.title}</h3><p>${copy.text}</p>${error?`<div class="adelia-notify-error">${String(error).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</div>`:''}<div class="adelia-notify-actions"><button type="button" class="adelia-notify-enable">${copy.action}</button><button type="button" class="adelia-notify-later">Позже</button></div><small class="adelia-notify-note">${copy.note||''}</small>`;
    root.querySelector('.adelia-notify-later').onclick=()=>{markDismissed();removeNotificationCard()};
    root.querySelector('.adelia-notify-enable').onclick=async()=>{
      const btn=root.querySelector('.adelia-notify-enable');btn.disabled=true;const before=btn.textContent;btn.textContent='Подключаю…';
      try{
        if(copy.mode==='install'){const result=await window.AdeliaPWA.install();if(result?.message)alert(result.message);return}
        if(copy.mode==='retry'){
          const result=await syncPushSubscription();
          if(result?.status==='subscribed'){removeNotificationCard();return}
          throw new Error(result?.status||'push_subscription_failed');
        }
        await requestNotifications();
      }catch(err){showPushRecoveryCard(err)}finally{if(document.body.contains(btn)){btn.disabled=false;btn.textContent=before}}
    };
    document.body.appendChild(root);
  }
  function showPushRecoveryCard(err){
    const msg=String(err&&err.message||err||'Не удалось зарегистрировать устройство для push-уведомлений.');
    renderNotificationCard({title:'Уведомления разрешены, но устройство ещё не подключено',text:'iPhone уже разрешил уведомления Аделии. Осталось зарегистрировать это устройство для получения push.',action:'Повторить подключение',mode:'retry',note:'Если ошибка повторится, Аделия сохранит разрешение — повторно подтверждать его в iOS не придётся.'},{force:true,error:msg});
  }
  async function requestNotifications(){
    if(ios()&&!standalone())return {status:'install_required'};
    if(!notificationSupported())return {status:'unsupported'};
    try{
      let result=Notification.permission;
      if(result==='default')result=await Notification.requestPermission();
      window.dispatchEvent(new CustomEvent('adelia:notification-permission',{detail:{permission:result}}));
      if(result==='granted'){
        try{
          const synced=await syncPushSubscription();
          if(synced?.status==='subscribed')removeNotificationCard();
          else showPushRecoveryCard(synced?.status||'push_subscription_failed');
          return synced;
        }catch(err){console.warn('PWA push subscribe:',err);showPushRecoveryCard(err);return {status:'granted',push_status:'sync_failed',error:String(err&&err.message||err)}}
      }
      if(result==='denied'){markDismissed();removeNotificationCard()}
      return {status:result};
    }catch(err){showPushRecoveryCard(err);return {status:'error',error:String(err&&err.message||err)}}
  }
  function showNotificationCard(force=false){
    if(document.getElementById('adeliaNotificationCard'))return;
    if(!force&&dismissed())return;
    if(!notificationSupported()&&!(ios()&&!standalone()))return;
    if(notificationSupported()&&Notification.permission==='granted'){
      syncPushSubscription().then(result=>{if(result?.status==='subscribed')removeNotificationCard();else showPushRecoveryCard(result?.status)}).catch(showPushRecoveryCard);
      return;
    }
    if(notificationSupported()&&Notification.permission==='denied')return;
    renderNotificationCard(notificationCopy(),{force});
  }
  window.AdeliaPWA={isStandalone:standalone,isIOS:ios,canInstall:()=>!!deferredPrompt||(!standalone()&&ios()),notificationPermission:permission,requestNotifications,syncPushSubscription,testPush,showNotificationPrompt:()=>showNotificationCard(true),async install(){if(standalone())return {status:'installed'};if(!deferredPrompt){if(ios())return {status:'manual',message:'В Safari нажмите «Поделиться», затем «На экран Домой».'};return {status:'unavailable'}}const prompt=deferredPrompt;deferredPrompt=null;await prompt.prompt();const choice=await prompt.userChoice.catch(()=>null);window.dispatchEvent(new CustomEvent('adelia:pwa-state'));return {status:choice?.outcome||'dismissed'}}};
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredPrompt=event;window.dispatchEvent(new CustomEvent('adelia:pwa-state'))});
  window.addEventListener('appinstalled',()=>{deferredPrompt=null;window.dispatchEvent(new CustomEvent('adelia:pwa-state'))});
  window.addEventListener('adelia:notification-permission',reconcileNotificationCard);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&Notification.permission==='granted'&&!document.getElementById('adeliaNotificationCard'))syncPushSubscription().catch(showPushRecoveryCard)});
  window.addEventListener('focus',()=>{if(Notification.permission==='granted'&&!document.getElementById('adeliaNotificationCard'))syncPushSubscription().catch(showPushRecoveryCard)});
  if('serviceWorker' in navigator){window.addEventListener('load',()=>{navigator.serviceWorker.register('/app/service-worker.js',{scope:'/app/'}).then(async reg=>{if(reg.waiting)reg.waiting.postMessage({type:'SKIP_WAITING'});if(Notification.permission==='granted'){try{const result=await syncPushSubscription();if(result?.status!=='subscribed')showPushRecoveryCard(result?.status)}catch(err){console.warn('PWA push sync:',err);showPushRecoveryCard(err)}}}).catch(err=>{console.warn('PWA service worker:',err);if(Notification.permission==='granted')showPushRecoveryCard(err)})});navigator.serviceWorker.addEventListener('controllerchange',()=>window.dispatchEvent(new CustomEvent('adelia:pwa-state')))}
  window.addEventListener('load',()=>setTimeout(()=>showNotificationCard(false),1800));
})();
