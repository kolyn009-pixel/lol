(()=>{'use strict';
const body=document.body;
const header=document.querySelector('.teacher-shell>main>header');
const aside=document.querySelector('.teacher-shell>aside');
if(!header||!aside)return;
let toggle=header.querySelector('[data-clean-menu]');
if(!toggle){
  toggle=document.createElement('button');
  toggle.type='button';
  toggle.className='clean-menu-toggle';
  toggle.dataset.cleanMenu='1';
  toggle.setAttribute('aria-label','Открыть меню');
  toggle.setAttribute('aria-expanded','false');
  toggle.textContent='☰';
  header.prepend(toggle);
}
function close(){body.classList.remove('menu-open');toggle.setAttribute('aria-expanded','false')}
function open(){body.classList.add('menu-open');toggle.setAttribute('aria-expanded','true')}
toggle.addEventListener('click',()=>body.classList.contains('menu-open')?close():open());
aside.addEventListener('click',e=>{if(e.target.closest('[data-view]'))close()});
document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
document.addEventListener('click',e=>{if(!body.classList.contains('menu-open'))return;if(e.target.closest('.teacher-shell>aside')||e.target.closest('[data-clean-menu]'))return;close()});
})();