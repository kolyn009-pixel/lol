const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../web/onboarding/onboarding.js'), 'utf8');
const flush = async () => { for (let i=0;i<60;i++) await Promise.resolve(); };
function harness(saved, responses) {
  let nodes={}, html='', now=0, stored=JSON.stringify(saved), requests=0;
  const intervals=new Map(), timeouts=new Map(); let timer=0;
  const scene={set innerHTML(value){html=value;nodes={};for(const match of value.matchAll(/id="([^"]+)"/g))nodes[match[1]]={textContent:'',disabled:false,hidden:false};nodes['.error']={textContent:''};},get innerHTML(){return html;}};
  const context={URLSearchParams,AbortController,Intl,TypeError,Date:class extends Date {static now(){return now;}},location:{search:'',pathname:'/onboarding/',href:''},history:{replaceState(){}},window:{scrollTo(){}},document:{querySelector(s){return s==='#scene'?scene:s==='.error'?nodes[s]:nodes[s.slice(1)]||null;},querySelectorAll(){return [];}},localStorage:{getItem(){return stored;},setItem(k,v){stored=v;},removeItem(){stored=null;}},setInterval(fn){const id=++timer;intervals.set(id,fn);return id;},clearInterval(id){intervals.delete(id);},setTimeout(fn){const id=++timer;timeouts.set(id,fn);return id;},clearTimeout(id){timeouts.delete(id);},fetch:async (url,options)=>{requests++;const response=responses.shift();if(typeof response==='function')return response(url,options);if(response instanceof Error)throw response;return {ok:!response.error,status:response.error?response.http||400:200,json:async()=>response};}};
  vm.runInNewContext(source,context);
  return {context,nodes:()=>nodes,html:()=>html,intervals,timeouts,requests:()=>requests,stored:()=>stored,advance(ms){now+=ms;}};
}
const saved={token:'JOIN-TEST',channel:'TELEGRAM',schedule:[]};
(async()=>{
  let h=harness(saved,[{status:'WAIT_CHANNEL'},{status:'WAIT_CHANNEL'},{status:'CHANNEL_VERIFIED'}]);await flush();
  assert.match(h.html(),/Подтверждение аккаунта/);assert.match(h.html(),/join_JOIN-TEST/);
  await h.nodes().check.onclick();await flush();assert.match(h.html(),/Настроим часовой пояс/);assert.equal(h.intervals.size,0);
  h=harness(saved,[{status:'WAIT_CHANNEL'},{error:'onboarding_expired'}]);await flush();
  assert.match(h.nodes()['.error'].textContent,/истекла/);assert.equal(h.intervals.size,0);assert.ok(h.nodes().restart.onclick);
  h=harness(saved,[new TypeError('offline'),{status:'WAIT_CHANNEL'},{status:'WAIT_CHANNEL'}]);await flush();
  assert.match(h.nodes()['.error'].textContent,/Нет связи/);assert.ok(h.stored());assert.equal(h.nodes().resumeRetry.hidden,false);
  await h.nodes().resumeRetry.onclick();await flush();assert.match(h.html(),/Подтверждение аккаунта/);
  h=harness(saved,[{status:'WAIT_CHANNEL'},{error:'server_error',http:500},{status:'WAIT_CHANNEL'}]);await flush();
  assert.match(h.nodes()['.error'].textContent,/На сервере/);assert.equal(h.intervals.size,1);
  h.advance(61000);await h.nodes().check.onclick();await flush();assert.match(h.nodes().checking.textContent,/нажали «Начать»/);assert.equal(h.nodes()['.error'].textContent,'');
  let resolve;h=harness(saved,[{status:'WAIT_CHANNEL'},()=>new Promise(r=>{resolve=r;})]);await flush();
  await h.nodes().check.onclick();assert.equal(h.requests(),2);h.nodes().restart.onclick();resolve({ok:true,json:async()=>({status:'CHANNEL_VERIFIED'})});await flush();assert.match(h.html(),/С возвращением/);
  h=harness(saved,[{status:'WAIT_CHANNEL'},(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Object.assign(new Error('aborted'),{name:'AbortError'}))))]);await flush();
  assert.equal(h.timeouts.size,1);[...h.timeouts.values()][0]();await flush();assert.match(h.nodes()['.error'].textContent,/не ответил вовремя/);assert.equal(h.nodes().check.disabled,false);assert.equal(h.timeouts.size,0);
  h=harness({...saved,channel:'VK'},[{status:'WAIT_CHANNEL'},{status:'WAIT_CHANNEL'}]);await flush();assert.match(h.html(),/vk.me\/club241263797/);assert.match(h.html(),/JOIN-TEST/);
  console.log('PASS: resume, verification, expiry, offline retry, server recovery, late response, overlap, timeout, VK');
})().catch(error=>{console.error(error);process.exitCode=1;});
