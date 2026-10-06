'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../web/teacher_payment_reversal.js'),'utf8');
(async()=>{
 for(const mode of ['cancel','confirm','failure']){
  const requests=[],alerts=[];let refresh=0,handlers=0;
  const root={},button={dataset:{reversePayment:'17'},disabled:false,isConnected:true,parentElement:root};
  const ctx={window:{},WeakMap,confirm:()=>mode!=='cancel',alert:x=>alerts.push(x),
   CustomEvent:class{constructor(type,data){this.type=type;this.detail=data.detail}},
   document:{addEventListener:(event,fn)=>{ctx.click=fn;handlers++},dispatchEvent(){}},
   fetch:async(url,opt)=>{requests.push({url,opt});return {ok:!(mode==='failure'&&opt.method==='POST'),
    json:async()=>opt.method==='POST'?(mode==='failure'?{error:'server_error'}:{status:'ok',payment_id:17}):{status:'PAID',name:'Test',amount:1600,lessons_count:1}}}};
  vm.createContext(ctx);vm.runInContext(source,ctx);vm.runInContext(source,ctx);
  assert.equal(handlers,1);
  ctx.window.AdeliaPaymentReversal.bind(root,()=>refresh++);
  assert(ctx.window.AdeliaPaymentReversal.button(17,'PAID').includes('data-reverse-payment'));
  assert.equal(ctx.window.AdeliaPaymentReversal.button(17,'REVERSED'),'');
  await ctx.click({target:{closest:()=>button}});
  assert.equal(button.disabled,false);
  assert.equal(requests.length,mode==='cancel'?1:2);
  assert.equal(refresh,mode==='confirm'?1:0);
  assert.equal(alerts.length,mode==='failure'?1:0);
  if(mode!=='cancel')assert.deepEqual(JSON.parse(requests[1].opt.body),{payment_id:17,confirmed:true,reason:'Ошибочное подтверждение оплаты'});
  console.log('PASS reversal UI '+mode);
 }
})();
