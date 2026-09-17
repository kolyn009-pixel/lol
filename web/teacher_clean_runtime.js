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

const style=document.createElement('style');
style.textContent=`
.teacher-quick-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-left:auto}
.teacher-quick-actions button{border:1px solid #e7e0ff;background:#fff;color:#44366e;border-radius:10px;padding:7px 10px;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.teacher-quick-actions button:hover{background:#f8f5ff;border-color:#cfc1ff}
.teacher-quick-actions .qa-warn{background:#fff9e9;border-color:#f1df9b;color:#765d12}
.teacher-quick-actions .qa-cancel{background:#fff5f5;border-color:#f3c7c7;color:#9e3030}
.teacher-quick-actions .qa-open{background:#6847f5;border-color:#6847f5;color:#fff}
@media(max-width:900px){.teacher-quick-actions{width:100%;margin:8px 0 0}.teacher-quick-actions button{flex:1 1 auto}.row:has(.teacher-quick-actions){flex-wrap:wrap}}
`;
document.head.append(style);

function clickView(view){const b=document.querySelector(`nav [data-view="${view}"]`);if(b)b.click()}
function enhanceToday(){
  const title=document.querySelector('#title');
  if(!title||title.textContent.trim()!=='Сегодня')return;
  document.querySelectorAll('#app .row').forEach(row=>{
    const lessonButton=row.querySelector('[data-lesson]');
    const studentButton=row.querySelector('[data-student]');
    if(!lessonButton||row.querySelector('.teacher-quick-actions'))return;
    const lessonId=lessonButton.dataset.lesson;
    const studentId=studentButton?.dataset.student||'';
    lessonButton.style.display='none';
    if(studentButton)studentButton.style.display='none';
    const actions=document.createElement('div');
    actions.className='teacher-quick-actions';
    actions.innerHTML=`<button type="button" class="qa-open" data-qa="open">Открыть</button><button type="button" data-qa="move">Перенести</button><button type="button" class="qa-warn" data-qa="warn">Предупредить</button><button type="button" class="qa-cancel" data-qa="cancel">Отменить</button>${studentId?'<button type="button" data-qa="student">Ученик</button>':''}`;
    actions.addEventListener('click',e=>{
      const b=e.target.closest('[data-qa]');if(!b)return;
      const action=b.dataset.qa;
      if(action==='open'){lessonButton.click();return}
      if(action==='student'&&studentButton){studentButton.click();return}
      if(action==='move'){
        sessionStorage.setItem('adelia_teacher_action',JSON.stringify({type:'reschedule',lesson_id:Number(lessonId),student_id:Number(studentId||0)}));
        lessonButton.click();return;
      }
      if(action==='warn'){
        sessionStorage.setItem('adelia_teacher_action',JSON.stringify({type:'warn',lesson_id:Number(lessonId),student_id:Number(studentId||0)}));
        clickView('messages');return;
      }
      if(action==='cancel'){
        sessionStorage.setItem('adelia_teacher_action',JSON.stringify({type:'cancel',lesson_id:Number(lessonId),student_id:Number(studentId||0)}));
        lessonButton.click();
      }
    });
    row.append(actions);
  });
}

const observer=new MutationObserver(()=>enhanceToday());
observer.observe(document.querySelector('#app'),{childList:true,subtree:true});
enhanceToday();
})();