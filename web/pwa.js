(function(){
  if(!('serviceWorker' in navigator)) return;
  window.addEventListener('load',()=>{
    navigator.serviceWorker.register('/app/service-worker.js',{scope:'/app/'}).catch(err=>console.warn('PWA service worker:',err));
  });
})();
