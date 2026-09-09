(function(){
const money=n=>new Intl.NumberFormat('ru-RU').format(Number(n||0))+' ₽';
async function loadHomeFinance(){
 const app=document.querySelector('#app');
 if(!app||document.querySelector('#homeFinanceAnalytics'))return;
 try{
  const r=await fetch('/api/teacher/finance/calendar-analytics',{credentials:'same-origin'});
  if(!r.ok)return;
  const d=await r.json(),w=d.week,m=d.month;
  const box=document.createElement('section');box.id='homeFinanceAnalytics';box.className='panel home-finance';
  box.innerHTML=`<div class="home-finance-head"><div><span class="badge">Финансы</span><h2>Финансовая аналитика</h2></div><button class="ghost" data-view="finance">Подробнее →</button></div><div class="home-finance-period"><h3>Эта календарная неделя</h3><div class="finance-kpis home"><article><span>Ожидается за неделю</span><strong>${money(w.planned.amount)}</strong><small>${w.planned.lessons} занятий по расписанию</small></article><article><span>Уже отработано</span><strong>${money(w.worked.amount)}</strong><small>${w.worked.lessons} занятий</small></article><article><span>Осталось отработать</span><strong>${money(w.remaining.amount)}</strong><small>${w.remaining.lessons} занятий</small></article></div></div><div class="home-finance-period"><h3>Этот календарный месяц</h3><div class="finance-kpis home"><article><span>Ожидается за месяц</span><strong>${money(m.planned.amount)}</strong><small>${m.planned.lessons} занятий по расписанию</small></article><article><span>Уже отработано</span><strong>${money(m.worked.amount)}</strong><small>${m.worked.lessons} занятий</small></article><article><span>Осталось отработать</span><strong>${money(m.remaining.amount)}</strong><small>${m.remaining.lessons} занятий</small></article></div></div>`;
  const stats=app.querySelector('.stats');if(stats)stats.insertAdjacentElement('afterend',box);else app.prepend(box);
 }catch(_){/* finance widget must never break teacher home */}
}
function schedule(){setTimeout(()=>{const t=document.querySelector('#title');if(t&&t.textContent.trim()==='Сегодня')loadHomeFinance()},0)}
const observer=new MutationObserver(schedule);document.addEventListener('DOMContentLoaded',()=>{observer.observe(document.querySelector('#app')||document.body,{childList:true,subtree:true});schedule()});
})();