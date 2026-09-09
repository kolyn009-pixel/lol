const CACHE='adelia-shell-v6';
const SHELL=[
  '/app/',
  '/app/styles.css',
  '/app/student_homework_plus.css',
  '/app/formulas.css',
  '/app/stage11_mobile.css',
  '/app/pwa.js',
  '/app/app_shell_plus.js',
  '/app/manifest.webmanifest',
  '/app/lesson/'
];
const OPTIONAL=[
  '/app/app.js',
  '/app/student_homework_plus.js',
  '/app/student_formulas.js',
  '/app/lesson/lesson.js',
  '/app/lesson/lesson.css'
];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(async cache=>{
    await cache.addAll(SHELL);
    await Promise.allSettled(OPTIONAL.map(url=>cache.add(url)));
  }).then(()=>self.skipWaiting()));
});

self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));
});

self.addEventListener('message',event=>{
  if(event.data?.type==='SKIP_WAITING')self.skipWaiting();
});

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;

  if(request.mode==='navigate'&&url.pathname.startsWith('/app/')){
    const fallback=url.pathname.startsWith('/app/lesson/')?'/app/lesson/':'/app/';
    event.respondWith(fetch(request).catch(()=>caches.match(fallback)));
    return;
  }

  event.respondWith(caches.match(request).then(cached=>{
    const network=fetch(request).then(response=>{
      if(response&&response.ok){
        const copy=response.clone();
        caches.open(CACHE).then(cache=>cache.put(request,copy));
      }
      return response;
    }).catch(()=>cached||Response.error());
    return cached||network;
  }));
});
