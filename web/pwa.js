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
  async function currentSubscription(){
    if(!pushSupported())return null;
    const reg=await serviceWorkerReady();
    return reg.pushManager.getSubscription();
  }
  async function persistSubscription(subscription){
    const saved=await api('/api/push/subscribe',{method:'POST',body:JSON.stringify({subscription:subscription.toJSON()})});
    window.dispatchEvent(new CustomEvent('adelia:push-state',{detail:{status:'subscribed',subscription_id:saved.subscription_id}}));
    removePushAction();removeNotificationCard();
    return {status:'subscribed',subscription_id:saved.subscription_id};
  }
  async function syncExistingSubscription(){
    if(!pushSupported()||Notification.permission!=='granted')return {status:'permission_required'};
    const state=await api('/api/push/status');
    if(!state.public_key)return {status:'server_not_configured'};
    const subscription=await currentSubscription();
    if(!subscription)return {status:'user_gesture_required'};
    return persistSubscription(subscription);
  }
  async function subscribeFromGesture(){
    if(!pushSupported())throw new Error('push_unsupported');
    const state=await api('/api/push/status');
    if(!state.public_key)throw new Error('server_not_configured');
    const reg=await serviceWorkerReady();
    let subscription=await reg.pushManager.getSubscription();
    if(!subscription)subscription=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToBytes(state.public_key)});
    return persistSubscription(subscription);
  }
  async function syncPushSubscription(){
    const result=await syncExistingSubscription();
    if(result.status==='user_gesture_required')mountPushAction('Нажмите, чтобы завершить подключение уведомлений');
    return result;
  }
  async function testPush(){await subscribeFromGesture();return api('/api/push/test',{method:'POST',body:'{}'})}

  function injectNotificationStyles(){
    if(document.getElementById('adeliaNotificationStyles'))return;
    const s=document.createElement('style');s.id='adeliaNotificationStyles';s.textContent=`
      .adelia-notify-card{position:fixed;left:max(14px,env(safe-area-inset-left));right:max(14px,env(safe-area-inset-right));bottom:max(14px,calc(env(safe-area-inset-bottom) + 10px));z-index:2147483000;max-width:560px;margin:0 auto;padding:16px;border-radius:22px;background:rgba(255,255,255,.97);border:1px solid rgba(104,71,245,.16);box-shadow:0 18px 60px rgba(38,27,72,.2);backdrop-filter:blur(18px);font-family:inherit;color:#211b2d}
      .adelia-notify-card h3{margin:0 0 6px;font-size:17px;line-height:1.2}.adelia-notify-card p{margin:0;color:#756e80;font-size:13px;line-height:1.45}.adelia-notify-actions{display:flex;gap:9px;margin-top:13px}.adelia-notify-actions button{min-height:42px;border-radius:13px;padding:0 14px;font:inherit;font-weight:800;cursor:pointer}.adelia-notify-enable{flex:1;border:0;background:#7048d8;color:#fff}.adelia-notify-later{border:1px solid #e7e1ef;background:#fff;color:#625a6c}.adelia-notify-note{display:block;margin-top:8px;color:#938b9d;font-size:11px;line-height:1.35}.adelia-notify-error{margin-top:9px;padding:9px 10px;border-radius:12px;background:#fff5f2;color:#8e3b24;font-size:12px;line-height:1.35}
      .adelia-push-action{position:fixed;right:max(14px,env(safe-area-inset-right));bottom:max(14px,calc(env(safe-area-inset-bottom) + 10px));z-index:2147482999;border:0;border-radius:16px;background:#211b2d;color:#fff;padding:12px 15px;font:inherit;font-size:13px;font-weight:800;box-shadow:0 14px 40px rgba(32,24,55,.24);cursor:pointer;max-width:min(330px,calc(100vw - 28px));text-align:left}.adelia-push-action small{display:block;margin-top:3px;color:#d8d1e4;font-weight:500;line-height:1.3}
      @media(max-width:520px){.adelia-notify-card{padding:15px}.adelia-notify-actions{flex-direction:column}.adelia-notify-actions button{width:100%}.adelia-push-action{left:14px;right:14px;width:auto}}
    `;document.head.appendChild(s);
  }
  function removeNotificationCard(){document.getElementById('adeliaNotificationCard')?.remove()}
  function removePushAction(){document.getElementById('adeliaPushAction')?.remove()}
  function dismissed(){try{return localStorage.getItem(DISMISSED_KEY)==='1'}catch(_){return false}}
  function markDismissed(){try{localStorage.setItem(DISMISSED_KEY,'1')}catch(_){}}
  function mountPushAction(note='Уведомления разрешены, но устройство ещё не зарегистрировано'){
    injectNotificationStyles();
    if(document.getElementById('adeliaPushAction'))return;
    const b=document.createElement('button');b.id='adeliaPushAction';b.type='button';b.className='adelia-push-action';b.innerHTML=`🔔 Подключить уведомления<small>${note}</small>`;
    b.onclick=async()=>{b.disabled=true;const old=b.innerHTML;b.textContent='Подключаю…';try{const result=await subscribeFromGesture();if(result.status==='subscribed')removePushAction()}catch(err){b.disabled=false;b.innerHTML=old;showPushRecoveryCard(err)}};
    document.body.appendChild(b);
  }
  function notificationCopy(){
    if(ios()&&!standalone())return {title:'Включить уведомления Аделии',text:'На iPhone уведомления доступны после установки Аделии на экран «Домой».',action:'Как установить',mode:'install',note:'После установки откройте Аделию с домашнего экрана — там появится системный запрос.'};
    return {title:'Не пропускайте занятия и оплату',text:'Разрешите Аделии присылать уведомления о занятиях, домашних заданиях и важных изменениях.',action:'Включить уведомления',mode:'permission',note:'Разрешение можно изменить позже в настройках устройства.'};
  }
  function renderNotificationCard(copy,{force=false,error=''}={}){
    removeNotificationCard();if(!force&&dismissed())return;injectNotificationStyles();
    const root=document.createElement('section');root.id='adeliaNotificationCard';root.className='adelia-notify-card';root.setAttribute('role','dialog');root.setAttribute('aria-label',copy.title);
    const safe=String(error||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    root.innerHTML=`<h3>🔔 ${copy.title}</h3><p>${copy.text}</p>${safe?`<div class="adelia-notify-error">${safe}</div>`:''}<div class="adelia-notify-actions"><button type="button" class="adelia-notify-enable">${copy.action}</button><button type="button" class="adelia-notify-later">Позже</button></div><small class="adelia-notify-note">${copy.note||''}</small>`;
    root.querySelector('.adelia-notify-later').onclick=()=>{markDismissed();removeNotificationCard()};
    root.querySelector('.adelia-notify-enable').onclick=async()=>{const btn=root.querySelector('.adelia-notify-enable');btn.disabled=true;const before=btn.textContent;btn.textContent='Подключаю…';try{if(copy.mode==='install'){const result=await window.AdeliaPWA.install();if(result?.message)alert(result.message);return}if(Notification.permission==='default'){const p=await Notification.requestPermission();if(p!=='granted'){if(p==='denied'){markDismissed();removeNotificationCard()}return}}const result=await subscribeFromGesture();if(result.status==='subscribed')removeNotificationCard()}catch(err){showPushRecoveryCard(err)}finally{if(document.body.contains(btn)){btn.disabled=false;btn.textContent=before}}};
    document.body.appendChild(root);
  }
  function showPushRecoveryCard(err){const msg=String(err&&err.message||err||'Не удалось зарегистрировать устройство для push-уведомлений.');renderNotificationCard({title:'Уведомления разрешены, но устройство ещё не подключено',text:'Нажмите кнопку ещё раз — iPhone требует явное действие пользователя для регистрации push.',action:'Подключить уведомления',mode:'retry',note:'Разрешение iOS уже сохранено; повторно подтверждать его не нужно.'},{force:true,error:msg})}
  async function requestNotifications(){
    if(ios()&&!standalone())return {status:'install_required'};
    if(!notificationSupported())return {status:'unsupported'};
    try{
      let result=Notification.permission;
      if(result==='default')result=await Notification.requestPermission();
      if(result==='granted')return subscribeFromGesture();
      if(result==='denied'){markDismissed();removeNotificationCard();removePushAction()}
      return {status:result};
    }catch(err){showPushRecoveryCard(err);return {status:'error',error:String(err&&err.message||err)}}
  }
  function showNotificationCard(force=false){
    if(document.getElementById('adeliaNotificationCard'))return;
    if(!force&&dismissed())return;
    if(!notificationSupported()&&!(ios()&&!standalone()))return;
    if(notificationSupported()&&Notification.permission==='granted'){syncExistingSubscription().then(result=>{if(result.status==='user_gesture_required')mountPushAction();}).catch(showPushRecoveryCard);return}
    if(notificationSupported()&&Notification.permission==='denied')return;
    renderNotificationCard(notificationCopy(),{force});
  }

  window.AdeliaPWA={isStandalone:standalone,isIOS:ios,canInstall:()=>!!deferredPrompt||(!standalone()&&ios()),notificationPermission:permission,requestNotifications,syncPushSubscription,subscribeFromGesture,testPush,showNotificationPrompt:()=>showNotificationCard(true),async install(){if(standalone())return {status:'installed'};if(!deferredPrompt){if(ios())return {status:'manual',message:'В Safari нажмите «Поделиться», затем «На экран Домой».'};return {status:'unavailable'}}const prompt=deferredPrompt;deferredPrompt=null;await prompt.prompt();const choice=await prompt.userChoice.catch(()=>null);window.dispatchEvent(new CustomEvent('adelia:pwa-state'));return {status:choice?.outcome||'dismissed'}}};
  document.addEventListener('click',e=>{const trigger=e.target.closest('[data-notifications-adelia]');if(!trigger)return;e.preventDefault();requestNotifications()},true);
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferredPrompt=event;window.dispatchEvent(new CustomEvent('adelia:pwa-state'))});
  window.addEventListener('appinstalled',()=>{deferredPrompt=null;window.dispatchEvent(new CustomEvent('adelia:pwa-state'))});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&Notification.permission==='granted')syncExistingSubscription().then(r=>{if(r.status==='user_gesture_required')mountPushAction()}).catch(showPushRecoveryCard)});
  window.addEventListener('focus',()=>{if(Notification.permission==='granted')syncExistingSubscription().then(r=>{if(r.status==='user_gesture_required')mountPushAction()}).catch(showPushRecoveryCard)});
  if('serviceWorker' in navigator){window.addEventListener('load',()=>{navigator.serviceWorker.register('/app/service-worker.js',{scope:'/app/'}).then(async reg=>{if(reg.waiting)reg.waiting.postMessage({type:'SKIP_WAITING'});if(Notification.permission==='granted'){try{const result=await syncExistingSubscription();if(result.status==='user_gesture_required')mountPushAction()}catch(err){showPushRecoveryCard(err)}}}).catch(err=>{console.warn('PWA service worker:',err);if(Notification.permission==='granted')showPushRecoveryCard(err)})});navigator.serviceWorker.addEventListener('controllerchange',()=>window.dispatchEvent(new CustomEvent('adelia:pwa-state')))}
  window.addEventListener('load',()=>setTimeout(()=>showNotificationCard(false),1600));
})();
