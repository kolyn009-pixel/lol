const CACHE='adelia-shell-v10';
const SHELL=[
 '/app/','/app/manifest.webmanifest','/app/assets/icons/adelia-icon.svg',
 '/app/styles.css','/app/stage11_mobile.css','/app/responsive_shell.css','/app/selects.css',
 '/app/student_chat.css','/app/student_homework_plus.css','/app/formulas.css','/app/student_booking_ui.css',
 '/app/pwa.js','/app/app.js','/app/auth_flow_v2.js','/app/app_shell_plus.js','/app/responsive_shell.js','/app/student_boot.js','/app/student_booking_ui.js'
];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>Promise.allSettled(SHELL.map(url=>cache.add(url)))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()))});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting()});
self.addEventListener('push',event=>{
 let payload={};try{payload=event.data?.json()||{}}catch(_){try{payload={body:event.data?.text()||''}}catch(__){}}
 const title=payload.title||'Аделия';const target=payload.url||'/app/';
 const options={body:payload.body||'',icon:'/app/assets/icons/adelia-icon-192.png',badge:'/app/assets/icons/adelia-icon-192.png',tag:payload.tag||'adelia',data:{url:target,...(payload.data||{})}};
 event.waitUntil(self.registration.showNotification(title,options));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();const raw=event.notification?.data?.url||'/app/';let target;
 try{const u=new URL(raw,self.location.origin);target=u.origin===self.location.origin?u.href:new URL('/app/',self.location.origin).href}catch(_){target=new URL('/app/',self.location.origin).href}
 event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{for(const client of list){try{if(new URL(client.url).origin===self.location.origin){if('navigate' in client)client.navigate(target);return client.focus()}}catch(_){}}return clients.openWindow?clients.openWindow(target):undefined}));
});
self.addEventListener('fetch',event=>{
 const request=event.request;if(request.method!=='GET')return;
 const url=new URL(request.url);if(url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
 if(request.mode==='navigate'&&url.pathname.startsWith('/app/')){event.respondWith(fetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put('/app/',response.clone()));return response}).catch(()=>caches.match('/app/')));return}
 const code=/\.(?:js|css|svg)$/.test(url.pathname)||url.pathname.endsWith('/manifest.webmanifest');
 if(code){event.respondWith(fetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put(request,response.clone()));return response}).catch(()=>caches.match(request)));return}
 event.respondWith(caches.match(request).then(cached=>cached||fetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put(request,response.clone()));return response})))
});
