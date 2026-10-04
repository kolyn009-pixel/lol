'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/student_messenger_v2.js'),'utf8');
const window={StudentTime:{preference:{zone:'Europe/Moscow'}},addEventListener(){}};
vm.runInNewContext(source.replace(/\}\)\(\);\s*$/,'window.test={receipt,signature};})();'),{
 window,document:{querySelector:()=>null,addEventListener(){}},Intl,Date,console,
 fetch:async()=>({ok:true,json:async()=>({})}),setInterval(){},clearInterval(){}
});
const row={id:1,status:'READ',read_at:'2026-10-04T16:00:00+00:00'};
assert.match(window.test.receipt(row),/19:00/);
window.StudentTime.preference.zone='Europe/Samara';assert.match(window.test.receipt(row),/20:00/);
window.StudentTime.preference.zone='Asia/Tokyo';assert.match(window.test.receipt(row),/05.10.*01:00/);
assert.match(window.test.receipt({status:'SENT'}),/Отправлено/);
assert.match(window.test.receipt({status:'DELIVERED'}),/Доставлено/);
assert.notEqual(window.test.signature([{id:1,status:'SENT'}]),window.test.signature([{id:1,status:'DELIVERED'}]));
console.log('STUDENT_RECEIPTS_TIMEZONES=PASS');
