const CACHE='adelia-shell-v18';
const NETWORK_LIMIT_MS=4500;
const boundedFetch=request=>Promise.race([fetch(request),new Promise((_,reject)=>setTimeout(()=>reject(new Error('network_timeout')),NETWORK_LIMIT_MS))]);
const SHELL=[
 '/app/','/app/manifest.webmanifest','/app/assets/icons/adelia-icon-32.png?v=20260925-brand4','/app/assets/icons/adelia-icon-180.png?v=20260925-brand4','/app/assets/icons/adelia-icon-192.png?v=20260925-brand4','/app/assets/icons/adelia-icon-512.png?v=20260925-brand4',
 '/app/student_clean.css','/app/student_time.css','/app/pwa_connection_status.css','/app/student_chat.css','/app/student_next_step.css','/app/student_homework_plus.css','/app/formulas.css','/app/student_booking_ui.css','/app/group_events_ui.css','/app/desktop_payment.css',
 '/app/pwa.js','/app/install_runtime.js','/app/student_time.js','/app/pwa_connection_status.js','/app/app.js','/app/auth_flow_v2.js','/app/app_shell_plus.js','/app/student_boot.js','/app/student_booking_ui.js','/app/group_events_ui.js','/app/desktop_payment.js',
 '/app/student_messenger_v2.js','/app/student_next_step.js','/app/student_stage1_home.js','/app/student_stage2_lessons.js','/app/student_stage3_learning.js','/app/student_stage4_workspace.js','/app/student_formulas.js'
];
const ICON='/app/assets/icons/adelia-icon-180.png?v=20260925-brand4';
const BADGE='/app/assets/icons/adelia-icon-32.png?v=20260925-brand4';
const TYPE_META={
 invoice:{emoji:'💳',title:'Новый счёт'},
 payment:{emoji:'✅',title:'Оплата подтверждена'},
 receipt:{emoji:'🧾',title:'Чек обработан'},
 lesson:{emoji:'🎓',title:'Занятие'},
 lesson_start:{emoji:'🎥',title:'Занятие начинается'},
 telemost:{emoji:'🎥',title:'Ссылка на занятие'},
 schedule:{emoji:'🗓️',title:'Расписание изменилось'},
 homework:{emoji:'📚',title:'Домашнее задание'},
 homework_review:{emoji:'✍️',title:'Работа проверена'},
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
 const financial=['invoice','payment','payment_review','receipt'].includes(type);if(financial)title='💳 Оплата в Аделии';
 return {title,body:financial?'Детали доступны после входа в приложение.':String(payload?.body||''),url:String(payload?.url||'/app/'),tag:String(payload?.tag||`adelia-${type||'notice'}`),data};
}
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>Promise.allSettled(SHELL.map(url=>cache.add(url)))).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('adelia-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()))});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting()});
self.addEventListener('push',event=>{
 let payload={};try{payload=event.data?.json()||{}}catch(_){try{payload={body:event.data?.text()||''}}catch(__){}}
 const view=notificationView(payload);
 const options={body:view.body,icon:ICON,badge:BADGE,tag:view.tag,renotify:false,silent:false,timestamp:Date.now(),data:{url:view.url,...view.data}};
 event.waitUntil(self.registration.showNotification(view.title,options));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();const raw=event.notification?.data?.url||'/app/';let target;
 try{const u=new URL(raw,self.location.origin);target=u.origin===self.location.origin?u.href:new URL('/app/',self.location.origin).href}catch(_){target=new URL('/app/',self.location.origin).href}
 event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{for(const client of list){try{const u=new URL(client.url);if(u.origin===self.location.origin&&u.pathname.startsWith('/app/')){if('navigate' in client)client.navigate(target);return client.focus()}}catch(_){}}return clients.openWindow?clients.openWindow(target):undefined}));
});
self.addEventListener('fetch',event=>{
 const request=event.request;if(request.method!=='GET')return;
 const url=new URL(request.url);if(url.origin!==self.location.origin||url.pathname.startsWith('/api/')||url.pathname==='/app/teacher.html')return;
 if(request.mode==='navigate'&&url.pathname.startsWith('/app/')){event.respondWith(boundedFetch(request).then(response=>{if(response.ok&&url.pathname==='/app/')caches.open(CACHE).then(c=>c.put('/app/',response.clone()));return response}).catch(async()=>url.pathname==='/app/'?(await caches.match('/app/'))||new Response('Нет сети. Повторите попытку позже.',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}}):new Response('<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Аделия · нет сети</title><main style="font:16px system-ui;padding:24px"><h1>Нет соединения</h1><p>Для открытия этого раздела нужна сеть. Уже открытая главная страница доступна без сети, но данные требуют подключения.</p><a href="/app/">На главную</a></main></html>',{status:503,headers:{'Content-Type':'text/html; charset=utf-8'}})));return}
 const code=/\.(?:js|css|svg|png)$/.test(url.pathname)||url.pathname.endsWith('/manifest.webmanifest');
 if(code){event.respondWith(boundedFetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put(request,response.clone()));return response}).catch(()=>caches.match(request)));return}
 event.respondWith(caches.match(request).then(cached=>cached||boundedFetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(c=>c.put(request,response.clone()));return response})))
});
