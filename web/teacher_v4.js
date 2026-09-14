(()=>{'use strict';
const $=(s,r=document)=>r.querySelector(s);
function statusText(v){const m={PHYSICS:'Физика',CHEMISTRY:'Химия',MATH:'Математика',CONFIRMED:'Подтверждено',PENDING:'Ожидает',SCHEDULED:'Запланировано',CANCELLED:'Отменено',COMPLETED:'Завершено',PAID:'Оплачено',UNPAID:'Не оплачено',AWAITING_PAYMENT:'Ожидает оплату',WAITING:'Ожидает',APPROVED:'Подтверждено',REJECTED:'Отклонено',SUBMITTED:'Сдано',DONE:'Готово',ACTIVE:'Активно',INACTIVE:'Неактивно',EGE:'ЕГЭ',OGE:'ОГЭ',SCHOOL:'Школьная программа',OLYMPIAD:'Олимпиада'};return m[v]||v}
window.AdeliaStatusText=statusText;
function installButton(btn){btn.addEventListener('click',async()=>{try{const api=window.AdeliaPWA;if(api&&typeof api.install==='function'){const r=await api.install();if(r?.status==='manual')alert(r.message||'Используйте пункт установки приложения в меню браузера.');else if(r?.status==='unavailable')alert('На Mac используйте Safari: Файл → Добавить в Dock, либо Chrome/Edge: Установить приложение.');return}alert('Откройте Аделию в Chrome/Edge или Safari и выберите установку приложения.')}catch(e){alert('Не удалось открыть установку. Обновите страницу и повторите.')}})}
async function health(btn){try{const r=await fetch('/api/health',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw new Error();await r.json().catch(()=>({}));btn.classList.add('ok');btn.classList.remove('bad');$('.v4-status-text',btn).textContent='Аделия работает'}catch(e){btn.classList.add('bad');btn.classList.remove('ok');$('.v4-status-text',btn).textContent='Есть проблема'}}
function boot(){
  const header=$('.teacher-shell>main>header'),aside=$('.teacher-shell>aside');if(!header||!aside)return;
  const headLeft=header.firstElementChild;if(headLeft&&!headLeft.classList.contains('header-title-wrap')){headLeft.classList.add('header-title-wrap');const menu=document.createElement('button');menu.type='button';menu.className='v4-mobile-menu';menu.setAttribute('aria-label','Открыть меню');menu.textContent='☰';menu.onclick=()=>document.body.classList.toggle('v4-menu-open');headLeft.prepend(menu)}
  const actions=$('.header-actions',header);if(actions&&!$('.v4-status',actions)){
    const s=document.createElement('button');s.type='button';s.className='v4-status';s.innerHTML='<span class="v4-dot"></span><span class="v4-status-text">Проверяю…</span>';s.onclick=()=>document.querySelector('[data-view="health"]')?.click();
    const i=document.createElement('button');i.type='button';i.className='v4-install';i.textContent='Установить';installButton(i);actions.prepend(s,i);health(s);setInterval(()=>health(s),60000)
  }
  aside.addEventListener('click',e=>{if(e.target.closest('button'))document.body.classList.remove('v4-menu-open')});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')document.body.classList.remove('v4-menu-open')});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
