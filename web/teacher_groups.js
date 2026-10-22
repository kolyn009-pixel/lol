(()=>{'use strict';
const q=(s,r=document)=>r.querySelector(s);const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
const api=async(path,opt={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Ошибка');return j};
const days=['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье'];
let sourceItems=[];let filter='ALL';let query='';let sort='NEWEST';

function recruitment(g){const s=String(g.recruitment_status||'').toUpperCase();if(s==='OPEN')return{key:'OPEN',label:'Набор открыт',cls:'is-open'};if(s==='WAITLIST')return{key:'WAITLIST',label:'Лист ожидания',cls:'is-wait'};return{key:'CLOSED',label:'Набор закрыт',cls:'is-closed'}}
function nextLabel(value){if(!value)return 'Не запланировано';try{return new Date(value).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch{return String(value)}}
function itemName(x){const g=x.group||x;return String(g.name||g.title||'Группа')}
function filtered(){
  let items=sourceItems.slice();
  if(filter!=='ALL')items=items.filter(x=>recruitment(x.group||x).key===filter);
  const needle=query.trim().toLocaleLowerCase('ru-RU');
  if(needle)items=items.filter(x=>{const g=x.group||x;return [g.name,g.title,g.subject,g.study_goal].some(v=>String(v||'').toLocaleLowerCase('ru-RU').includes(needle))});
  items.sort((a,b)=>{if(sort==='NAME')return itemName(a).localeCompare(itemName(b),'ru');const an=a.next_lesson?+new Date(a.next_lesson):Number.MAX_SAFE_INTEGER,bn=b.next_lesson?+new Date(b.next_lesson):Number.MAX_SAFE_INTEGER;if(sort==='NEXT')return an-bn;return itemName(a).localeCompare(itemName(b),'ru')});
  return items;
}
function stat(key){return sourceItems.filter(x=>recruitment(x.group||x).key===key).length}
function card(x){const g=x.group||x;const count=Number(x.member_count??g.member_count??0),cap=Number(g.max_members||8),status=recruitment(g);const subject=window.AdeliaStatusText?.(g.subject)||g.subject||'Физика';const goal=window.AdeliaStatusText?.(g.study_goal)||g.study_goal||'';return `<article class="groups-card-v2">
  <div class="groups-card-icon">${window.AdeliaAvatars?window.AdeliaAvatars.image(g,'group'):'👥'}</div>
  <div class="groups-card-main">
    <div class="groups-card-title"><h3>${esc(g.name||g.title||'Группа')}</h3><span class="groups-status-v2 ${status.cls}">${esc(status.label)}</span></div>
    <p>${esc(subject)}${goal?' · '+esc(goal):''}</p>
    <div class="groups-card-meta"><span>👤 ${count} из ${cap}</span><span>🗓 Ближайшее: ${esc(nextLabel(x.next_lesson))}</span></div>
  </div><div class="groups-card-actions"><button class="soft" type="button" data-group-chat="${g.id}">Чат группы</button><button class="soft" type="button" data-group-settings="${g.id}">Настроить группу</button></div>
</article>`}
function emptyFiltered(){return `<div class="groups-empty-v2"><div class="groups-empty-icon">⌕</div><h3>Ничего не найдено</h3><p>Измените фильтр или поисковый запрос.</p><button class="ghost" type="button" id="groupsResetFilters">Сбросить фильтры</button></div>`}
function emptyAll(){return `<div class="groups-empty-v2 is-first"><div class="groups-empty-icon">👥</div><h3>Пока нет учебных групп</h3><p>Создайте первую группу, задайте состав и постоянное время занятий.</p><button class="primary" type="button" id="groupCreateOpen">＋ Создать группу</button></div>`}
function form(){return `<form class="v4-form" id="groupCreateForm"><div class="v4-form-head"><div><span class="v4-kicker">Новая группа</span><h2>Создать групповое занятие</h2><p>Группа появится в расписании и будет доступна для набора.</p></div><button class="ghost" type="button" id="groupCreateClose">Закрыть</button></div><div class="v4-form-grid"><label><span>Название</span><input name="name" required placeholder="Физика · ОГЭ"></label><label><span>Предмет</span><select name="subject"><option value="PHYSICS">Физика</option><option value="CHEMISTRY">Химия</option><option value="MATH">Математика</option></select></label><label><span>Цель</span><select name="study_goal"><option value="SCHOOL">Школьная программа</option><option value="OGE">ОГЭ</option><option value="EGE">ЕГЭ</option><option value="OLYMPIAD">Олимпиада</option></select></label><label><span>Цена за занятие, ₽</span><input name="price_per_lesson" type="number" min="0" step="50" value="0"></label><label><span>Максимум учеников</span><input name="max_members" type="number" min="2" max="30" value="8"></label><label><span>Минимум для проведения</span><input name="min_attendees" type="number" min="1" max="30" value="2"></label><label><span>День недели</span><select name="weekday">${days.map((d,i)=>`<option value="${i}">${d}</option>`).join('')}</select></label><label><span>Время</span><input name="start_time" type="time" required value="18:00"></label><label><span>Длительность</span><select name="duration_minutes"><option value="60">60 минут</option><option value="90">90 минут</option><option value="120">120 минут</option></select></label><label><span>Первое занятие</span><input name="first_lesson_at" type="datetime-local"></label><label class="v4-span-2"><span>Ссылка на доску</span><input name="board_url" type="url" placeholder="https://..."></label><label class="v4-span-2"><span>Описание</span><textarea name="description" rows="3" placeholder="Для кого группа и что будем изучать"></textarea></label></div><div class="v4-form-actions"><span id="groupCreateState"></span><button class="primary" type="submit">Создать группу</button></div></form>`}
function bindToolbar(){
  document.querySelectorAll('[data-group-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.groupFilter;paintList()});
  const input=q('#groupsSearch');if(input)input.oninput=()=>{query=input.value;paintList()};
  const select=q('#groupsSort');if(select)select.onchange=()=>{sort=select.value;paintList()};
  const open=()=>{q('#groupFormHost').innerHTML=form();q('#groupCreateClose').onclick=()=>q('#groupFormHost').innerHTML='';q('#groupCreateForm').onsubmit=create};
  q('#groupCreateTop')&&(q('#groupCreateTop').onclick=open);q('#groupCreateOpen')&&(q('#groupCreateOpen').onclick=open);
}
function paintList(){const host=q('#groupsList');if(!host)return;document.querySelectorAll('[data-group-filter]').forEach(b=>b.classList.toggle('active',b.dataset.groupFilter===filter));const items=filtered();host.innerHTML=items.length?items.map(card).join(''):(sourceItems.length?emptyFiltered():emptyAll());q('#groupCreateOpen')&&(q('#groupCreateOpen').onclick=()=>q('#groupCreateTop')?.click());q('#groupsResetFilters')&&(q('#groupsResetFilters').onclick=()=>{filter='ALL';query='';const input=q('#groupsSearch');if(input)input.value='';paintList()})}
async function render(){const app=q('#app'),title=q('#title');if(title)title.textContent='Группы';app.innerHTML='<section class="loading">Загружаю группы…</section>';try{const d=await api('/teacher/groups');sourceItems=d.items||[];app.innerHTML=`<section class="groups-workspace-v2">
  <div class="groups-top-v2"><div><span class="workspace-kicker-v2">Рабочее пространство</span><h2>Группы</h2><p>Управление групповыми занятиями, составом и расписанием.</p></div><button class="primary groups-create-v2" id="groupCreateTop">＋ Создать группу</button></div>
  <div class="groups-toolbar-v2">
    <div class="groups-filters-v2">
      <button data-group-filter="ALL" class="active">Все <b>${sourceItems.length}</b></button>
      <button data-group-filter="OPEN"><i class="dot is-open"></i>Набор открыт <b>${stat('OPEN')}</b></button>
      <button data-group-filter="WAITLIST"><i class="dot is-wait"></i>Ожидание <b>${stat('WAITLIST')}</b></button>
      <button data-group-filter="CLOSED"><i class="dot is-closed"></i>Набор закрыт <b>${stat('CLOSED')}</b></button>
    </div>
    <div class="groups-tools-v2"><input id="groupsSearch" type="search" placeholder="Поиск групп…"><select id="groupsSort"><option value="NAME">По названию</option><option value="NEXT">По ближайшему занятию</option></select></div>
  </div>
  <div class="groups-list-v2" id="groupsList"></div>
  <div id="groupFormHost"></div>
</section>`;bindToolbar();paintList()}catch(e){app.innerHTML=`<div class="error">Не удалось загрузить группы: ${esc(e.message)}</div>`}}
async function create(ev){ev.preventDefault();const f=ev.currentTarget,s=q('#groupCreateState');const data=Object.fromEntries(new FormData(f).entries());['price_per_lesson','max_members','min_attendees','weekday','duration_minutes'].forEach(k=>data[k]=Number(data[k]||0));s.textContent='Создаю…';try{await api('/teacher/group/create',{method:'POST',body:JSON.stringify(data)});await render()}catch(e){s.textContent='Ошибка: '+e.message}}
window.teacherGroups=render;
document.addEventListener('click',e=>{const b=e.target.closest('[data-view="groups"]');if(!b||b.dataset.cleanProxy==='1')return;e.preventDefault();e.stopImmediatePropagation();document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x===b));render()},true);
})();
