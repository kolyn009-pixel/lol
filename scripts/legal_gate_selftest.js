'use strict';
const assert=require('assert'),vm=require('vm'),fs=require('fs'),path=require('path');
const code=fs.readFileSync(path.join(__dirname,'../web/parent/legal_gate.js'),'utf8');
(async()=>{
 for(const [url,status,error,expected] of [
  ['/api/parent/dashboard',428,'legal_acceptance_required',true],
  ['/api/payments/robokassa/checkout',428,'legal_acceptance_required',true],
  ['/api/parent/dashboard',200,'',false],
  ['/api/parent/dashboard',428,'other_error',false],
  ['https://external.test/api/parent/dashboard',428,'legal_acceptance_required',false],
  ['/app/parent/',428,'legal_acceptance_required',false]
 ]) {
  let target=null,calls=0;
  const context={URL,location:{href:'https://adelia.test/app/parent/',origin:'https://adelia.test',replace:x=>target=x},window:{fetch:async()=>{calls++;return new Response(JSON.stringify({error}),{status});}}};
  vm.runInNewContext(code,context);vm.runInNewContext(code,context);
  const response=await context.window.fetch(url);
  assert.equal(calls,1);assert.equal(response.status,status);assert.equal(Boolean(target),expected);
  assert.deepEqual(await response.json(),{error}); // The caller's body stays readable.
 }
 console.log('LEGAL_GATE_CLIENT=PASS');
})().catch(e=>{console.error(e);process.exit(1);});
