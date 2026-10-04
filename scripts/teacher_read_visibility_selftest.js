'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/teacher_messages_stage10.js'),'utf8');
const list={scrollHeight:1000,scrollTop:900,clientHeight:100};
const document={hidden:false,querySelector:s=>s==='#msgHistory'?list:null,addEventListener(){}};
const window={addEventListener(){}};let calls=[],complete;
vm.runInNewContext(source.replace(/\}\)\(\);\s*$/,'window.test={state,acknowledgeRead};})();'),{
 window,document,Intl,Date,console,setInterval(){},clearInterval(){},
 fetch:(url,options)=>{calls.push(JSON.parse(options.body));return new Promise(resolve=>{complete=()=>resolve({ok:true,json:async()=>({read_at:'2026-10-04T16:00:00+00:00'})});});}
});
const {state,acknowledgeRead}=window.test;
(async()=>{
 state.visible=true;state.active={id:10,unread:1};state.renderedId=10;state.history=[{id:5,direction:'IN'}];
 document.hidden=true;await acknowledgeRead();assert.equal(calls.length,0);
 document.hidden=false;list.scrollTop=0;await acknowledgeRead();assert.equal(calls.length,0);
 list.scrollTop=900;state.renderedId=11;await acknowledgeRead();assert.equal(calls.length,0);
 state.renderedId=10;const pending=acknowledgeRead();
 assert.equal(calls[0].through_id,5);assert.equal(calls[0].conversation_id,10);
 state.history.push({id:6,direction:'IN'});complete();await pending;
 assert.equal(state.history[0].status,'READ');assert.equal(state.history[1].read_at,undefined);
 console.log('TEACHER_READ_VISIBLE_AND_BOUNDARY=PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
