(()=>{'use strict';
if(window.AdeliaPaymentReversal)return;
const refreshers=new WeakMap();
const errors={provider_payment_requires_refund:'Это подтверждённый платёж через кассу. Для него нужен возврат через платёжный сервис.',payment_not_paid:'Оплата уже изменилась. Обновите страницу.',payment_not_found:'Платёж не найден.',bonus_payment_not_reversible:'Бонусы исправляются через управление балансом.',confirmation_required:'Подтвердите отмену.',payment_package_missing:'У платежа нет связанного начисления. Нужна проверка истории.',server_error:'Не удалось выполнить отмену. Обновите страницу и проверьте статус перед повторной попыткой.'};
async function J(path,opt={}){const r=await fetch('/api/teacher/finance/payment/'+path,{credentials:'same-origin',...opt}),j=await r.json().catch(()=>({}));if(!r.ok)throw Error(errors[j.error]||j.error||'Не удалось исправить оплату');return j}
function button(id,status){const pid=Number(id);return status==='PAID'&&Number.isInteger(pid)&&pid>0?'<button type="button" class="ghost fin-reversal" data-reverse-payment="'+pid+'">Отменить подтверждение</button>':''}
function bind(root,refresh){if(root)refreshers.set(root,refresh)}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-reverse-payment]');if(!b||b.disabled)return;
 const pid=Number(b.dataset.reversePayment);if(!Number.isInteger(pid)||pid<=0)return;
 b.disabled=true;
 try{
  const p=await J('reversal-preview?payment_id='+pid);
  if(p.status!=='REVERSED'&&!confirm('Отменить ошибочное подтверждение?\n\n'+p.name+' · '+p.amount+' ₽\nПлатёж #'+pid+'\nСвязанных занятий: '+p.lessons_count+'\n\nОшибочное начисление будет убрано. Занятия сохранятся со статусом «Ожидает оплаты». История сохранится. Деньги через банк не возвращаются.'))return;
  const result=await J('reverse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({payment_id:pid,confirmed:true,reason:'Ошибочное подтверждение оплаты'})});
  let root=b;while(root&&!refreshers.has(root))root=root.parentElement;
  if(root){try{await refreshers.get(root)()}catch(_){alert('Подтверждение отменено. Обновите страницу, чтобы увидеть текущий статус.')}}else{b.replaceWith(document.createTextNode('Подтверждение отменено'))}
  document.dispatchEvent(new CustomEvent('adelia:payment-reversed',{detail:result}));
 }catch(err){alert(err.message)}finally{if(b.isConnected)b.disabled=false}
});
window.AdeliaPaymentReversal=Object.freeze({button,bind});
})();
