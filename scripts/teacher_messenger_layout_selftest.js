'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.join(__dirname,'..');
const nodes=new Map();let resolveHistory;
const document={querySelector:s=>nodes.get(s)||null,addEventListener(){}};
const window={addEventListener(){},innerHeight:800};
const source=fs.readFileSync(path.join(root,'web/teacher_messages_stage10.js'),'utf8');
const exportsCode='window.test={state,rememberDraft,restoreDraft,clearDraft,listHtml,history,fitMessenger};';
vm.runInNewContext(source.replace(/\}\)\(\);\s*$/,exportsCode+'})();'),{
 window,document,Intl,Date,Map,console,setInterval,clearInterval,
 fetch:()=>new Promise(resolve=>{resolveHistory=resolve;})
});
const t=window.test;
const input={value:'Черновик первого диалога'},label={textContent:''};
nodes.set('#msgText',input);nodes.set('#msgFileName',label);
t.state.active={id:1};t.state.renderedId=1;
const file={name:'homework.pdf'};t.state.drafts.set(1,{file});
t.rememberDraft();t.state.active={id:2};t.restoreDraft();
assert.equal(input.value,'');assert.equal(label.textContent,'');
input.value='Второй диалог';t.state.renderedId=2;t.rememberDraft();
t.state.active={id:1};t.restoreDraft();
assert.equal(input.value,'Черновик первого диалога');assert.equal(label.textContent,'homework.pdf');
t.clearDraft();assert.equal(t.state.drafts.has(1),false);assert.equal(t.state.drafts.get(2).text,'Второй диалог');
t.state.items=[{id:1,name:'<test>',unread:2},{id:2,name:'Другой',unread:5}];
let html=t.listHtml();assert.match(html,/7 непрочитанных/);assert.match(html,/<i>7<\/i>/);assert.match(html,/&lt;test&gt;/);
t.state.items[0].unread=0;html=t.listHtml();assert.match(html,/5 непрочитанных/);assert.match(html,/<i>5<\/i>/);
let height;nodes.set('.msg-shell',{getBoundingClientRect:()=>({top:140}),style:{setProperty:(key,value)=>{height=value;}}});
t.fitMessenger();assert.equal(height,'644px');
(async()=>{
 t.state.visible=true;t.state.active={id:1};t.state.history=[];
 const pending=t.history();t.state.active={id:2};
 resolveHistory({ok:true,json:async()=>({items:[{body:'чужой диалог'}]})});
 await pending;assert.equal(t.state.history.length,0);
 console.log('TEACHER_MESSENGER_DRAFTS_COUNTS_RACE=PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
