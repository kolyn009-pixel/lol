(function(){
const money=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0))+' ₽';
const prepaidCard=p=>`<article class="finance-prepaid-kpi"><span>Уже оплачено ранее</span><strong>${money(p.amount)}</strong><small>${p.lessons} занятий этого периода уже были оплачены и учтены раньше</small></article>`;
const receivedCard=p=>`<article class="finance-received-kpi"><span>Получено и подтверждено</span><strong>${money(p.amount)}</strong><small>${p.payments} подтверждённых оплат за этот период</small></article>`;
async function loadHomeFinance(){
 const app=document.querySelector('#app');
 if(!app||document.querySelector('#homeFinanceAnalytics'))return;
 try{
  const r=await fetch('/api/teacher/finance/calendar-analytics',{credentials:'same-origin'});
  if(!r.ok)return;
  const d=await r.json(),w=d.week,m=d.month;
  const box=document.createElement('section');box.id='homeFinanceAnalytics';box.className='panel home-finance';
  box.innerHTML=`<div class="home-finance-head"><div><span class="badge">Финансы</span><h2>Финансовая аналитика</h2><p>Отдельно считаю стоимость работы и реальные деньги, которые были подтверждены по оплатам.</p></div><button class="ghost" data-view="finance">Подробнее →</button></div><div class="home-finance-period"><h3>Эта календарная неделя</h3><div class="finance-kpis home"><article><span>Стоимость недели</span><strong>${money(w.planned.amount)}</strong><small>${w.planned.lessons} занятий по расписанию</small></article>${receivedCard(w.received_confirmed)}<article><span>Уже отработано</span><strong>${money(w.worked.amount)}</strong><small>${w.worked.lessons} занятий</small></article><article><span>Осталось отработать</span><strong>${money(w.remaining.amount)}</strong><small>${w.remaining.lessons} занятий</small></article>${prepaidCard(w.already_paid_before_period)}</div>${w.remaining_already_prepaid.amount?`<div class="finance-prepaid-note">Из оставшихся занятий <b>${money(w.remaining_already_prepaid.amount)}</b> (${w.remaining_already_prepaid.lessons}) уже оплачены заранее — повторно как новое поступление они не считаются.</div>`:''}</div><div class="home-finance-period"><h3>Этот календарный месяц</h3><div class="finance-kpis home"><article><span>Стоимость месяца</span><strong>${money(m.planned.amount)}</strong><small>${m.planned.lessons} занятий по расписанию</small></article>${receivedCard(m.received_confirmed)}<article><span>Уже отработано</span><strong>${money(m.worked.amount)}</strong><small>${m.worked.lessons} занятий</small></article><article><span>Осталось отработать</span><strong>${money(m.remaining.amount)}</strong><small>${m.remaining.lessons} занятий</small></article>${prepaidCard(m.already_paid_before_period)}</div>${m.remaining_already_prepaid.amount?`<div class="finance-prepaid-note">Из оставшихся занятий <b>${money(m.remaining_already_prepaid.amount)}</b> (${m.remaining_already_prepaid.lessons}) уже оплачены заранее.</div>`:''}</div>`;
  const stats=app.querySelector('.stats');if(stats)stats.insertAdjacentElement('afterend',box);else app.prepend(box);
 }catch(_){/* finance widget must never break teacher home */}
}
function schedule(){setTimeout(()=>{const t=document.querySelector('#title');if(t&&t.textContent.trim()==='Сегодня')loadHomeFinance()},0)}
const observer=new MutationObserver(schedule);document.addEventListener('DOMContentLoaded',()=>{observer.observe(document.querySelector('#app')||document.body,{childList:true,subtree:true});schedule()});
})();