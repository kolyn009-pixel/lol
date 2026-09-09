const CACHE='adelia-shell-v2';
const SHELL=['/app/','/app/styles.css','/app/app.js','/app/pwa.js','/app/manifest.webmanifest'];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});

self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));
});

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET') return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin || url.pathname.startsWith('/api/')) return;

  event.respondWith(
    fetch(request).then(response=>{
      if(response && response.ok){
        const copy=response.clone();
        caches.open(CACHE).then(cache=>cache.put(request,copy));
      }
      return response;
    }).catch(async()=>{
      const cached=await caches.match(request);
      if(cached) return cached;
      if(request.mode==='navigate' && url.pathname.startsWith('/app/')) return caches.match('/app/');
      return Response.error();
    })
  );
});
