const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const path=require('path');let parseHTML;try{({parseHTML}=require('linkedom'));}catch{({parseHTML}=require('../qa-deps/node_modules/linkedom'));}
const script=fs.readFileSync(path.join(__dirname,'../web/olympiads.js'),'utf8');
const seed=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/olympiads_2026_2027.json')));
async function check(teacher){
 const {window,document}=parseHTML('<html><body>'+(teacher?'<div class="teacher-shell"><nav><div class="more-items"></div></nav></div>':'<header class="topbar"></header><section id="roleSheet"></section>')+'</body></html>');
 Object.defineProperty(window.HTMLElement.prototype,'elements',{configurable:true,get(){return Object.fromEntries([...this.querySelectorAll('[name]')].map(x=>[x.name||x.getAttribute('name'),x]));}});
 Object.defineProperty(window.HTMLSelectElement.prototype,'value',{configurable:true,get(){return this.querySelector('option[selected]')?.getAttribute('value')||this.querySelector('option')?.getAttribute('value')||'';},set(v){this.querySelectorAll('option').forEach(o=>o.toggleAttribute('selected',o.getAttribute('value')===String(v)));}});
 window.HTMLElement.prototype.showModal=function(){this.open=true;};
 window.HTMLElement.prototype.close=function(){this.open=false;this.dispatchEvent(new window.Event('close'));};
 delete window.AdeliaOlympiads;
 const calls=[];const items=seed.items.map(x=>({...x,title:x.title+(x.registry_number===35?' <img src=x onerror=alert(1)>':''),events:seed.events.filter(([id])=>id===x.id).map(([id,e],i)=>({...e,id:'event-'+i,revision:1,checked_at:seed.verified_at})),sources:[],channels:[],recommendation:null}));
 const payload={items,students:[{id:1,name:'Иван'}],notices:[],deliveries:[],available_channels:['WEB','VK'],season:seed.season,server_time:seed.verified_at};
 window.fetch=async(url,opt)=>{calls.push({url,opt});return{ok:true,json:async()=>url.endsWith('/subscribe')?{status:'ok'}:payload};};
 const context={window,document,fetch:window.fetch,MutationObserver:class{observe(){}},AbortController,setTimeout,clearTimeout,Intl,Date,URL,URLSearchParams,TextEncoder,Blob,FormData:class{},location:{search:''},console};
 vm.runInNewContext(script,context);
 assert(document.querySelector('[data-oy-open]'));
 await window.AdeliaOlympiads.open();
 assert.equal(document.querySelectorAll('.oy-card').length,39);
 assert.equal(document.querySelectorAll('.oy-card h3 img').length,0,'unsafe HTML was interpolated');
 assert.equal(document.querySelectorAll('[data-oy-recommend]').length,teacher?39:0);
 const physics=document.querySelector('[data-oy-follow]');physics.onclick();
 assert(document.querySelector('.oy-modal input[value=WEB]'));
 assert.equal(document.querySelectorAll('.oy-modal input[name=channel]').length,2);
 document.querySelector('[data-oy-dismiss]').click();
 document.querySelector('[data-oy-tab="calendar"]').click();
 assert.equal(document.querySelectorAll('.oy-weekday').length,7);
 assert(document.querySelectorAll('.oy-day').length>=28);
 document.querySelector('[data-oy-mode=week]').click();assert.equal(document.querySelectorAll('.oy-day').length,7);
 document.querySelector('[data-oy-mode=agenda]').click();assert(document.querySelector('.oy-agenda'));
 document.querySelector('[data-oy-mode=month]').click();
 const item=document.querySelector('[data-oy-event]');if(item){item.click();assert(document.querySelector('.oy-event-detail'));assert(document.querySelector('.oy-action-link'));document.querySelector('[data-oy-dismiss]').click();}
 document.querySelector('[data-oy-tab="updates"]').click();assert(document.querySelector('.oy-updates'));
 document.querySelector('[data-oy-tab="mine"]').click();assert.equal(document.querySelectorAll('.oy-card').length,0);
 document.querySelector('[data-oy-close]').click();assert(!document.querySelector('.oy-shell'));
 assert(calls[0].url.startsWith('/api/'+(teacher?'teacher':'student')+'/olympiads'));
}
(async()=>{await check(true);await check(false);console.log('Teacher/student cards, escaping, subscriptions, month/week/agenda and event dialog: OK');})().catch(e=>{console.error(e);process.exitCode=1;});
