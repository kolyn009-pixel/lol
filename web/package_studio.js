(()=>{'use strict';
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const lessons=n=>{const a=n%100,b=n%10;return a>=11&&a<=14?'занятий':b===1?'занятие':b>=2&&b<=4?'занятия':'занятий';};
const money=n=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:2}).format(n);
const tariffs={SCHOOL_PHYSICS_5_8:'Физика · 5–8 классы',SCHOOL_PHYSICS_9_11:'Физика · 9–11 классы',SCHOOL_CHEMISTRY_5_8:'Химия · 5–8 классы',SCHOOL_CHEMISTRY_9_11:'Химия · 9–11 классы',OGE_PHYSICS:'ОГЭ · физика',OGE_CHEMISTRY:'ОГЭ · химия',EGE_PHYSICS:'ЕГЭ · физика',OLYMPIAD_PHYSICS:'Олимпиадная физика',COLLEGE_PHYSICS:'Физика · колледж'};
let loadingRoot=null;
async function enhance(){
 const body=document.querySelector('#financeBody'),add=body?.querySelector('#finNewPackage');
 if(!add||body.querySelector('.package-studio')||loadingRoot===add)return;
 loadingRoot=add;
 try{
  const r=await fetch('/api/teacher/finance/packages',{credentials:'same-origin',cache:'no-store'});if(!r.ok)return;
  const d=await r.json();if(!add.isConnected||body.querySelector('#finNewPackage')!==add)return;
  const editButtons=new Map([...body.querySelectorAll('[data-package]')].map(b=>[b.dataset.package,b]));
  const studio=document.createElement('section');studio.className='package-studio';
  const items=d.items||[],active=items.filter(x=>Number(x.active)!==0).length;
  studio.innerHTML='<header class="ps-head"><div><span class="ps-eyebrow">Абонементы</span><h2>Больше занятий — понятнее условия</h2><p>Создавайте предложения для новых покупок. У уже купленных абонементов сохраняются прежние условия.</p></div><div class="ps-add"></div></header><div class="ps-summary"><span><b>'+items.length+'</b> шаблонов</span><span><b>'+active+'</b> активных</span><span><b>'+(items.length-active)+'</b> выключено</span></div><div class="ps-toolbar"><label>Поиск<input type="search" data-ps-search placeholder="Название или направление"></label><div class="ps-filters" role="group" aria-label="Статус абонементов"><button type="button" data-ps-filter="all" aria-pressed="true">Все</button><button type="button" data-ps-filter="active" aria-pressed="false">Активные</button><button type="button" data-ps-filter="off" aria-pressed="false">Выключенные</button></div></div><div class="ps-grid"></div><p class="ps-empty" hidden role="status">По этим условиям абонементов нет.</p>';
  studio.querySelector('.ps-add').append(add);const grid=studio.querySelector('.ps-grid');
  for(const p of items){const card=document.createElement('article');const fixed=p.fixed_total!==null&&p.fixed_total!==undefined&&p.fixed_total!=='';const enabled=Number(p.active)!==0;const count=Number(p.lessons_count)||0;card.className='ps-card'+(enabled?'':' ps-off');card.dataset.active=String(enabled);card.dataset.search=[p.title,tariffs[p.tariff_key]||'Любое направление'].join(' ').toLocaleLowerCase('ru');
   card.innerHTML='<div class="ps-card-top"><span class="ps-status">'+(enabled?'Доступен для покупки':'Выключен')+'</span><span class="ps-kind">'+(fixed?'Фиксированная цена':'По тарифу')+'</span></div><h3>'+E(p.title||'Абонемент')+'</h3><p class="ps-direction">'+E(p.tariff_key?(tariffs[p.tariff_key]||'Выбранный тариф'):'Любое направление · тариф ученика')+'</p><div class="ps-count"><strong>'+count+'</strong><span>'+lessons(count)+'<br>в абонементе</span></div><div class="ps-price"><span>'+(fixed?'Стоимость абонемента':'Скидка от тарифа')+'</span><b>'+E(fixed?money(Number(p.fixed_total)):Number(p.discount_percent||0)+'%')+'</b><small>'+E(fixed&&count>0?money(Number(p.fixed_total)/count)+' за занятие':'Итоговая стоимость зависит от тарифа ученика')+'</small></div><footer></footer>';
   const edit=editButtons.get(String(p.code));if(edit){edit.textContent='Настроить абонемент';card.querySelector('footer').append(edit);}else card.querySelector('footer').textContent='Для изменения обновите раздел.';
   grid.append(card);
  }
  body.replaceChildren(studio);let filter='all';const input=studio.querySelector('[data-ps-search]');
  function apply(){const q=input.value.toLocaleLowerCase('ru').trim();let shown=0;grid.querySelectorAll('.ps-card').forEach(c=>{const fits=(!q||c.dataset.search.includes(q))&&(filter==='all'||c.dataset.active===String(filter==='active'));c.hidden=!fits;if(fits)shown++;});studio.querySelector('.ps-empty').hidden=shown>0;}
  input.oninput=apply;studio.querySelectorAll('[data-ps-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.psFilter;studio.querySelectorAll('[data-ps-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));apply();});apply();
 }catch{}finally{if(loadingRoot===add)loadingRoot=null;}
}
function editor(){const modal=document.querySelector('#financeModal .finance-modal');if(!modal||!modal.querySelector('#pkgSave')||modal.classList.contains('ps-editor'))return;modal.classList.add('ps-editor');modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');const title=modal.querySelector('h2');if(title){title.id='psEditorTitle';modal.setAttribute('aria-labelledby',title.id);}const close=document.createElement('button');close.type='button';close.className='ps-close';close.setAttribute('aria-label','Закрыть редактор абонемента');close.textContent='×';close.onclick=()=>{document.querySelector('#financeModal').replaceChildren();document.querySelector('#finNewPackage')?.focus();};modal.prepend(close);const hint=document.createElement('p');hint.className='ps-editor-note';hint.textContent='Фиксированная сумма имеет приоритет над процентной скидкой. Изменения применяются только к будущим покупкам.';modal.querySelector('#pkgSave').before(hint);const code=modal.querySelector('#pkgCode');if(code)code.placeholder='Например: PHYSICS_8';}
let pending=false;function update(){if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;enhance();editor();});}new MutationObserver(update).observe(document.body,{childList:true,subtree:true});update();
document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelector('.ps-editor .ps-close')?.click();});
})();
