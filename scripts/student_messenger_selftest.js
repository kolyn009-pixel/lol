'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

async function main(){
  const root=path.resolve(__dirname,'..');
  const items=[{id:1,direction:'OUT',text:'Первое сообщение',created_at:'2026-09-28T10:00:00Z'}];
  const draft={value:'Мой черновик'};
  const list={innerHTML:'',scrollHeight:200,scrollTop:100,clientHeight:100};
  const state={textContent:'',dataset:{}};
  const document={
    hidden:false,
    querySelector(selector){
      if(selector==='#studentChatHistory')return list;
      if(selector==='#studentChatState')return state;
      if(selector==='#studentChatText')return draft;
      return null;
    },
    addEventListener(){},
  };
  const window={};
  const context={
    window,document,console,
    fetch:async url=>({ok:true,json:async()=>url.includes('/student/messages')?{items:items.slice()}:{unread_messages:0}}),
    setInterval:()=>1,clearInterval:()=>{},
    Intl,Date,JSON,Number,String,
  };
  vm.runInNewContext(fs.readFileSync(path.join(root,'web/student_messenger_v2.js'),'utf8'),context);
  const inbox=window.AdeliaStudentMessenger;
  assert.match(await inbox.screen(),/Переписка с преподавателем сохраняется в Аделии/);
  items.push({id:2,direction:'IN',text:'Новый вопрос',created_at:'2026-09-28T10:01:00Z'});
  await inbox.refresh();
  assert.match(list.innerHTML,/Новый вопрос/);
  assert.equal(draft.value,'Мой черновик');
  assert.match(fs.readFileSync(path.join(root,'web/app.js'),'utf8'),/AdeliaStudentMessenger\?\.screen\|\|messages/);
  console.log('STUDENT_MESSENGER=PASS');
}
main().catch(error=>{console.error(error);process.exitCode=1});
