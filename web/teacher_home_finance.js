(function(){
const money=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0))+' ₽';
const prepaidCard=p=>`<article class="finance-prepaid-kpi"><span>Оплачено до периода</span><strong>${money(p.amount)}</strong><small>${p.lessons} занятий этого периода были оплачены раньше</small></article>`;
const receivedCard=p=>`<article class="finance-received-kpi"><span>Получено по чекам</span><strong>${money(p.amount)}</strong><small>${p.payments} подтверждённых оплат именно в этом периоде</small></article>`;
const expectedCard=p=>`<article class="finance-expected-kpi"><span>Ещё ожидается денег</span><strong>${money(p.amount)}</strong><small>${p.lessons} будущих неоплаченных занятий</small></article>`;
const workCard=(title,p,extra='')=>`<article><span>${title}</span><strong>${money(p.amount)}</strong><small>${p.lessons} занятий${extra}</small></article>`;
function period(title,p){return `<div class="home-finance-period"><div class="home-finance-period-head"><h3>${title}</h3><span>${p.planned.lessons} занятий · ${money(p.planned.amount)}</span></div><div class="finance-kpis home">${receivedCard(p.received_confirmed)}${expectedCard(p.expected_to_receive)}${workCard('Уже отработано',p.worked)}${workCard('Осталось отработать',p.remaining)}${prepaidCard(p.already_paid_before_period)}</div><div class="finance-period-notes">${p.future_already_paid.amount?`<div class="finance-prepaid-note"><b>${money(p.future_already_paid.amount)}</b> из будущей работы уже оплачено (${p.future_already_paid.lessons} зан.) и поэтому не входит в «ещё ожидается денег».</div>`:''}${p.remaining_already_prepaid.amount?`<div class="finance-prepaid-note">Из оставшихся занятий <b>${money(p.remaining_already_prepaid.amount)}</b> (${p.remaining_already_prepaid.lessons}) оплачены ещё до начала этого периода.</div>`:''}</div></div>`}
async function loadHomeFinance(){
 const app=document.querySelector('#app');
 if(!app||document.querySelector('#homeFinanceAnalytics'))return;
 try{
  const r=await fetch('/api/teacher/finance/calendar-analytics',{credentials:'same-origin'});if(!r.ok)return;
  const d=await r.json(),box=document.createElement('section');box.id='homeFinanceAnalytics';box.className='panel home-finance';
  box.innerHTML=`<div class="home-finance-head"><div><span class="badge">Финансы</span><h2>Финансовая аналитика</h2><p>Деньги и работа считаются отдельно: сколько подтверждено по чекам, сколько ещё ожидается и какая часть занятий уже была оплачена заранее.</p></div><button class="ghost" data-view="finance">Подробнее →</button></div>${period('Эта календарная неделя',d.week)}${period('Этот календарный месяц',d.month)}`;
  const stats=app.querySelector('.stats');if(stats)stats.insertAdjacentElement('afterend',box);else app.prepend(box);
 }catch(_){/* finance widget must never break teacher home */}
}
function schedule(){setTimeout(()=>{const t=document.querySelector('#title');if(t&&t.textContent.trim()==='Сегодня')loadHomeFinance()},0)}
const observer=new MutationObserver(schedule);document.addEventListener('DOMContentLoaded',()=>{observer.observe(document.querySelector('#app')||document.body,{childList:true,subtree:true});schedule()});
})();