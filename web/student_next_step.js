/* One current action for the student home screen, shared by PWA and Desktop. */
(()=>{'use strict';
if(window.__adeliaStudentNextStep)return;window.__adeliaStudentNextStep=true;
const root=document.querySelector('#content');if(!root)return;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let sequence=0,started=0;
const api=async path=>{const r=await fetch('/api'+path,{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw Error('unavailable');return r.json()};
const navigate=tab=>document.querySelector('.nav-item[data-tab="'+tab+'"]')?.click();
function isHome(){return !!root.querySelector('.welcome,.student2-hero')&&!!document.querySelector('.nav-item.active[data-tab="home"]')}
function choose(d,homework){
  const lesson=d.next_lesson||null,now=Date.now(),homeworkOpen=(homework.items||[]).filter(x=>['ASSIGNED','REVISION'].includes(String(x.status||'').toUpperCase()));
  const due=homeworkOpen.filter(x=>x.deadline&&Number.isFinite(Date.parse(x.deadline))).sort((a,b)=>Date.parse(a.deadline)-Date.parse(b.deadline))[0];
  if(lesson?.started_at&&!lesson.finished_at)return{eyebrow:'Идёт сейчас',title:'Занятие началось',detail:'Вернись к уроку одним нажатием.',label:'Открыть занятие',kind:'lesson',id:lesson.id};
  if(due&&Date.parse(due.deadline)<=now+48*3600000)return{eyebrow:'Следующий шаг',title:due.title||'Домашнее задание',detail:'Задание ждёт выполнения.',label:'Открыть ДЗ',kind:'homework'};
  if(Number(d.unread_messages||0)>0)return{eyebrow:'Новое сообщение',title:'Преподаватель написал тебе',detail:'Открой переписку, когда будет удобно.',label:'Прочитать',kind:'messages'};
  if(lesson){let when='';try{when=new Intl.DateTimeFormat('ru-RU',{timeZone:d.student?.timezone?.zone||'Europe/Moscow',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(lesson.start_at||lesson.start_time))}catch{}return{eyebrow:'Ближайший урок',title:'Урок '+(when||'в расписании'),detail:'Время по выбранному региону: '+(d.student?.timezone?.label||'Москва')+'.',label:'Открыть занятие',kind:'lesson',id:lesson.id}}
  if(homeworkOpen.length)return{eyebrow:'Следующий шаг',title:'ДЗ ждёт тебя',detail:homeworkOpen.length+' заданий в работе.',label:'Открыть ДЗ',kind:'homework'};
  if(Number(d.payments_waiting||0)>0)return{eyebrow:'Оплата',title:'Есть платёж в ожидании',detail:'Статус и сумма доступны в разделе оплаты.',label:'Посмотреть',kind:'payments'};
  return null;
}
function show(a){
  const hero=root.querySelector('.welcome,.student2-hero');if(!hero)return;
  let slot=root.querySelector('#studentNextStep');if(!a){slot?.remove();root.classList.remove('student-has-next-step');return}
  if(!slot){slot=document.createElement('section');slot.id='studentNextStep';slot.className='student-next-step';hero.after(slot)}
  slot.innerHTML='<div><small>'+esc(a.eyebrow)+'</small><h2>'+esc(a.title)+'</h2><p>'+esc(a.detail)+'</p></div><button type="button">'+esc(a.label)+' →</button>';
  root.classList.add('student-has-next-step');
  slot.querySelector('button').onclick=()=>{if(a.kind==='lesson'){if(window.adeliaDesktop?.desktop&&window.adeliaDesktop.openLesson)window.adeliaDesktop.openLesson(a.id);else location.href='/app/lesson/?id='+encodeURIComponent(a.id)}else navigate(a.kind)};
}
async function update(){
  if(!isHome())return;
  const current=++sequence;try{
    const [d,h]=await Promise.all([api('/student/dashboard'),api('/student/homework')]);
    if(current!==sequence||!isHome())return;show(choose(d,h));
  }catch{if(current===sequence)root.classList.remove('student-has-next-step')}
}
new MutationObserver(()=>{if(isHome()){if(!root.querySelector('#studentNextStep'))update()}else{sequence++;root.classList.remove('student-has-next-step')}}).observe(root,{childList:true});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&isHome())update()});
window.addEventListener('adelia:student-timezone-changed',()=>{if(isHome())update()});
setTimeout(update,1000);
})();