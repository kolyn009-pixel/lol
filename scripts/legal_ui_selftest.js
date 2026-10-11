'use strict';
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const edition={version:'test-edition',published_at:'2026-10-02T12:00:00Z',name:'Тестовый исполнитель <script>alert(1)</script>',inn:'500100732259',email:'test@example.com',phone:'+79990000000',address:'Тестовый адрес',terms:'Условия занятий. '.repeat(40),privacy:'Политика обработки данных. '.repeat(40),consent:'Отдельное согласие. '.repeat(40)};
 let accepted=null,stale=true;const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://adelia.test/**',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/api/public/legal')return route.fulfill({json:{edition}});
  if(u.pathname==='/api/parent/legal/status')return route.fulfill({json:{configured:true,required:true,edition}});
  if(u.pathname==='/api/parent/legal/accept'){accepted=route.request().postDataJSON();return route.fulfill({status:stale?409:200,json:stale?{error:'documents_changed'}:{required:false}});}
  if(u.pathname==='/api/teacher/legal')return route.fulfill({json:{draft:{},published:null}});
  if(u.pathname==='/api/parent/dashboard')return route.fulfill({status:428,json:{error:'legal_acceptance_required'}});
  if(u.pathname==='/app/parent/')return route.fulfill({contentType:'text/html',body:'<h1>Кабинет</h1>'});
  const local=path.join(__dirname,'..','web',u.pathname.replace(/^\/app\//,''));
  if(fs.existsSync(local)&&fs.statSync(local).isFile())return route.fulfill({body:fs.readFileSync(local),contentType:u.pathname.endsWith('.js')?'text/javascript':u.pathname.endsWith('.css')?'text/css':'text/html'});
  return route.fulfill({status:404,body:'not found'});
 });
 await page.goto('https://adelia.test/app/legal.html');await page.locator('#details').waitFor();
 assert((await page.locator('#details').innerText()).includes('<script>'));assert.equal(await page.locator('#legalContent script').count(),0);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'/tmp/adelia-legal-mobile.png',fullPage:true});
 await page.goto('https://adelia.test/app/parent/consent.html');await page.locator('#acceptForm').waitFor({state:'visible'});
 assert(await page.locator('button[type=submit]').isDisabled());
 for(const name of ['terms','privacy_ack','consent'])await page.locator(`[name=${name}]`).check();
 await page.locator('button[type=submit]').click();await page.getByText('Документы обновились.',{exact:false}).waitFor();
 assert(await page.locator('button[type=submit]').isDisabled());assert.equal(await page.locator('input:checked').count(),0);
 assert.deepEqual(accepted,{version:'test-edition',terms:true,privacy_ack:true,consent:true});
 stale=false;for(const name of ['terms','privacy_ack','consent'])await page.locator(`[name=${name}]`).check();
 await page.locator('button[type=submit]').click();await page.waitForURL('https://adelia.test/app/parent/');
 await page.goto('https://adelia.test/app/legal-admin.html');await page.locator('#legalForm').waitFor({state:'visible'});
 assert((await page.locator('[name=terms]').inputValue()).includes('[Заполнить'));
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.goto('https://adelia.test/app/parent/');await page.addScriptTag({url:'https://adelia.test/app/parent/legal_gate.js'});
 await page.evaluate(()=>fetch('/api/parent/dashboard').then(()=>{}));await page.waitForURL('https://adelia.test/app/parent/consent.html');
 assert.deepEqual(errors,[]);await browser.close();console.log('LEGAL_UI_MOBILE_AND_GATE=PASS');
})().catch(e=>{console.error(e);process.exit(1);});
