/* The parent home leads to the canonical child payment screen. */
(()=>{'use strict';
if(window.__adeliaParentNextStep)return;window.__adeliaParentNextStep=true;
const root=document.querySelector('#root');if(!root)return;
let sequence=0,last=0,jumpToPayment=false;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0))+' ₽';
const api=async path=>{const r=await fetch('/api'+path,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('unavailable');return r.json()};
function selected(d,hubs){
  const students=d.students||[];
  const pending=hubs.find(x=>x?.finance?.waiting_payment);
  if(pending){const p=pending.finance.waiting_payment,review=String(p.status||'').toUpperCase()==='RECEIPT_SENT';
    return{payment:true,student:pending.student?.id,title:review?'Перевод на проверке':'К оплате '+money(p.total_amount),detail:(pending.student?.name||'Ученик')+' · '+(review?'Вы сообщили об оплате. Преподаватель проверит поступление.':'Проверьте сумму и получателя перед переводом.'),label:review?'Посмотреть статус':'Открыть оплату'}
  }
  const payable=hubs.find(x=>x?.nearest_unpaid_lesson);
  if(payable?.weekly_quote)return{payment:true,student:payable.student?.id,title:'2 занятия · '+money(payable.weekly_quote.total_amount),detail:(payable.student?.name||'Ученик')+' · один перевод и один чек за два занятия.',label:'Оплатить 2 занятия'};
  if(payable)return{payment:true,student:payable.student?.id,title:'Занятие · '+money(payable.nearest_unpaid_lesson.price),detail:(payable.student?.name||'Ученик')+' · сумма зафиксируется при создании платежа.',label:'Перейти к оплате'};
  const next=(d.upcoming||[])[0];if(next)return{student:next.user_id||students[0]?.id,title:'Ближайшее занятие',detail:(next.name||'Ученик')+' · '+(next.start_time?new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(next.start_time)):'смотрите расписание'),label:'Открыть карточку'};
  return null;
}
function show(a){
  const main=root.querySelector('main.wrap');if(!main)return;
  let card=main.querySelector('.parent-focus');
  if(!a){card?.remove();return}
  if(!card){card=document.createElement('section');card.className='card parent-focus';main.prepend(card)}
  card.classList.add('parent-next-step');
  card.innerHTML='<span class="eyebrow">Следующий шаг</span><h2>'+esc(a.title)+'</h2><p>'+esc(a.detail)+'</p><button type="button">'+esc(a.label)+' →</button>';
  card.querySelector('button').onclick=()=>{jumpToPayment=!!a.payment;root.querySelector('.student-card[data-student="'+Number(a.student)+'"]')?.click()};
}
async function update(dashboard){
  if(root.querySelector('#back')||!root.querySelector('.student-card'))return;
  if(!dashboard&&Date.now()-last<3000)return;last=Date.now();const current=++sequence;try{
    const d=dashboard||await api('/parent/dashboard');
    const results=await Promise.allSettled((d.students||[]).map(x=>api('/parent/finance/hub?student_id='+encodeURIComponent(x.id))));
    if(current!==sequence||root.querySelector('#back'))return;
    const hubs=results.filter(x=>x.status==='fulfilled').map(x=>x.value);
    await Promise.allSettled(hubs.map(async hub=>{const tariffs=hub.finance?.tariffs||[];if(hub.finance?.waiting_payment||tariffs.length!==1)return;const t=tariffs[0],lessons=(hub.upcoming_lessons||[]).filter(l=>l.subject===t.subject&&l.study_goal===t.study_goal&&!['PAID','FREE','RESERVED_BALANCE','TRANSFERRED','WAIVED','COVERED'].includes(l.payment_status)).slice(0,2);if(lessons.length!==2||Date.parse(lessons[1].start_at)-Date.parse(lessons[0].start_at)>7*86400000)return;
      const r=await fetch('/api/parent/finance/package/quote',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_id:hub.student.id,selection_key:t.selection_key,lessons_count:2}),signal:AbortSignal.timeout(12000)});if(r.ok)hub.weekly_quote=await r.json()
    }));
    if(current!==sequence||root.querySelector('#back'))return;
    if(results.some(x=>x.status==='rejected'))return;
    show(selected(d,hubs));
  }catch{}
}
window.addEventListener('adelia:parent-render',e=>{sequence++;if(jumpToPayment&&root.querySelector('#back')){jumpToPayment=false;[...root.querySelectorAll('section')].find(s=>s.querySelector('h2')?.textContent.trim()==='Оплата')?.scrollIntoView({behavior:'smooth',block:'start'})}update(e.detail?.dashboard)});
setTimeout(update,700);
})();
