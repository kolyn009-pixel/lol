const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.ADELIA_CHROMIUM_EXECUTABLE?{executablePath:process.env.ADELIA_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--no-zygote','--single-process']}:{})});try{const page=await browser.newPage();page.on('pageerror',e=>console.error('PAGE_ERROR',e.message));
for(const width of [1440,390]){
 await page.unroute('https://qa.adelia/**');await page.setViewportSize({width,height:950});let saved=false,moved=false,submitted,previews=0;
 const item={id:1,kind:'LESSON',lesson_id:37,student_name:'Кирилл',status:'WAITING',original_start:'2026-11-03T18:30:00',original_at:'2026-11-03T18:30:00+03:00',current_start:'2026-11-03T18:30:00',timezone:'Europe/Moscow',viewer_timezone:'Europe/Moscow',public_reason:'Мне необходимо перенести наше занятие.',private_reason:'Моя личная причина'};
 const templates=[{id:'NEUTRAL',label:'Без объяснения причины',text:'Мне необходимо перенести наше занятие.'},{id:'HEALTH',label:'Здоровье',text:'По состоянию здоровья не смогу провести занятие.'},{id:'CUSTOM',label:'Своя причина',text:''}];
 await page.route('https://qa.adelia/**',async route=>{const u=new URL(route.request().url()),p=u.pathname;
  if(p==='/api/teacher/working-hours')return route.fulfill({json:{timezone:'Europe/Moscow',mode:'SAME',items:[],warnings:[],exceptions:saved?[{id:1,date:'2026-11-03',exception_type:'CLOSED'}]:[],timezone_change:{pending:false}}});
  if(p.endsWith('/day-off/invitations'))return route.fulfill({json:{items:saved&&!moved?[{...item,viewer_timezone:p.includes('/teacher/')?'Europe/Moscow':'Europe/Samara'}]:[],templates,today:'2026-11-01',timezone:'Europe/Moscow',deliveries:{PENDING:3}}});
  if(p.endsWith('/day-off/preview')){submitted=route.request().postDataJSON();previews++;return route.fulfill({json:{preview_token:'preview-'+previews,affected_count:1,affected_lessons:[{...item,start_time:item.original_start}],messages:[{role:'student',name:'Кирилл',timezone:'Europe/Samara',body:'Нейтральное сообщение о переносе.'}],timezone:'Europe/Moscow'}})}
  if(p.endsWith('/day-off/save')){assert.equal(route.request().postDataJSON().preview_token,'preview-'+previews);saved=true;return route.fulfill({json:{status:'ok',affected_count:1}})}
  if(p.endsWith('/day-off/slots'))return route.fulfill({json:{timezone:'Europe/Moscow',items:[{date:'2026-11-04',slots:[{start_time:'2026-11-04T15:45:00',start_at:'2026-11-04T15:45:00+03:00',end_time:'2026-11-04T16:45:00'}]}]}});
  if(p.endsWith('/day-off/reschedule')){const d=route.request().postDataJSON();assert.equal(d.start_time,'2026-11-04T15:45:00');moved=true;return route.fulfill({json:{status:'ok',payment_preserved:true}})}
  if(p==='/app/teacher.html')return route.fulfill({body:fs.readFileSync(path.join(root,'web/teacher.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''),contentType:'text/html'});
  if(p==='/app/test-student'||p==='/app/parent/test')return route.fulfill({body:'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app/day_off_planner.css"><main id="'+(p.includes('/parent/')?'root':'content')+'"></main>',contentType:'text/html'});
  const file=path.join(root,'web',p.replace(/^\/app\//,''));if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file});return route.fulfill({body:''});
 });
 await page.goto('https://qa.adelia/app/teacher.html');for(const f of ['day_off_shared.js','teacher_schedule_settings.js','teacher_day_off_preview.js'])await page.addScriptTag({url:'/app/'+f});await page.evaluate(()=>window.teacherSchedule());
 await page.locator('[name=reason_template]').selectOption('CUSTOM');await page.locator('[name=reason]').fill('Моя личная причина');await page.locator('[name=share_reason]').uncheck();await page.locator('[name=date]').fill('2026-11-03');await page.locator('[name=date]').dispatchEvent('change');await page.locator('[name=end_date]').fill('2026-11-04');
 await page.locator('#doForm [type=submit]').click();await page.locator('#doSave').waitFor();assert.equal(submitted.share_reason,false);assert.equal(submitted.end_date,'2026-11-04');
 await page.locator('[name=reason]').fill('Моя личная причина, дополненная');assert(await page.locator('#doSave').isDisabled());await page.locator('#doForm [type=submit]').click();await page.locator('#doSave:not(:disabled)').waitFor();
 await page.locator('#dayOffPreviewPanel').screenshot({path:`/tmp/adelia-day-off-teacher-${width}.png`});await page.locator('#doSave').click();await page.locator('[data-dayoff-picker]').waitFor();assert.equal(saved,true);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 for(const role of ['student','parent']){
  moved=false;await page.goto('https://qa.adelia/app/'+(role==='student'?'test-student':'parent/test'));for(const f of ['day_off_shared.js','student_day_off.js'])await page.addScriptTag({url:'/app/'+f});await page.locator('[data-off-id]').click();await page.getByRole('button',{name:'16:45',exact:true}).click();await page.getByRole('button',{name:'Подтвердить перенос',exact:true}).click();await page.getByText('Занятие перенесено. Оплата сохранена.',{exact:true}).waitFor();assert(moved);await page.getByRole('button',{name:'Готово',exact:true}).click();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 }
 console.log(`DAY_OFF_BROWSER_${width}=OK`);
}
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
