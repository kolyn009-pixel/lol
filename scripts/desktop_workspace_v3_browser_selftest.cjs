'use strict';
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),manifest=require('../desktop/bundled_ui_manifest');
const launch={headless:true,executablePath:process.env.ADELIA_CHROMIUM||undefined,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-zygote','--single-process']};
(async()=>{const browser=await chromium.launch(launch);try{
 const page=await browser.newPage();let role='teacher',readPosts=0;const posts=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 let html=fs.readFileSync(path.join(root,'web/teacher.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');
 html=html.replace('</head>',manifest.teacher.css.map(n=>'<link rel="stylesheet" href="/app/'+n+'">').join('')+'</head>');
 const dashboard={stats:{today_total:3,today_remaining:2,active_students:18,unpaid_amount:10900},week:{planned:10,remaining:6,cancelled:4},today_lessons:[{id:1,name:'Кирилл',user_id:20,start_time:'2026-10-22T16:00:00',start_at:'2026-10-22T13:00:00Z',subject:'PHYSICS',payment_status:'PAID',lesson_status:'CONFIRMED',meeting_url:'https://telemost.yandex.ru/j/123',board_url:'https://myboard.io/board/123'},{id:2,name:'Тимур',user_id:21,start_time:'2026-10-22T19:00:00',subject:'PHYSICS',payment_status:'AWAITING_PAYMENT',lesson_status:'CONFIRMED'}],next_lessons:[{id:1,name:'Кирилл',start_time:'2026-10-22T16:00:00',subject:'PHYSICS',payment_status:'PAID',lesson_status:'CONFIRMED'}],week_lessons:[],pending_reviews:[]};
 const conv={id:10,student_id:20,participant_type:'STUDENT',name:'Кирилл',last_body:'Здравствуйте!',channels:{},unread:1};
 await page.route('https://qa.adelia/**',async route=>{const req=route.request(),u=new URL(req.url()),p=u.pathname;const json=d=>route.fulfill({json:d});
 if(p==='/app/teacher.html')return route.fulfill({body:html,contentType:'text/html'});
 if(p==='/api/auth/me')return json({authenticated:true,session:{role}});
 if(p==='/api/teacher/dashboard')return json(dashboard);
 if(p==='/api/teacher/messages')return json({items:[conv]});
 if(p==='/api/teacher/messages/history')return json({items:[{id:1,direction:'IN',body:'Здравствуйте! Когда следующее занятие?',created_at:'2026-10-22T13:00:00Z',origin_channel:'WEB',read_at:null}]});
 if(p==='/api/teacher/messages/read'){readPosts++;return json({read_at:'2026-10-22T13:01:00Z'})}
 if(req.method()==='POST'){posts.push({path:p,body:req.postDataJSON()});return json({ok:true,id:2})}
 if(p==='/api/student/dashboard')return json({student:{timezone:{zone:'Europe/Moscow',label:'Москва'}}});
 if(p==='/api/student/messages')return json({items:[{id:1,direction:'OUT',text:'Здравствуйте, Кирилл!',created_at:'2026-10-22T13:00:00Z'}]});
 if(p.startsWith('/app/')){const f=path.join(root,'web',p.slice(5));if(fs.existsSync(f)&&fs.statSync(f).isFile())return route.fulfill({path:f});return route.fulfill({body:'',contentType:p.endsWith('.css')?'text/css':'text/javascript'})}
 return json({items:[]});});
 for(const width of [900,1024,1280,1440,1920]){
  await page.setViewportSize({width,height:1000});await page.goto('https://qa.adelia/app/teacher.html'+(process.env.ADELIA_QA_WEB?'?web=1':''));await page.evaluate(()=>{if(!location.search.includes('web=1'))document.documentElement.classList.add('adelia-desktop','adelia-desktop-teacher');window.adeliaDesktop={desktop:true,openLessonTool:async(kind,url)=>{window.lastTool=[kind,url];return true}};if(location.search.includes('web=1'))delete window.adeliaDesktop;window.TeacherTime={ready:async()=>{},preference:{zone:'Europe/Moscow'},lesson:x=>x.start_time.slice(11,16),label:()=> 'Москва'};});
  for(const name of ['teacher_studio.js','teacher_dashboard_week.js','desktop_workspace_v3.js'])await page.addScriptTag({path:path.join(root,'web',name)});
  await page.waitForSelector('.dashboard-lesson-card');assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'page overflow '+width);
  assert.equal(await page.locator('.dashboard-subject').first().textContent(),'Физика');
  for(const box of await page.locator('.dashboard-lesson-actions button').evaluateAll(bs=>bs.map(b=>{const p=b.closest('.dashboard-lesson-card').getBoundingClientRect(),r=b.getBoundingClientRect();return{right:r.right,left:r.left,parentRight:p.right,parentLeft:p.left}})))assert(box.right<=box.parentRight+1&&box.left>=box.parentLeft-1,'actions escaped '+width);
  assert((await page.locator('.dashboard-lesson-main>b').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)))>=16);
  if(width===1440&&process.env.ADELIA_QA_SCREENSHOTS)await page.screenshot({path:'/tmp/adelia-workspace-v3-1440.png',fullPage:true});
  console.log('DESKTOP_LAYOUT_'+width+'=OK');
 }
 if(!process.env.ADELIA_QA_WEB){await page.getByRole('button',{name:'Яндекс Телемост',exact:true}).click();assert.deepEqual(await page.evaluate(()=>window.lastTool),['meeting','https://telemost.yandex.ru/']);}
 await page.locator('.v3-chat-launcher').click();const chat=page.frameLocator('iframe[title="Переписка в Аделии"]');await chat.locator('[data-conv="10"]').click();await chat.locator('#msgText').fill('Проверка панели');await chat.locator('button[type="submit"]').click();await page.waitForTimeout(600);assert(posts.some(x=>x.path==='/api/teacher/messages/send'&&x.body.text==='Проверка панели'),JSON.stringify(posts));
 await chat.locator('#msgText').fill('Мой черновик');await page.locator('[data-chat-close]').click();const count=readPosts;await page.locator('.v3-chat-launcher').click();await chat.locator('#msgText').waitFor();assert.equal(await chat.locator('#msgText').inputValue(),'Мой черновик');await page.waitForFunction(()=>{const d=document.querySelector('iframe[title="Переписка в Аделии"]')?.contentDocument,e=d?.querySelector('.msg-thread-actions');return !!e&&d.defaultView.getComputedStyle(e).display==='none'});if(process.env.ADELIA_QA_SCREENSHOTS)await page.screenshot({path:'/tmp/adelia-workspace-v3-chat.png'});console.log('TEACHER_CHAT_SEND_DRAFT_CLOSE_REOPEN=OK',count);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.querySelector('.v3-chat-panel').getBoundingClientRect().width<=innerWidth));await chat.locator('#msgText').waitFor();assert(await chat.locator('.msg-shell').evaluate(e=>document.documentElement.scrollWidth<=innerWidth+1));await chat.locator('#msgBack').click();await chat.locator('[data-conv="10"]').waitFor({state:'visible'});await chat.locator('[data-conv="10"]').click();await chat.locator('#msgText').waitFor({state:'visible'});console.log('MOBILE_RIGHT_CHAT_BACK_AND_OPEN=OK');
 role='student';await page.goto('https://qa.adelia/app/quick_chat.html');await page.locator('#studentChatText').fill('Спасибо!');await page.locator('#studentChatForm button[type="submit"]').click();await page.waitForTimeout(600);assert(posts.some(x=>x.path==='/api/student/message'&&x.body.text==='Спасибо!'));assert.deepEqual(errors,[]);console.log('STUDENT_CHAT_SEND=OK');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
