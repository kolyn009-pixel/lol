(()=>{'use strict';
const SPECIAL=new Set(['schedule','groups','messages','formulas','finance','health']);
const handlers={
  schedule:()=>window.teacherSchedule?.(),
  groups:()=>window.teacherGroups?.(),
  messages:()=>window.teacherMessages?.(),
  formulas:()=>window.teacherFormulas?.(),
  finance:()=>window.teacherFinance?.(),
  health:()=>window.teacherHealth?.()
};
function setActive(view){document.querySelectorAll('aside nav button[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));}
function closeMenu(){document.body.classList.remove('menu-open');}
function fail(view){const app=document.querySelector('#app');if(app)app.innerHTML=`<section class="error">Раздел «${view}» не загрузился. Обновите страницу и попробуйте ещё раз.</section>`;}
function route(view){const fn=handlers[view];if(typeof fn!=='function')return false;setActive(view);closeMenu();try{const result=fn();if(result&&typeof result.catch==='function')result.catch(()=>fail(view));return true}catch(_){fail(view);return true}}
document.addEventListener('click',e=>{const button=e.target.closest('[data-view]');if(!button)return;const view=button.dataset.view;if(!SPECIAL.has(view))return;e.preventDefault();e.stopImmediatePropagation();route(view)},true);
window.AdeliaTeacherRoute=route;
})();