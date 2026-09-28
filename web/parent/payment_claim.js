(()=>{'use strict';
let studentId=null,sequence=0;
const money=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0))+' ₽';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,opt={}){const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...opt});const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(data.error||'Не удалось выполнить запрос');return data}
function mount(){const back=document.querySelector('#back');if(!back||!studentId)return;
 const title=[...document.querySelectorAll('.wrap .section-title h2')].find(x=>x.textContent.trim()==='Оплата');
 const section=title?.closest('section');if(!section)return;
 let slot=section.querySelector('#parentPaymentClaim');if(!slot){slot=document.createElement('div');slot.id='parentPaymentClaim';section.insertBefore(slot,section.firstElementChild?.nextSibling||null)}
 const seq=++sequence;slot.innerHTML='<p class="muted">Загружаю оплату…</p>';
 api('/parent/finance/hub?student_id='+encodeURIComponent(studentId)).then(d=>{if(seq!==sequence||!slot.isConnected)return;draw(slot,d)}).catch(()=>{if(seq===sequence&&slot.isConnected)slot.innerHTML='<p class="error">Не удалось загрузить оплату. Обновите страницу.</p>'})
}
function draw(slot,d){const finance=d.finance||{},pending=finance.waiting_payment,lesson=d.nearest_unpaid_lesson;
 if(!pending&&!lesson){slot.innerHTML='<article class="card"><strong>Ближайшее занятие оплачено</strong><p class="muted">Когда появится новая оплата, она будет здесь.</p></article>';return}
 const amount=pending?.total_amount??lesson?.price;
 slot.innerHTML='<article class="card" style="display:grid;gap:12px;margin:12px 0 20px"><div><span class="eyebrow">К оплате</span><h3 style="font-size:27px;margin:6px 0">'+money(amount)+'</h3><p class="muted" style="margin:0">'+(pending?'Платёж #'+esc(pending.id):'Ближайшее занятие')+'</p></div><div data-payment-method></div><div data-payment-action></div><p class="muted" style="font-size:13px;margin:0">Аделия не проверяет банк автоматически. После перевода сообщите об оплате, а преподаватель сверит поступление.</p></article>';
 const action=slot.querySelector('[data-payment-action]'),method=slot.querySelector('[data-payment-method]');
 if(pending){method.textContent=finance.payment_method||'Реквизиты оплаты уточните у преподавателя.';method.style.whiteSpace='pre-line';
  if(String(pending.status).toUpperCase()==='RECEIPT_SENT'){action.textContent='Ожидает проверки преподавателем';return}
  api('/parent/finance/qr/status').then(q=>{if(!q.configured||!method.isConnected)return;const box=document.createElement('div');box.style.cssText='display:grid;gap:8px;margin:12px 0';box.innerHTML='<img src="/api/parent/finance/qr/image" alt="QR Сбера для оплаты преподавателю" style="width:min(100%,240px);aspect-ratio:1;object-fit:contain;border-radius:12px;border:1px solid #ddd"><small>QR Сбера: сканируйте, проверьте получателя и введите сумму, указанную выше.</small>';method.prepend(box)}).catch(()=>{});
  action.innerHTML='<button type="button" data-claim style="min-height:44px">Я оплатил</button>';
  action.querySelector('[data-claim]').onclick=async e=>{const b=e.currentTarget;b.disabled=true;b.textContent='Отправляю…';try{await api('/parent/finance/claim',{method:'POST',body:JSON.stringify({student_id:studentId,payment_id:pending.id})});mount()}catch(err){b.disabled=false;b.textContent='Я оплатил';action.insertAdjacentHTML('beforeend','<p class="error">'+esc(err.message)+'</p>')}}
 }else{method.textContent='Стоимость занятия рассчитана по тарифу ученика. Создайте оплату, чтобы зафиксировать точную сумму.';action.innerHTML='<button type="button" data-create style="min-height:44px">Перейти к оплате</button>';
  action.querySelector('[data-create]').onclick=async e=>{const b=e.currentTarget;b.disabled=true;b.textContent='Создаю платёж…';try{await api('/parent/finance/pay-nearest',{method:'POST',body:JSON.stringify({student_id:studentId})});mount()}catch(err){b.disabled=false;b.textContent='Перейти к оплате';action.insertAdjacentHTML('beforeend','<p class="error">'+esc(err.message)+'</p>')}}
 }
}
document.addEventListener('click',e=>{const card=e.target.closest?.('[data-student]');if(card)studentId=card.dataset.student;else if(e.target.closest?.('#back')){studentId=null;sequence++}},true);
window.addEventListener('adelia:parent-render',mount);
})();