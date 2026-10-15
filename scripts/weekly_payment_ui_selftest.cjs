// npm install --prefix /tmp/adelia-payment-test linkedom@0.18.13
const {parseHTML}=require(process.env.ADELIA_TEST_DOM||'linkedom');
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/parent/payment_claim.js'),'utf8');
const tick=()=>new Promise(r=>setImmediate(r));
async function setup({pending=null,tariffs=[{selection_key:3,subject:'MATH',study_goal:'SCHOOL',duration:60}],quoteHandler=null,failHub=false}={}){
 const {window}=parseHTML('<html><body><div id="root"><button data-student="19"></button></div></body></html>');delete window.AdeliaParentPaymentClaim;const {document}=window,writes=[];let hubCalls=0;
 const fetch=async(url,opt={})=>{const body=opt.body?JSON.parse(opt.body):null;if(body)writes.push({url,body});let data={};
 if(url.includes('/hub')){hubCalls++;if(failHub&&hubCalls===1)throw Error('offline');data={finance:{tariffs,waiting_payment:pending,payment_method:'Перевод по реквизитам'}}}
 else if(url.endsWith('/quote')){if(quoteHandler)return quoteHandler(body);data={lessons_count:body.lessons_count,duration:60,total_amount:body.lessons_count*1500}}
 else if(url.endsWith('/package'))data={payment:{id:42,status:'WAITING',lessons_count:body.lessons_count,total_amount:3000,subject:'MATH'},payment_method:'Реквизиты'};
 return {ok:true,json:async()=>data}};
 class FileReader{readAsDataURL(){this.result='data:application/pdf;base64,JVBERi0=';this.onload()}}
 const context=vm.createContext({window,document,fetch,FileReader,AbortController,setTimeout,clearTimeout,Intl,console});vm.runInContext(source,context);
 document.querySelector('[data-student]').dispatchEvent(new window.Event('click',{bubbles:true}));
 document.querySelector('#root').innerHTML='<button id="back"></button><main class="wrap"><section><div class="section-title"><h2>Оплата</h2></div></section></main>';
 window.dispatchEvent(new window.Event('adelia:parent-render'));await tick();await tick();
 return {window,document,writes,el:s=>document.querySelector(s)};
}
(async()=>{
 let s=await setup();assert.match(s.el('[data-quote]').textContent,/3\s?000/);assert.equal(s.el('[data-count="2"]').getAttribute('aria-pressed'),'true');
 const create=s.el('[data-create]');create.onclick();create.onclick();await tick();assert.equal(s.writes.filter(x=>x.url.endsWith('/package')).length,1);assert.equal(s.writes.find(x=>x.url.endsWith('/package')).body.lessons_count,2);
 assert.equal(s.el('[data-send]')!==null,true);s.el('[data-file]').files=[{name:'week.pdf',type:'application/pdf',size:300000}];await s.el('[data-send]').onclick();await tick();assert.equal(s.writes.filter(x=>x.url.endsWith('/receipt')).length,1);assert.deepEqual(s.writes.find(x=>x.url.endsWith('/receipt')).body,{student_id:'19',payment_id:42,filename:'week.pdf',mime_type:'application/pdf',content_b64:'JVBERi0='});assert.match(s.el('[data-payment-action]').textContent,/Ожидает проверки/);assert.equal(s.el('[data-send]'),null);
 s=await setup({pending:{id:1,status:'RECEIPT_SENT',lessons_count:2,total_amount:3000}});assert.equal(s.el('[data-create]'),null);assert.equal(s.el('[data-send]'),null);
 s=await setup({pending:{id:1,status:'WAITING',lessons_count:2,total_amount:3000}});s.el('[data-file]').files=[{name:'large.pdf',type:'application/pdf',size:9*1024*1024}];await s.el('[data-send]').onclick();assert.match(s.el('[data-status]').textContent,/8 МБ/);assert.equal(s.writes.filter(x=>x.url.endsWith('/receipt')).length,0);s.el('[data-file]').files=[{name:'ok.pdf',type:'application/pdf',size:400000}];await s.el('[data-send]').onclick();await tick();assert.equal(s.el('[data-create]'),null);
 s=await setup({tariffs:[{selection_key:1,subject:'MATH',duration:60},{selection_key:2,subject:'PHYSICS',duration:90}]});assert.equal(s.el('[data-create]').disabled,true);assert.equal(s.writes.length,0);
 let resolvers=[];s=await setup({quoteHandler:body=>new Promise(resolve=>resolvers.push(()=>resolve({ok:true,json:async()=>({lessons_count:body.lessons_count,duration:60,total_amount:body.lessons_count*1500})}))) });
 s.el('[data-count="4"]').onclick();resolvers[1]();await tick();resolvers[0]();await tick();assert.match(s.el('[data-quote]').textContent,/6\s?000/);assert.doesNotMatch(s.el('[data-quote]').textContent,/3\s?000/);
 s=await setup({failHub:true});assert.ok(s.el('[data-retry]'));s.el('[data-retry]').onclick();await tick();await tick();assert.ok(s.el('[data-create]'));
 console.log('WEEKLY_PAYMENT_UI=OK: 2 lessons, one receipt, duplicate click, review lock, file size, explicit tariff, quote race, retry');
})().catch(e=>{console.error(e);process.exitCode=1});
