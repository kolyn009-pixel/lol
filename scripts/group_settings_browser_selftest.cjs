const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),outputs=process.env.ADELIA_QA_OUTPUT||'/tmp/adelia-group-design';
fs.mkdirSync(outputs,{recursive:true});
const token='a'.repeat(43),initial={id:7,name:'ЕГЭ · Физика · Группа 1',subject:'PHYSICS',study_goal:'EGE',description:'Готовимся к ЕГЭ на 75+ баллов. Разбираем теорию понятным языком, решаем экзаменационные задачи и учимся уверенно применять формулы.',price_per_lesson:900,max_members:6,min_attendees:3,recruitment_status:'OPEN',chat_mode:'OPEN',board_url:'',members:[],slots:[{weekday:0,start_time:'19:00',duration_minutes:90}]};
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.ADELIA_CHROMIUM_EXECUTABLE?{executablePath:process.env.ADELIA_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--no-zygote','--single-process']}:{})});try{
 const page=await browser.newPage();
 for(const width of [1440,1024,390,320]){
  await page.unroute('https://qa.adelia/**');await page.setViewportSize({width,height:1000});
  let group=structuredClone(initial),conflict=true,added=false;
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>window.copiedInvite=text},configurable:true}));
  await page.route('https://qa.adelia/**',async route=>{
   const u=new URL(route.request().url());
   if(u.pathname.startsWith('/api/teacher/group/')){
    if(u.pathname.endsWith('/weekly-session')){if(conflict)return route.fulfill({status:409,json:{error:'schedule_conflict:28.10.2026 18:15'}});added=true;group.slots.push({weekday:2,start_time:'18:15',duration_minutes:60,starts_on:'2026-10-28',ends_on:'2026-12-16'});return route.fulfill({json:{lesson_count:8,starts_on:'2026-10-28',ends_on:'2026-12-16'}})}
    if(route.request().method()==='POST'){group={...group,...route.request().postDataJSON()};return route.fulfill({json:{status:'ok'}})}
    return route.fulfill({json:{group,timezone:'Europe/Moscow',invite_path:'/app/group-invite.html?invite='+token}});
   }
   if(u.pathname==='/app/teacher.html'){let html=fs.readFileSync(path.join(root,'web/teacher.html'),'utf8');html=html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'');return route.fulfill({body:html,contentType:'text/html'})}
   if(u.pathname.endsWith('.js')&&!u.pathname.endsWith('/teacher_group_settings.js'))return route.fulfill({body:'',contentType:'application/javascript'});
   const file=path.join(root,'web',u.pathname.replace(/^\/app\//,''));
   if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file});
   if(/\.(png|ico)$/.test(u.pathname))return route.fulfill({path:path.join(root,'brand/existing-icon.png')});
   return route.fulfill({body:'',status:200});
  });
  await page.goto('https://qa.adelia/app/teacher.html');await page.addScriptTag({url:'/app/teacher_group_settings.js'});await page.evaluate(()=>window.AdeliaGroupSettings.open(7));
  await page.locator('#adeliaGroupSettingsStyle').evaluate(el=>el.sheet?true:new Promise(resolve=>el.onload=()=>resolve(true)));
  assert.equal(await page.locator('[role=tab][aria-selected=true]').textContent(),'Основное');
  await page.screenshot({path:path.join(outputs,`group-settings-${width}.png`),fullPage:true});
  await page.locator('[name=name]').fill('Физика ЕГЭ · Обновлено');
  await page.locator('[data-gs-tab=schedule]').click();await page.locator('#gsWeeklyDetails summary').click();
  await page.locator('#gsWeeklyForm [name=weekday]').selectOption('2');await page.locator('#gsWeeklyForm [name=start_time]').fill('18:15');await page.locator('#gsWeeklyForm [name=starts_on]').fill('2026-10-26');
  await page.locator('#gsWeeklyForm [type=submit]').click();await page.locator('#gsWeeklyState.is-error').waitFor();assert((await page.locator('#gsWeeklyState').textContent()).includes('28.10.2026'));
  conflict=false;await page.locator('#gsWeeklyForm [type=submit]').click();await page.waitForFunction(()=>document.querySelector('#gsWeeklyCount').textContent==='2');assert(added);
  await page.screenshot({path:path.join(outputs,`group-schedule-${width}.png`),fullPage:true});
  await page.locator('[data-gs-tab=settings]').click();assert.equal(await page.locator('[name=name]').inputValue(),'Физика ЕГЭ · Обновлено');await page.locator('#gsSave').click();await page.waitForFunction(()=>document.querySelector('#gsGroupName').textContent==='Физика ЕГЭ · Обновлено');
  await page.locator('[data-gs-tab=invite]').click();await page.locator('#gsCopy').click();assert((await page.evaluate(()=>window.copiedInvite)).endsWith(token));
  await page.screenshot({path:path.join(outputs,`group-invite-${width}.png`),fullPage:true});
  for(const tab of ['settings','schedule','members','invite']){await page.locator('[data-gs-tab='+tab+']').click();const overflow=await page.locator('.agw').evaluate(el=>({right:el.getBoundingClientRect().right,width:innerWidth,wide:document.documentElement.scrollWidth}));assert(overflow.right<=width+1&&overflow.wide<=width+1,JSON.stringify({width,tab,overflow}));assert.equal(await page.locator('[data-gs-pane]:visible').count(),1)}
  assert.deepEqual(errors,[]);console.log(`GROUP_DESIGN_${width}=OK`);
 }
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
