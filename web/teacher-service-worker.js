const CACHE='adelia-teacher-shell-v1';
self.addEventListener('install',event=>{event.waitUntil(self.skipWaiting())});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('adelia-teacher-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()))});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting()});
self.addEventListener('push',event=>{
  let payload={};
  try{payload=event.data?.json()||{}}catch(_){try{payload={body:event.data?.text()||''}}catch(__){}}
  const title=payload.title||'Аделия';
  const target=payload.url||'/teacher/';
  const options={
    body:payload.body||'',
    icon:'/adelia-apple-touch-icon-180.png',
    badge:'/adelia-favicon-32.png',
    tag:payload.tag||'adelia-teacher',
    data:{url:target,...(payload.data||{})}
  };
  event.waitUntil(self.registration.showNotification(title,options));
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const raw=event.notification?.data?.url||'/teacher/';
  let target;
  try{const u=new URL(raw,self.location.origin);target=u.origin===self.location.origin?u.href:new URL('/teacher/',self.location.origin).href}catch(_){target=new URL('/teacher/',self.location.origin).href}
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{
    for(const client of list){
      try{if(new URL(client.url).origin===self.location.origin&&new URL(client.url).pathname.startsWith('/teacher/')){if('navigate' in client)client.navigate(target);return client.focus()}}catch(_){}
    }
    return clients.openWindow?clients.openWindow(target):undefined;
  }));
});
