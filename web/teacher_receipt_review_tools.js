(function(){
'use strict';
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>n==null?'Не распознана':new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(n/100);
async function api(path,body){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),65000);try{const r=await fetch('/api/teacher/finance/receipt/'+path,{credentials:'same-origin',signal:controller.signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const d=await r.json();if(!r.ok)throw Error(d.error||'Не удалось выполнить запрос');return d}finally{clearTimeout(timer)}}
function refresh(root){window.teacherReceipts?.(document.querySelector('#receiptStatus')?.value||'WAITING',root)}
async function open(card){
 const present=card.querySelector('.rr-panel');if(present){present.hidden=!present.hidden;return}
 const panel=document.createElement('section');panel.className='rr-panel';panel.innerHTML='<p role="status">Загружаю данные платежа…</p>';card.append(panel);
 try{
  const pid=Number(card.dataset.paymentId),d=await api('details?payment_id='+pid),waiting=!['PAID','REVERSED'].includes(d.status);
  panel.innerHTML=`<h4>Проверка и дата оплаты</h4><p class="rr-muted">Дата оплаты — когда деньги поступили. Время проверки сохраняется отдельно.</p>${d.confirmed_at?`<p>Подтверждено: ${E(d.confirmed_at)}</p>`:''}<label>Дата фактической оплаты<input class="rr-date" type="date" max="${E(d.today)}" value="${E(d.paid_on||d.today)}" ${waiting?'':'disabled'} required></label>${d.lessons.length?`<p class="rr-muted">Связанные занятия: ${d.lessons.map(l=>`#${E(l.id)} · ${E(l.start_time)}`).join('; ')}</p>`:'<p class="rr-muted">Оплата пакета: начисление занятий выполняется по условиям этого платежа.</p>'}<div class="rr-inspection" role="status">Читаю чек…</div>${waiting?'<label class="rr-check"><input class="rr-bank" type="checkbox">Я проверил зачисление денег в своём банке</label><label>Комментарий к проверке<textarea class="rr-note" maxlength="1000" rows="2" placeholder="Если есть несоответствия, объясните причину подтверждения"></textarea></label><button type="button" class="primary rr-approve" disabled>Подтвердить оплату</button>':''}<p class="rr-state" role="status"></p>`;
  const input=panel.querySelector('.rr-date');input.oninput=()=>input.dataset.edited='1';
  const inspect=panel.querySelector('.rr-inspection');const rid=d.receipts[0]?.id;
  if(!rid)inspect.textContent='Файл чека не найден. Проверьте перевод вручную.';
  else try{
   const r=await api('inspect',{receipt_id:rid});
   const status={SUCCESS_TEXT:'В тексте указан успешный перевод',FAILED:'В тексте есть отказ / отмена',PENDING:'В тексте указано ожидание',UNKNOWN:'Статус перевода не распознан'};
   inspect.innerHTML=`<dl><div><dt>Сумма в чеке</dt><dd>${E(money(r.amount_kopeks))}</dd></div><div><dt>Ожидаемая сумма</dt><dd>${E(money(r.expected_kopeks))}</dd></div><div><dt>Получатель</dt><dd>${E(r.recipient||'Не распознан')}</dd></div><div><dt>Дата в чеке</dt><dd>${E(r.paid_on||'Не распознана')}</dd></div><div><dt>Статус в тексте</dt><dd>${E(status[r.transfer_status]||'Не распознан')}</dd></div></dl>${r.method==='OCR_UNAVAILABLE'?'<p>Распознавание изображений ещё не установлено на сервере.</p>':''}<ul>${r.warnings.map(x=>`<li>${E(x)}</li>`).join('')}</ul>${r.duplicates?.length?`<p>Другие платежи с таким файлом: ${r.duplicates.map(x=>'#'+E(x.payment_id)).join(', ')}</p>`:''}<p class="rr-muted">Распознавание не подтверждает подлинность чека или поступление денег.</p>${r.text_excerpt?`<details><summary>Распознанный текст</summary><pre>${E(r.text_excerpt)}</pre></details>`:''}`;
   if(waiting&&r.paid_on&&r.paid_on<=d.today&&!input.dataset.edited)input.value=r.paid_on;
  }catch(e){inspect.textContent=(e.name==='AbortError'?'Распознавание заняло слишком много времени.':e.message)+' Можно проверить файл и сумму вручную.'}
  const button=panel.querySelector('.rr-approve');
  if(button){button.disabled=false;button.onclick=async()=>{
   const state=panel.querySelector('.rr-state'),bank=panel.querySelector('.rr-bank');state.textContent='';
   if(!input.checkValidity()){input.reportValidity();return}if(!bank.checked){state.textContent='Сначала проверьте зачисление денег в банке.';bank.focus();return}
   button.disabled=true;
   try{await api('review',{payment_id:pid,action:'APPROVE',paid_on:input.value,note:panel.querySelector('.rr-note').value,acknowledged:true});refresh(card.closest('#receiptGrid')?.parentElement)}
   catch(e){state.textContent=e.name==='AbortError'?'Нет ответа сервера. Обновите список перед повторным подтверждением.':e.message;button.disabled=false}
  };}
 }catch(e){panel.innerHTML=`<p class="rr-state">${E(e.message)}</p>`}
}
function decorate(){document.querySelectorAll('.receipt-card[data-payment-id]').forEach(card=>{if(card.dataset.receiptTools)return;card.dataset.receiptTools='1';const b=document.createElement('button');b.type='button';b.className='ghost';b.dataset.receiptDetails='1';b.textContent='Проверка и дата оплаты';card.querySelector('.finance-actions')?.append(b)})}
document.addEventListener('click',e=>{const button=e.target.closest('[data-receipt-action="APPROVE"],[data-receipt-details]');if(!button)return;const card=button.closest('.receipt-card');if(!card)return;e.preventDefault();e.stopImmediatePropagation();open(card)},true);
const observer=new MutationObserver(decorate);observer.observe(document.body,{childList:true,subtree:true});decorate();
})();
