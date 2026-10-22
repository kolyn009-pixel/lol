const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const timeCode=fs.readFileSync(path.join(root,'web/teacher_time.js'),'utf8');
const guardCode=fs.readFileSync(path.join(root,'web/teacher_boot_guard.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function runtime(fetch){
 const timers=new Map();let id=0;
 const document={querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){},hidden:true};
 const context={window:{addEventListener(){},dispatchEvent(){}},document,fetch,AbortController,Intl,Date,Promise,Event,console,
  navigator:{},setTimeout(fn,ms){timers.set(++id,{fn,ms});return id},clearTimeout(key){timers.delete(key)},setInterval(){return 1}};
 vm.createContext(context);vm.runInContext(timeCode,context);
 return{context,timers,fire(ms){for(const [key,value]of [...timers])if(value.ms===ms){timers.delete(key);value.fn()}}};
}
async function timeoutAndRetry(){
 let count=0;let finishFirst;
 const r=runtime(()=>{count++;if(count===1)return new Promise(resolve=>finishFirst=resolve);return Promise.resolve({status:200,ok:true,json:async()=>({timezone:{zone:'Europe/Moscow',schedule_zone:'Europe/Moscow'}})})});
 const first=r.context.window.TeacherTime.ready();
 const second=r.context.window.TeacherTime.ready();
 assert.equal(first,second,'Concurrent callers must share the request');
 const rejected=assert.rejects(first,/NETWORK_TIMEOUT/);
 r.fire(12000);await rejected;
 await r.context.window.TeacherTime.ready();assert.equal(count,2,'Manual retry must make a new request');
 assert.equal(r.context.window.TeacherTime.preference.zone,'Europe/Moscow');
 finishFirst({status:200,ok:true,json:async()=>({timezone:{zone:'Europe/Samara',schedule_zone:'Europe/Moscow'}})});
 await tick();assert.equal(r.context.window.TeacherTime.preference.zone,'Europe/Moscow','A late timed-out response must not overwrite the recovered value');
}
async function stalledBody(){
 const r=runtime(async()=>({status:200,ok:true,json:()=>new Promise(()=>{})}));
 const pending=assert.rejects(r.context.window.TeacherTime.ready(),/NETWORK_TIMEOUT/);
 await tick();r.fire(12000);await pending;
}
async function unauthorized(){
 const r=runtime(async()=>({status:401,ok:false}));
 await r.context.window.TeacherTime.ready();assert.equal(r.context.window.TeacherTime.preference,null);
}
async function watchdog(){
 const details={textContent:''},check={},reload={};
 const panel={querySelector(selector){return selector.includes('details')?details:selector.includes('check')?check:reload}};
 let markup='';const app={querySelector:()=>true,firstElementChild:panel,set innerHTML(text){markup=text}};
 let timer;const hooks={};const location={origin:'https://adeliatutor.ru',href:'https://adeliatutor.ru/app/teacher.html',replace(url){this.reloaded=url}};
 const retained=[{url:'https://adeliatutor.ru/app/teacher_time.js?v=old'},{url:'https://adeliatutor.ru/app/parent/pwa.js'},{url:'https://adeliatutor.ru/app/student_boot.js'}],deleted=[];
 const context={window:{addEventListener(type,fn){hooks[type]=fn}},document:{querySelector:()=>app},location,URL,Date,Set,Promise,AbortController,
  setTimeout(fn,ms){if(ms===18000)timer=fn;return 1},clearTimeout(){},fetch:async()=>({ok:true,json:async()=>({ok:true})}),
  caches:{keys:async()=>['adelia-shell-v23'],open:async()=>({keys:async()=>retained,delete:async request=>deleted.push(request.url)})}};
 context.window.caches=context.caches;
 vm.createContext(context);vm.runInContext(guardCode,context);
 assert.equal(typeof timer,'function','Recovery must arm before the window load event');
 hooks.error({target:{src:'https://adeliatutor.ru/app/teacher_time.js?secret=DO_NOT_REPORT'}});
 timer();assert.match(markup,/Не удалось завершить/);assert.match(details.textContent,/teacher_time.js/);assert.ok(!details.textContent.includes('secret'));
 await check.onclick({currentTarget:check});assert.match(details.textContent,/Сервер отвечает/);
 await reload.onclick({currentTarget:reload});assert.equal(deleted.length,1);assert.match(deleted[0],/teacher_time/);assert.match(location.reloaded,/boot_refresh=/);
}
(async()=>{await timeoutAndRetry();await stalledBody();await unauthorized();await watchdog();console.log('TEACHER_BOOT_TIMEOUT_RETRY_BODY_AUTH_AND_RECOVERY=OK')})().catch(error=>{console.error(error);process.exitCode=1});
