const CACHE='adelia-shell-v7';
const SHELL=['/app/','/app/styles.css','/app/pwa.js','/app/app.js','/app/auth_flow_v2.js','/app/app_shell_plus.js','/app/manifest.webmanifest'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>Promise.allSettled(SHELL.map(url=>cache.add(url)))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()))});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting()});
self.addEventListener('fetch',event=>{
 const request=event.request;if(request.method!=='GET')return;
 const url=new URL(request.url);if(url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
 if(request.mode==='navigate'&&url.pathname.startsWith('/app/')){const fallback=url.pathname.startsWith('/app/lesson/')?'/app/lesson/':'/app/';event.respondWith(fetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put(fallback,response.clone()));return response}).catch(()=>caches.match(fallback)));return}
 const isCode=/\.(?:js|css)$/.test(url.pathname)||url.pathname.endsWith('/manifest.webmanifest');
 if(isCode){event.respondWith(fetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put(request,response.clone()));return response}).catch(()=>caches.match(request)));return}
 event.respondWith(caches.match(request).then(cached=>cached||fetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put(request,response.clone()));return response})))
});
