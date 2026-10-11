'use strict';
/* Real Chromium layout/interaction checks with synthetic users and API data. */
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..','web');
const fixtures={
 student:{css:['student_clean.css','student_chat.css'],js:['student_messenger_v2.js'],body:'<div class="app-shell"><header class="topbar"><div class="eyebrow">Аделия · ученик</div><button id="roleButton">У</button></header><main id="content" class="content"></main><nav class="bottom-nav"><button class="nav-item" data-tab="messages"><span></span><small>Чат</small></button></nav></div>'},
 teacher:{css:['teacher_clean.css','teacher_groups_polish.css'],js:['teacher_groups.js'],body:'<div class="teacher-shell"><main><header><h1 id="title">Группы</h1><div class="header-actions"></div></header><div id="app"></div></main></div>'},
 parent:{css:['parent/parent_clean.css','parent/messenger.css'],js:['parent/messenger.js'],body:'<div id="root"><header><h1>Родительский кабинет</h1></header></div>'}
};
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,'http://localhost');
 if(u.pathname.startsWith('/fixture/')){const role=u.pathname.split('/').at(-1),f=fixtures[role];if(!f){res.writeHead(404);return res.end()}res.setHeader('Content-Type','text/html; charset=utf-8');return res.end('<!doctype html><html lang="ru"><head><meta name="viewport" content="width=device-width,initial-scale=1">'+[...f.css,'interface_unified.css'].map(x=>'<link rel="stylesheet" href="/app/'+x+'">').join('')+'</head><body>'+f.body+'<script>window.StudentTime={preference:{zone:"Europe/Samara"},load:async()=>{}};window.TeacherTime={preference:{zone:"Europe/Moscow"}};</script>'+['adelia_icons.js','appearance.js','group_chat.js',...f.js].map(x=>'<script src="/app/'+x+'"></script>').join('')+'</body></html>')}
 const file=path.resolve(root,u.pathname.replace(/^\/app\//,''));if(!file.startsWith(root+path.sep)){res.writeHead(403);return res.end()}
 try{const content=fs.readFileSync(file);res.setHeader('Content-Type',file.endsWith('.css')?'text/css':file.endsWith('.js')?'application/javascript':file.endsWith('.svg')?'image/svg+xml':file.endsWith('.png')?'image/png':'text/plain');res.end(content)}catch{res.writeHead(404);res.end()}
});
async function scenario(browser,size){
 const context=await browser.newContext({viewport:size,isMobile:size.width<700,hasTouch:size.width<700});const page=await context.newPage(),errors=[],posts=[];let role='student',failSend=false;
 const groupItems=[{id:1,sender_role:'TEACHER',body:'Добро пожаловать',created_at:'2026-10-11T12:00:00Z'}];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',async route=>{const req=route.request(),u=new URL(req.url());let data={};
  if(u.pathname==='/api/profile/appearance'){data={role,owner_id:1,preset:'student_avatar_01',url:'/app/assets/avatars/student_avatar_01.svg',custom:false};if(req.method()==='POST'){const preset=req.postDataJSON().preset;data={...data,preset,url:'/app/assets/avatars/'+preset+'.svg'}}}
  else if(u.pathname==='/api/profile/avatar')data={role,owner_id:1,url:'/app/assets/avatars/student_avatar_02.svg',custom:true};
  else if(u.pathname.endsWith('/group/chat')){if(req.method()==='POST'){const body=req.postDataJSON();posts.push(body);if(failSend)return route.fulfill({status:503,json:{error:'retry_later'}});groupItems.push({id:groupItems.length+1,sender_role:role.toUpperCase(),sender_name:'Тестовый ученик',body:body.body,mine:true,created_at:'2026-10-11T13:00:00Z'});data={message_id:groupItems.length}}else data={group:{id:1,name:'Тестовая группа',chat_mode:'OPEN'},items:groupItems}}
  else if(u.pathname==='/api/teacher/groups')data={items:[{id:1,name:'Тестовая группа',subject:'Физика',chat_mode:'OPEN'}]};
  else if(u.pathname==='/api/parent/messages/students')data={items:[{id:1,name:'Первый ребёнок'},{id:2,name:'Второй ребёнок'}]};
  else if(u.pathname==='/api/parent/messages')data={items:[{id:1,direction:'OUT',body:'Фото задания',created_at:'2026-10-11T12:00:00Z',attachment:{kind:'photo',name:'Задание',url:'/app/assets/avatars/student_avatar_03.svg'}}]};
  else if(u.pathname==='/api/student/messages')data={items:[{id:1,direction:'OUT',text:'Здравствуйте',created_at:'2026-10-11T12:00:00Z'}]};
  else if(u.pathname==='/api/student/dashboard')data={unread_messages:0};
  await route.fulfill({json:data});
 });
 const origin='http://127.0.0.1:'+server.address().port;
 await page.goto(origin+'/fixture/student');await page.evaluate(async()=>{document.querySelector('#content').innerHTML=await AdeliaStudentMessenger.screen();AdeliaStudentMessenger.mount()});
 await page.locator('#studentChatText').fill('Черновик');await page.evaluate(()=>AdeliaStudentMessenger.refresh(true));await page.waitForTimeout(100);
 assert.equal(await page.locator('#studentChatText').inputValue(),'Черновик');assert.equal(await page.locator('.student-helper').getAttribute('open'),null);
 const composer=await page.locator('#studentChatForm').boundingBox();assert(composer.height>=44&&composer.y+composer.height<=size.height,'student composer must fit viewport');
 await page.evaluate(()=>AdeliaAppearance.edit());await page.locator('#adeliaAvatarEditor').waitFor();assert.equal(await page.locator('[data-preset]').count(),10);
 await page.locator('[data-preset="student_avatar_05"]').click();await page.locator('[data-save]').click();await page.locator('#adeliaAvatarEditor').waitFor({state:'detached'});
 await page.evaluate(()=>{AdeliaStudentMessenger.stop();document.querySelector('#content').innerHTML='<div id="testGroup"></div>';AdeliaGroupChat.mount(document.querySelector('#testGroup'),{groupId:1})});
 const textarea=page.locator('#testGroup textarea');await textarea.fill('Сообщение группе');await textarea.evaluate(el=>el.dataset.sameComposer='yes');failSend=true;await page.locator('#testGroup button[type=submit]').click();await page.locator('#testGroup [role=status]').filter({hasText:'Не отправлено'}).waitFor();assert.equal(await textarea.inputValue(),'Сообщение группе');
 failSend=false;await page.locator('#testGroup button[type=submit]').click();await page.locator('#testGroup [role=status]').filter({hasText:'Отправлено'}).waitFor();assert.equal(await textarea.inputValue(),'');assert.equal(await textarea.getAttribute('data-same-composer'),'yes');assert.equal(posts[0].client_token,posts[1].client_token,'retry uses same idempotency key');
 await page.evaluate(()=>AdeliaGroupChat.mount(document.querySelector('#testGroup'),{groupId:2,group:{chat_mode:'ANNOUNCEMENTS'}}));assert.equal(await page.locator('#testGroup textarea').isDisabled(),true);
 role='parent';await page.goto(origin+'/fixture/parent');await page.locator('#parentMessagesOpen').click();await page.locator('.pm-media img').waitFor();await page.locator('#pmText').fill('Первый черновик');await page.locator('#pmStudent').selectOption('2');assert.equal(await page.locator('#pmText').inputValue(),'');await page.locator('#pmText').fill('Второй черновик');await page.locator('#pmStudent').selectOption('1');assert.equal(await page.locator('#pmText').inputValue(),'Первый черновик');await page.keyboard.press('Escape');assert.equal(await page.locator('#parentMessenger').count(),0);
 role='teacher';await page.goto(origin+'/fixture/teacher');await page.evaluate(()=>teacherGroups());await page.locator('[data-group-chat]').click();await page.locator('.adelia-group-compose textarea').waitFor();await page.locator('.adelia-group-compose textarea').fill('Объявление преподавателя');await page.locator('.adelia-group-compose button').click();await page.locator('.adelia-group-status').filter({hasText:'Отправлено'}).waitFor();
 assert.deepEqual(errors,[]);console.log('INTERFACE_BROWSER='+size.width+'x'+size.height+' PASS');await context.close();
}
(async()=>{await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;try{browser=await chromium.launch();for(const size of [{width:390,height:844},{width:1440,height:900}])await scenario(browser,size)}finally{await browser?.close();server.close()}})().catch(e=>{console.error(e);process.exitCode=1});
