const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),writes=[];
const data={student:{id:1,name:'Кирилл'},summaries:[{lesson_id:10,start_time:'2026-10-11T10:00:00Z',topics:'Второй закон Ньютона',achievement:'Решает задачи на силы',next_step:'Повторить единицы измерения',published:1}],errors:[{id:3,subject:'PHYSICS',topic:'Перевод единиц',description:'Сантиметры и метры',practice:'Пять коротких задач',status:'OPEN'}],plans:[{id:2,subject:'PHYSICS',target:'ЕГЭ: 80 баллов',target_date:'2027-06-01',progress_percent:50,steps:[{id:7,title:'Механика',status:'DONE'},{id:8,title:'Оптика',status:'TODO'}]}],waiting:[],offers:[],lessons:[{id:10,start_time:'2026-10-11T10:00:00Z',lesson_status:'COMPLETED'}]};
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 for(const role of ['student','parent','teacher']){const context=await browser.newContext({viewport:role==='teacher'?{width:1440,height:1000}:{width:390,height:844},timezoneId:'Europe/Moscow'}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://adelia.test/**',async route=>{const req=route.request(),u=new URL(req.url()),p=u.pathname;let response;
 if(p==='/')return route.fulfill({contentType:'text/html',body:`<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app/learning_hub.css"><body><button data-learning-open>Учебный план</button><script src="/app/learning_hub.js"></script></body></html>`});
 if(p.startsWith('/app/'))return route.fulfill({contentType:p.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(path.join(root,'web',p.slice(5)),'utf8')});
 if(req.method()==='POST'){writes.push({role,path:p,body:req.postDataJSON()});response={status:'ok'};}
 else if(p==='/api/auth/me')response={authenticated:true,session:{role,id:1}};
 else if(p==='/api/teacher/students')response=[{id:1,name:'Кирилл'}];
 else if(p==='/api/parent/messages/students')response={items:[{id:1,name:'Кирилл'}]};
 else if(p.endsWith('/materials'))response={items:[{id:1,title:'Законы Ньютона',description:'Конспект по механике',url:'/api/student/material/file?id=1'}]};
 else if(p.endsWith('/waiting'))response={items:[{id:4,user_id:1,name:'Кирилл',subject:'PHYSICS',preferred_date:'2027-01-15',preferred_from:'16:00',preferred_to:'18:00',timezone:'Europe/Samara',note:'После школы',offers:[]}]};
 else response=structuredClone(data);
 return route.fulfill({contentType:'application/json',body:JSON.stringify(response)});});
 await page.goto('http://adelia.test/');await page.locator('[data-learning-open]').click();await page.locator('#lhStatus').waitFor();
 assert.equal(await page.locator('#learningHubPanel h2').textContent(),'Учебный план и результаты');
 assert.equal(await page.locator('#lhSummary').count(),role==='teacher'?1:0);
 assert.equal(await page.locator('#lhWait').count(),role==='student'?1:0);
 assert.equal(await page.locator('#lhSearch').count(),role==='parent'?0:1);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 if(role!=='parent'){await page.locator('#lhSearch [name=q]').fill('закон');await page.locator('#lhSearch [type=submit]').click();await page.getByRole('link',{name:'Законы Ньютона'}).waitFor();}
 if(role==='teacher'){await page.locator('[data-summary="10"]').click();assert.equal(await page.locator('#lhSummary [name=topics]').inputValue(),'Второй закон Ньютона');await page.locator('#lhSummary [name=published]').uncheck();await page.locator('#lhSummary [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#lhSummary [type=submit]').disabled);
 await page.locator('#lhSlot [name=start_at]').fill('2027-01-15T15:00');await page.locator('#lhSlot [type=submit]').click();await page.locator('[data-send-offer]').click();await page.getByText('Предложение появилось в кабинете ученика.').waitFor();}
 if(role==='student'){await page.locator('#lhWait [name=preferred_date]').fill('2027-01-15');await page.locator('#lhWait [name=preferred_from]').fill('16:00');await page.locator('#lhWait [name=preferred_to]').fill('18:00');await page.locator('#lhWait [type=submit]').click();await page.waitForFunction(()=>!document.querySelector('#lhWait [type=submit]').disabled);}
 await page.screenshot({path:path.join(root,'learning-hub-'+role+'.png'),fullPage:true});assert.deepEqual(errors,[]);await page.keyboard.press('Escape');assert.equal(await page.locator('#learningHubOverlay').count(),0);await context.close();
 }
 assert.equal(writes.find(x=>x.path.endsWith('/summary')).body.published,false);assert.equal(writes.find(x=>x.path.endsWith('/wait')).body.timezone,'Europe/Moscow');assert.equal(writes.find(x=>x.path.endsWith('/offer')).body.start_at,'2027-01-15T12:00:00.000Z');
 console.log('LEARNING_UI=PASS: 3 roles, mobile width, summary edit, material search, wait request, offer conversion, Escape');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
