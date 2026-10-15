/* Isolated Chromium journeys using production HTML/JS and fixture API responses. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),outputs=path.join(root,'qa-mobile');
const now=new Date(),future=h=>new Date(now.getTime()+h*3600000).toISOString();
const lesson={id:10,user_id:1,name:'Тестовый ученик',start_time:future(24),start_at:future(24),end_time:future(25),duration_minutes:60,subject:'MATH',study_goal:'SCHOOL',lesson_status:'CONFIRMED',payment_status:'AWAITING_PAYMENT',price:1750};
const student={id:1,name:'Тестовый ученик',grade:8,study_goal:'SCHOOL',main_subject:'MATH',education_type:'SCHOOL',education_level:8,timezone:{zone:'Europe/Moscow',label:'Москва',selected:true},board_url:'https://example.test/board'};
const tariff={selection_key:3,program_id:3,subject:'MATH',study_goal:'SCHOOL',duration:60,nominal:1750,hourly_rate:1750,balance:{total:0}};
const dash={student,next_lesson:lesson,active_homework:1,unread_messages:1,payments_waiting:0,stats:{},today_lessons:[],week_lessons:[],next_lessons:[],pending_reviews:[]};
const homework={id:5,title:'Задачи на движение',description:'Решите задачу.',mode:'MANUAL',status:'ASSIGNED'};
const parentDash={parent:{id:7,name:'Родитель'},students:[student],upcoming:[lesson],summary:{upcoming_lessons:2,balance_minutes:0,waiting_amount:0,waiting_payments:0}};
(async()=>{fs.mkdirSync(outputs,{recursive:true});let args=['--no-sandbox'],executablePath=process.env.ADELIA_CHROMIUM;
 if(process.env.ADELIA_CHROMIUM_HELPER){const c=(await import(process.env.ADELIA_CHROMIUM_HELPER)).default;args=c.args.filter(x=>x!=='--single-process')}
 const browser=await chromium.launch({headless:true,args,...(executablePath?{executablePath}:{})});try{
 for(const role of ['parent','student','teacher']){const ctx=await browser.newContext({viewport:{width:390,height:844},timezoneId:'Europe/Moscow',serviceWorkers:'block'}),page=await ctx.newPage(),errors=[],writes=[],unknown=new Set();let pending=null,chatFail=false,homeworkFail=false,lessonOpen=false,loggedIn=true;
 await page.clock.install({time:now});page.setDefaultTimeout(8000);console.log('START',role);page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://adelia.test/**',async route=>{const req=route.request(),u=new URL(req.url()),p=u.pathname;let d={};
 if(!p.startsWith('/api/')){let file=path.join(root,'web',p.replace(/^\/app\/?/,''));if(p==='/teacher/'||p==='/app/teacher.html')file=path.join(root,'web/teacher.html');if(p.endsWith('/')&&p!=='/teacher/')file=path.join(file,'index.html');
 if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/octet-stream',body:fs.readFileSync(file)});
 if(/\.(png|svg|ico|webmanifest)$/.test(p))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"/>'});return route.fulfill({status:404,body:'missing fixture asset'});}
 if(req.method()==='POST')writes.push({path:p,body:req.postDataJSON()});
 if(p==='/api/health'&&u.searchParams.has('token'))return route.fulfill({status:503,json:{error:'PRIVATE_TEST_ERROR'}});
 if(!loggedIn&&p==='/api/parent/dashboard')return route.fulfill({status:401,json:{error:'unauthorized'}});
 if(p==='/api/auth/parent/code'){if(req.postDataJSON().code!=='123456')return route.fulfill({status:401,json:{error:'invalid_code'}});loggedIn=true;return route.fulfill({json:{ok:true}});}
 if(p==='/api/auth/me')d={authenticated:true,role,session:{role,id:role==='parent'?7:1}};
 else if(p==='/api/health')d={ok:true,service:'adelia-web'};
 else if(p==='/api/parent/dashboard')d=parentDash;
 else if(p==='/api/parent/student')d={student,programs:[],lessons:{upcoming:2,recent:[lesson]},payments:pending?[pending]:[],minute_balance:{total:pending?.status==='PAID'?120:0},packages:{items:[]}};
 else if(p==='/api/parent/finance/payment')d={payment:pending};
 else if(p==='/api/parent/finance/hub'||p==='/api/student/payment-hub')d={student,schedule_timezone:'Europe/Moscow',nearest_unpaid_lesson:lesson,upcoming_lessons:[lesson,{...lesson,id:11,start_at:future(72),start_time:future(72)}],finance:{balance:{total:pending?.status==='PAID'?120:0},tariffs:[tariff],waiting_payment:pending?.status==='PAID'?null:pending,recent_payments:pending?[pending]:[],payment_method:'Тестовые реквизиты'}};
 else if(p.endsWith('/finance/package/quote')||p.endsWith('/finance/quote')){const body=req.method()==='POST'?req.postDataJSON():Object.fromEntries(u.searchParams);d={lessons_count:+body.lessons_count,duration:60,minutes_total:+body.lessons_count*60,total_amount:+body.lessons_count*1750};}
 else if(p.endsWith('/finance/package')){pending={id:42,status:'WAITING',lessons_count:2,total_amount:3500,minutes_total:120,subject:'MATH'};d={payment:pending,payment_method:'Тестовые реквизиты'};}
 else if(p.endsWith('/finance/receipt')){pending.status='RECEIPT_SENT';d={status:'ok',receipt_id:1};}
 else if(p==='/api/student/profile')d={student,onboarding_required:false,profile_complete:true,onboarding_completed:true};
 else if(p==='/api/student/dashboard')d=dash;
 else if(p==='/api/student/lesson')d={lesson:{...lesson,entry_open:lessonOpen,payment_required:false},board_url:'https://example.test/board'};
 else if(p==='/api/student/lesson/join')d={meeting_url:'https://example.test/lesson'};
 else if(p==='/api/student/schedule')d={upcoming:[lesson],past:[],items:[lesson]};
 else if(p==='/api/student/homework')d={items:[homework]};
 else if(p==='/api/student/homework/detail')d={homework,materials:[],attachments:[],tasks:[]};
 else if(p==='/api/student/homework/feedback')d={can_submit:true};
 else if(p==='/api/student/homework/manual-submit'){if(homeworkFail)return route.fulfill({status:503,json:{error:'Попробуйте позже'}});d={status:'ok'};}
 else if(p==='/api/student/messages')d={items:[]};
 else if(p==='/api/parent/messages/students')d={items:[student]};
 else if(p==='/api/parent/messages')d={items:[]};
 else if(p==='/api/parent/messages/send'){if(chatFail)return route.fulfill({status:503,json:{error:'Тестовый сбой'}});d={status:'ok'};}
 else if(p.includes('/finance/overview'))d={balance:{total:0},tariffs:[tariff],waiting_payment:pending};
 else if(p==='/api/teacher/dashboard')d=dash;
 else if(p==='/api/teacher/display-timezone')d={timezone:{zone:'Europe/Moscow',label:'Москва',selected:true},zone:'Europe/Moscow',label:'Москва',selected:true};
 else if(p==='/api/teacher/finance/receipts')d={items:[],summary:{waiting:1}};
 else if(p==='/api/teacher/requests')d={counts:{trial:0,lesson:1,schedule:0},items:[]};
 else if(p==='/api/teacher/students')d=[student];
 else if(p.includes('messages'))d={items:[]};
 else if(p.includes('robokassa/status'))d={enabled:false};
 else if(p.includes('onboarding'))d={required:false,completed:true};
 else if(p.includes('timezone'))d={timezone:student.timezone,...student.timezone};
 else {unknown.add(p);d={items:[],balance:{total:0},summary:{},counts:{},stats:{}};}
 return route.fulfill({contentType:'application/json',body:JSON.stringify(d)});
 });
 await page.goto('http://adelia.test'+(role==='parent'?'/app/parent/':role==='teacher'?'/teacher/':'/app/'));await page.waitForTimeout(1800);console.log('LOADED',role);
 if(role==='parent'){
 await page.getByRole('heading',{name:/2 занятия ·/}).waitFor();await page.locator('[data-student="1"]').click();await page.locator('[data-create]').waitFor();assert.match(await page.locator('[data-quote]').innerText(),/3\s?500/);assert.equal(await page.locator('[data-dates] li').count(),2);await page.locator('[data-create]').click();await page.locator('[data-file]').setInputFiles({name:'receipt.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.5\nfixture')});await page.locator('[data-send]').click();await page.getByText('Чек отправлен. Ожидает проверки преподавателем.').waitFor();assert.equal(writes.filter(w=>w.path.endsWith('/finance/package')).length,1);assert.equal(writes.filter(w=>w.path.endsWith('/finance/receipt')).length,1);assert.equal(await page.locator('[data-create]').count(),0);
 pending.status='PAID';await page.clock.runFor(16000);await page.getByText(/Последняя подтверждённая оплата/).waitFor();assert.match(await page.locator('[data-balance]').innerText(),/120 мин/);
 await page.locator('#back').click();await page.locator('#parentMessagesOpen').click();await page.locator('#pmText').fill('Черновик сообщения');chatFail=true;await page.locator('#pmForm [type=submit]').click();await page.getByText(/Не отправлено/).waitFor();assert.equal(await page.locator('#pmText').inputValue(),'Черновик сообщения');await page.locator('#pmClose').click();await page.locator('#parentMessagesOpen').click();assert.equal(await page.locator('#pmText').inputValue(),'Черновик сообщения');await page.reload();await page.locator('#parentMessagesOpen').click();assert.equal(await page.locator('#pmText').inputValue(),'Черновик сообщения');chatFail=false;await page.locator('#pmForm [type=submit]').click();await page.waitForFunction(()=>document.querySelector('#pmText').value==='');await page.locator('#pmClose').click();
 }
 if(role==='student'){
 await page.screenshot({path:path.join(outputs,'student-home.png'),fullPage:true}); await page.locator('.nav-item[data-tab=homework]').click();await page.locator('[data-hw="5"]').first().click();await page.locator('#manualHwComment').fill('Сохрани мой комментарий');homeworkFail=true;await page.locator('#manualHwSubmit').click();await page.locator('#studentHwResult .form-error').waitFor();assert.equal(await page.locator('#manualHwComment').inputValue(),'Сохрани мой комментарий');await page.locator('#studentHwBack').click();await page.locator('[data-hw="5"]').first().click();assert.equal(await page.locator('#manualHwComment').inputValue(),'Сохрани мой комментарий');
 await page.goto('http://adelia.test/app/lesson/?id=10');await page.getByRole('heading',{name:'Преподаватель ещё не открыл занятие'}).waitFor();lessonOpen=true;await page.reload();await page.evaluate(()=>window.open=()=>({closed:false}));await page.locator('#joinLesson').click();assert.equal(writes.filter(w=>w.path==='/api/student/lesson/join').length,1);
 }
 if(role==='teacher'){await page.locator('#teacherAttention').waitFor();assert.ok(await page.locator('[data-attention=payments]').count());await page.locator('[data-attention-refresh]').click()}
 await page.evaluate(()=>fetch('/api/health?token=PRIVATE_TEST_TOKEN&text=PRIVATE_TEXT').catch(()=>{}));await page.locator('[data-adelia-support]').click();await page.locator('#adeliaSupport').waitFor();const report=await page.evaluate(()=>window.AdeliaReliability.report());assert.ok(!JSON.stringify(report).includes('PRIVATE_'));assert.ok(report.events.some(e=>e.route==='/api/health'&&e.status===503));assert.ok(!JSON.stringify(report).includes('Черновик'));assert.ok(!JSON.stringify(report).includes('Сохрани мой'));await page.screenshot({path:path.join(outputs,role+'-support.png'),fullPage:true});await page.locator('[data-close]').click();
 for(const width of [390,320]){await page.setViewportSize({width,height:844});if(!(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)))console.log('OVERFLOW',role,width,await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.id,e.className,Math.round(e.getBoundingClientRect().width)]).slice(0,15)));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,role+' width '+width)}
 await page.screenshot({path:path.join(outputs,role+'.png'),fullPage:true});if(role==='parent'){loggedIn=false;await page.goto('http://adelia.test/app/parent/');await page.locator('#code').fill('000000');await page.locator('#loginForm button').click();await page.getByText('Не удалось войти. Проверьте код.').waitFor();await page.locator('#code').fill('123456');await page.locator('#loginForm button').click();await page.locator('[data-student="1"]').waitFor()}
 console.log(role,'pageerrors',errors,'unmapped API',Array.from(unknown));assert.deepEqual(errors,[]);await ctx.close();
 }
 console.log('MOBILE_JOURNEYS=OK: parent weekly receipt/status/chat recovery; student homework recovery; support + 320/390px across 3 roles');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
