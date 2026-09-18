(()=>{'use strict';
const SPECIAL=new Set(['schedule','groups','homework','reviews','messages','formulas','finance','health','students','analytics']);
const handlers={
  schedule:()=>window.teacherSchedule?.(),
  groups:()=>window.teacherGroups?.(),
  homework:()=>window.teacherHomework?.(),
  reviews:()=>window.teacherReviews?.(),
  formulas:()=>window.teacherFormulas?.(),
  finance:()=>window.teacherFinance?.(),
  students:()=>window.teacherStudentsClean?.(),
  analytics:()=>window.teacherProgress?.()
};
function setActive(view){document.querySelectorAll('aside nav button[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));}
function closeMenu(){document.body.classList.remove('menu-open');}
function fail(view){const app=document.querySelector('#app');if(app)app.innerHTML=`<section class="error">Раздел «${view}» не загрузился. Обновите страницу и попробуйте ещё раз.</section>`;}
function proxy(view){const source=document.querySelector(`aside nav button[data-view="${view}"]`)||document.querySelector(`[data-view="${view}"]`);if(!source)return false;const clone=source.cloneNode(true);clone.hidden=true;clone.dataset.cleanProxy='1';document.body.appendChild(clone);try{clone.click();return true}finally{clone.remove();setActive(view);closeMenu();}}
function route(view){setActive(view);closeMenu();const fn=handlers[view];try{if(typeof fn==='function'){const result=fn();if(result&&typeof result.catch==='function')result.catch(()=>fail(view));return true}return proxy(view)}catch(_){fail(view);return true}}
document.addEventListener('click',e=>{const button=e.target.closest('[data-view]');if(!button||button.dataset.cleanProxy==='1')return;const view=button.dataset.view;if(!SPECIAL.has(view))return;e.preventDefault();e.stopImmediatePropagation();route(view)},true);
window.AdeliaTeacherRoute=route;
})();