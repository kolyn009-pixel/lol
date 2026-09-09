(function(){
  let deferredPrompt=null;
  const standalone=()=>window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;
  window.AdeliaPWA={
    isStandalone:standalone,
    canInstall:()=>!!deferredPrompt,
    async install(){
      if(!deferredPrompt)return {status:standalone()?'installed':'unavailable'};
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
