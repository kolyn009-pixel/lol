(function(){
  'use strict';
  const LABELS={PHYSICS:'Физика',CHEMISTRY:'Химия',MATH:'Математика',CONFIRMED:'Подтверждено',PENDING:'Ожидает подтверждения',SCHEDULED:'Запланировано',CANCELLED:'Отменено',COMPLETED:'Завершено',PAID:'Оплачено',UNPAID:'Не оплачено',WAITING:'Ожидает',APPROVED:'Подтверждено',REJECTED:'Отклонено',SUBMITTED:'Сдано',DONE:'Готово',ACTIVE:'Активно',INACTIVE:'Неактивно',EGE:'ЕГЭ',OGE:'ОГЭ',SCHOOL:'Школьная программа',OLYMPIAD:'Олимпиада'};
  function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n}
  function humanize(root){
    if(!root)return;
    const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];
    while(w.nextNode())nodes.push(w.currentNode);
    nodes.forEach(n=>{const p=n.parentElement;if(!p||['SCRIPT','STYLE','CODE','PRE','TEXTAREA'].includes(p.tagName))return;let v=n.nodeValue;Object.entries(LABELS).forEach(([a,b])=>{v=v.replace(new RegExp('\\b'+a+'\\b','g'),b)});if(v!==n.nodeValue)n.nodeValue=v});
  }
  function polishNav(){
    const nav=document.querySelector('.teacher-shell>aside nav');
    if(!nav||nav.dataset.adeliaPolished)return;
    nav.dataset.adeliaPolished='1';
    const brand=document.querySelector('.teacher-shell>aside .brand');
    if(brand&&!brand.querySelector('img')){const img=document.createElement('img');img.src='/app/assets/icons/adelia-icon.svg';img.alt='';img.width=34;img.height=34;brand.prepend(img)}
    [['dashboard','Основное'],['homework','Обучение'],['messages','Связь'],['health','Система']].forEach(([view,text])=>{const target=nav.querySelector('[data-view="'+view+'"]');if(!target)return;const label=el('div','adelia-nav-label',text);nav.insertBefore(label,target)});
    ['library','formulas','payments','finance','analytics'].forEach(view=>nav.querySelector('[data-view="'+view+'"]')?.classList.add('adelia-nav-secondary'));
    const first=nav.querySelector('.adelia-nav-secondary');
    if(first){const more=el('button','adelia-nav-more');more.type='button';more.innerHTML='<span>•••</span><span>Дополнительно</span>';more.addEventListener('click',()=>nav.classList.toggle('adelia-nav-expanded'));nav.insertBefore(more,first)}
  }
  function mount(){
    const header=document.querySelector('.teacher-shell>main>header');
    if(header&&!header.querySelector('.adelia-runtime-actions')){
      const actions=el('div','adelia-runtime-actions');
      const status=el('button','adelia-status-chip');status.type='button';status.innerHTML='<span class="adelia-status-dot"></span><span>Проверка сервера…</span>';
      status.addEventListener('click',()=>document.querySelector('[data-view="health"]')?.click());
      const install=el('button','adelia-install-teacher','Установить на компьютер');install.type='button';
      install.addEventListener('click',async()=>{const api=window.AdeliaPWA;if(api&&typeof api.install==='function'){const r=await api.install().catch(()=>null);if(r&&r.status==='manual')alert(r.message||'Добавьте Аделию на главный экран через меню браузера.');else if(r&&r.status==='unavailable')alert('На компьютере откройте Аделию в Chrome или Edge. На Mac в Safari используйте «Файл → Добавить в Dock».');return}alert('Для установки откройте Аделию в Chrome или Edge.');});
      actions.append(status,install);header.appendChild(actions);
      fetch('/api/health',{credentials:'same-origin',cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.json()}).then(()=>{status.classList.add('ok');status.querySelector('span:last-child').textContent='Сервер работает'}).catch(()=>{status.classList.add('bad');status.querySelector('span:last-child').textContent='Проблема с сервером'});
    }
    polishNav();humanize(document.body);
  }
  const observer=new MutationObserver(()=>humanize(document.querySelector('#app')));
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{mount();observer.observe(document.body,{childList:true,subtree:true})},{once:true});else{mount();observer.observe(document.body,{childList:true,subtree:true})}
})();
