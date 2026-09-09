(function(){
  let deferredPrompt=null;
  const standalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  const ios=()=>/iphone|ipad|ipod/i.test(navigator.userAgent)&&!window.MSStream;
  window.AdeliaPWA={
    isStandalone:standalone,
    isIOS:ios,
    canInstall:()=>!!deferredPrompt||(!standalone()&&ios()),
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
})();
