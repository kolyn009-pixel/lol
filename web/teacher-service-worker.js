const CACHE='adelia-teacher-shell-v2';
const ICON='/adelia-apple-touch-icon-180.png';
const BADGE='/adelia-favicon-32.png';
const TYPE_META={
 invoice:{emoji:'💳',title:'Счёт отправлен'},
 payment:{emoji:'💰',title:'Поступила оплата'},
 receipt:{emoji:'🧾',title:'Новый чек'},
 lesson:{emoji:'🎓',title:'Занятие'},
 lesson_start:{emoji:'🎥',title:'Занятие начинается'},
 telemost:{emoji:'🎥',title:'Телемост готов'},
 schedule:{emoji:'🗓️',title:'Изменение расписания'},
 homework:{emoji:'📚',title:'Домашнее задание'},
 homework_review:{emoji:'✍️',title:'Работа ученика'},
 message:{emoji:'💬',title:'Новое сообщение'},
 reminder:{emoji:'⏰',title:'Напоминание'},
 test:{emoji:'💜',title:'Аделия работает'}
};
function notificationView(payload){
  const data=payload&&typeof payload.data==='object'&&payload.data?payload.data:{};
  const type=String(data.type||'').toLowerCase();
  const meta=TYPE_META[type];
  let title=String(payload?.title||meta?.title||'Аделия').trim();
  if(meta&&!/^[\p{Extended_Pictographic}]/u.test(title))title=`${meta.emoji} ${title}`;
  if(!meta&&title==='Аделия')title='💜 Аделия';
  return {title,body:String(payload?.body||''),url:String(payload?.url||'/teacher/'),tag:String(payload?.tag||`adelia-teacher-${type||'notice'}`),data};
}
self.addEventListener('install',event=>{event.waitUntil(self.skipWaiting())});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('adelia-teacher-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()))});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting()});
self.addEventListener('push',event=>{
  let payload={};try{payload=event.data?.json()||{}}catch(_){try{payload={body:event.data?.text()||''}}catch(__){}}
  const view=notificationView(payload);
  const options={body:view.body,icon:ICON,badge:BADGE,tag:view.tag,renotify:true,silent:false,timestamp:Date.now(),data:{url:view.url,...view.data}};
  event.waitUntil(self.registration.showNotification(view.title,options));
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();const raw=event.notification?.data?.url||'/teacher/';let target;
  try{const u=new URL(raw,self.location.origin);target=u.origin===self.location.origin?u.href:new URL('/teacher/',self.location.origin).href}catch(_){target=new URL('/teacher/',self.location.origin).href}
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{for(const client of list){try{const u=new URL(client.url);if(u.origin===self.location.origin&&u.pathname.startsWith('/teacher/')){if('navigate' in client)client.navigate(target);return client.focus()}}catch(_){}}return clients.openWindow?clients.openWindow(target):undefined}));
});
