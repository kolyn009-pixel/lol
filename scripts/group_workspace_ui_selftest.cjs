const {JSDOM}=require('jsdom');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),vm=require('vm');
const root=path.resolve(__dirname,'../web'),token='a'.repeat(43);
const source=p=>fs.readFileSync(path.join(root,p),'utf8');
const flush=async()=>{for(let i=0;i<10;i++)await new Promise(r=>setImmediate(r))};
(async()=>{
 const dom=new JSDOM('<div id="scene"></div><div class="progress"><i></i></div>',{url:'https://test.adelia/onboarding/?group_invite='+token,runScripts:'outside-only'}),w=dom.window;
 w.scrollTo=()=>{};w.AbortController=AbortController;let status='CHANNEL_VERIFIED',started,complete;
 w.fetch=async(url,opt={})=>{
  assert(url.startsWith('/api/group-onboarding/'),url);
  const p=url.split('?')[0],body=opt.body?JSON.parse(opt.body):{};
  if(p.endsWith('/start'))started=body;
  if(p.endsWith('/region'))status='SCHEDULE_SET';
  if(p.endsWith('/complete')){complete=body;return {ok:false,status:409,json:async()=>({error:'login_taken'})}};
  return {ok:true,json:async()=>({token:'JOIN-TEST',status,preferred_channel:'TELEGRAM',group_invite:token,schedule:[]})};
 };
 w.eval(source('onboarding/onboarding.js'));await flush();
 const q=s=>w.document.querySelector(s);q('[name=name]').value='Кирилл';
 q('#f').dispatchEvent(new w.Event('submit',{cancelable:true}));q('[data-ch=TELEGRAM]').click();q('#connect').click();await flush();
 assert.equal(started.group_invite,token);assert(q('#region'));
 q('#region').value='Москва';q('#next').click();await flush();assert(q('#cred'));assert.equal(q('#days'),null);
 q('[name=login]').value='kirill';q('[name=password]').value='password123';q('#cred').dispatchEvent(new w.Event('submit',{cancelable:true}));await flush();assert.equal(complete.token,'JOIN-TEST');assert(q('.error').textContent.includes('занят'));
 const saved=w.localStorage.getItem('adelia_returning_onboarding');dom.window.close();
 const resumed=new JSDOM('<div id="scene"></div><div class="progress"><i></i></div>',{url:'https://test.adelia/onboarding/',runScripts:'outside-only'});resumed.window.localStorage.setItem('adelia_returning_onboarding',saved);resumed.window.fetch=w.fetch;resumed.window.AbortController=AbortController;resumed.window.scrollTo=()=>{};
 resumed.window.eval(source('onboarding/onboarding.js'));await flush();assert(resumed.window.document.querySelector('#cred'));resumed.window.close();
 // Existing login continuation survives the URL being replaced by the login flow.
 const storage=new Map();let handler,destination;const context={URLSearchParams,Date,JSON,sessionStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)},window:{addEventListener:(e,h)=>handler=h},location:{search:'?group_invite='+token,replace:p=>destination=p}};
 vm.runInNewContext(source('group_invite_continue.js'),context);context.location.search='';vm.runInNewContext(source('group_invite_continue.js'),context);handler();assert.equal(destination,'/app/group-invite.html?invite='+token);assert.equal(storage.size,0);
 // Actual event list and group cards expose settings, including groups without lessons.
 const events=new JSDOM('<aside><nav></nav></aside><h1 id="title"></h1><div id="app"></div>',{url:'https://test.adelia/app/teacher.html',runScripts:'outside-only'});events.window.fetch=async url=>({ok:true,json:async()=>url.endsWith('/groups')?{items:[{id:7,name:'Физика ЕГЭ',max_members:8,member_count:0}]}:{items:[]}});events.window.eval(source('teacher_events.js'));events.window.document.querySelector('[data-view=events]').click();await flush();assert(events.window.document.querySelector('[data-group-settings="7"]'));assert(!events.window.document.querySelector('#app').textContent.includes('Пока событий нет'));events.window.close();
 console.log('GROUP_WORKSPACE_UI=OK; registration, retry, resume, login continuation, events visibility');
})().catch(e=>{console.error(e);process.exit(1)});
