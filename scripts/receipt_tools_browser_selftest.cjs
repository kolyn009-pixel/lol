const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.ADELIA_CHROMIUM_EXECUTABLE?{executablePath:process.env.ADELIA_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--no-zygote','--single-process']}:{})});try{const page=await browser.newPage();
for(const width of [1440,390]){
 await page.unroute('https://qa.adelia/**');await page.setViewportSize({width,height:950});let paid=false,reviews=[];
 await page.route('https://qa.adelia/**',async route=>{const u=new URL(route.request().url()),p=u.pathname;
  if(p==='/api/teacher/finance/receipts')return route.fulfill({json:{summary:{waiting:paid?0:1,approved:paid?1:0,waiting_amount:1800},items:[{receipt_id:1,payment_id:1,name:'Кирилл',subject:'PHYSICS',lessons_count:2,total_amount:1800,receipt_status:paid?'APPROVED':'WAITING',payment_status:paid?'PAID':'WAITING',source_platform:'WEB',file_type:'PNG',can_view_file:true}]}});
  if(p==='/api/teacher/finance/receipt/details')return route.fulfill({json:{payment_id:1,status:paid?'PAID':'WAITING',total_amount:1800,paid_on:paid?'2026-10-12':null,today:'2026-10-22',receipts:[{id:1}],lessons:[{id:37,start_time:'2026-10-12T18:15:00'}]}});
  if(p==='/api/teacher/finance/receipt/inspect')return route.fulfill({json:{amount_kopeks:90000,expected_kopeks:180000,paid_on:'2026-10-12',recipient:'<img src=x onerror="window.bad=true">',transfer_status:'SUCCESS_TEXT',method:'OCR',text_excerpt:'Тестовый текст',warnings:['Сумма в чеке отличается от суммы платежа.'],duplicates:[]}});
  if(p==='/api/teacher/finance/receipt/review'){const b=route.request().postDataJSON();reviews.push(b);if(b.note.length<5)return route.fulfill({status:409,json:{error:'Укажите причину подтверждения.'}});paid=true;return route.fulfill({json:{status:'ok'}})}
  if(p==='/app/teacher.html')return route.fulfill({body:fs.readFileSync(path.join(root,'web/teacher.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''),contentType:'text/html'});
  const file=path.join(root,'web',p.replace(/^\/app\//,''));if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file});return route.fulfill({body:''});
 });
 await page.goto('https://qa.adelia/app/teacher.html');for(const f of ['teacher_finance_receipts.js','teacher_receipt_review_tools.js'])await page.addScriptTag({url:'/app/'+f});await page.evaluate(()=>window.teacherReceipts('WAITING',document.querySelector('#app')));
 await page.locator('[data-receipt-action=APPROVE]').click();await page.getByText('Сумма в чеке отличается от суммы платежа.',{exact:true}).waitFor();assert.equal(await page.locator('.rr-date').inputValue(),'2026-10-12');assert.equal(await page.evaluate(()=>window.bad),undefined);
 await page.locator('.rr-approve').click();assert.equal(reviews.length,0);await page.locator('.rr-bank').check();await page.locator('.rr-approve').click();await page.getByText('Укажите причину подтверждения.',{exact:true}).waitFor();
 await page.locator('.rr-note').fill('Поступление проверено в банке, чек на часть суммы.');await page.locator('.rr-approve').click();await page.locator('.receipt-card .badge').filter({hasText:'Подтверждён'}).waitFor();assert.equal(reviews.length,2);assert.equal(reviews[1].paid_on,'2026-10-12');assert.equal(reviews[1].acknowledged,true);
 await page.locator('[data-receipt-details]').click();await page.locator('.rr-date:disabled').waitFor();assert.equal(await page.locator('.rr-date').inputValue(),'2026-10-12');assert.equal(await page.locator('.rr-approve').count(),0);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:`/tmp/adelia-receipt-tools-${width}.png`,fullPage:true});console.log(`RECEIPT_TOOLS_BROWSER_${width}=OK`);
}
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
