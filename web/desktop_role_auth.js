(()=>{
'use strict';
if(!window.adeliaDesktop?.desktop)return;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
const api=async(path,opt={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok){const e=new Error(j.error||'request_failed');e.status=r.status;throw e}return j};
let mode='choose';
function host(){return document.querySelector('#content')||document.querySelector('main')||document.body}
function authResultText(e){const x=String(e?.message||'');if(x==='expired')return 'Код истёк. Получите новый код в админском TutorBot.';if(x==='too_many_attempts')return 'Слишком много попыток. Подождите минуту.';return 'Код не подошёл. Получите новый код в админском TutorBot и попробуйте ещё раз.'}
async function currentSession(){try{return (await api('/auth/me')).session||null}catch{return null}}
function choose(){
 mode='choose';window.__adeliaAuthV2=false;document.body.classList.add('adelia-auth-screen','desktop-role-auth');
 host().innerHTML=`<section class="desktop-role-card"><div class="desktop-role-brand"><div class="desktop-role-logo">💜</div><div><span>Аделия для Windows</span><h2>Кто входит?</h2><p>Приложение откроет нужное рабочее пространство и запомнит сессию на этом компьютере.</p></div></div><div class="desktop-role-grid"><button type="button" id="desktopTeacherLogin"><i>👨‍🏫</i><b>Я преподаватель</b><span>Кабинет преподавателя, ученики, занятия, ДЗ и финансы</span><em>Войти по защищённому коду →</em></button><button type="button" id="desktopStudentLogin"><i>🎓</i><b>Я ученик</b><span>Занятия, домашние задания, чат, группы и оплата</span><em>Войти в свой кабинет →</em></button></div><small class="desktop-role-note">Аделия не запрашивает доступ к личным файлам, истории браузера, контактам или другим программам.</small></section>`;
 document.querySelector('#desktopTeacherLogin').onclick=teacherCode;
 document.querySelector('#desktopStudentLogin').onclick=studentLogin;
}
function teacherCode(message=''){
 mode='teacher';document.body.classList.add('adelia-auth-screen','desktop-role-auth');
 host().innerHTML=`<section class="form-card auth-card adelia-auth-v2 desktop-teacher-auth"><button type="button" class="desktop-auth-back" id="desktopRoleBack">← Выбор роли</button><span class="status">👨‍🏫 Кабинет преподавателя</span><h2>Вход преподавателя</h2><p>Получите одноразовый 6-значный код в вашем админском TutorBot. Код действует ограниченное время и после входа больше не используется.</p><label>Код преподавателя</label><input class="code-input" id="desktopTeacherCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000"><button class="form-primary" id="desktopTeacherSubmit">Войти в кабинет преподавателя</button><div id="desktopTeacherResult" class="form-error">${esc(message)}</div><div class="desktop-auth-security">🔒 Сессия хранится только в защищённом профиле приложения. Пароль от Telegram приложению не нужен.</div></section>`;
 document.querySelector('#desktopRoleBack').onclick=choose;
 document.querySelector('#desktopTeacherSubmit').onclick=submitTeacher;
 document.querySelector('#desktopTeacherCode').addEventListener('keydown',e=>{if(e.key==='Enter')submitTeacher()});
 setTimeout(()=>document.querySelector('#desktopTeacherCode')?.focus(),0);
}
async function submitTeacher(){
 const input=document.querySelector('#desktopTeacherCode'),btn=document.querySelector('#desktopTeacherSubmit'),out=document.querySelector('#desktopTeacherResult');
 const code=(input?.value||'').replace(/\D/g,'');if(code.length!==6){out.textContent='Введите 6 цифр из админского TutorBot.';return}
 btn.disabled=true;out.textContent='Проверяю код…';
 try{await api('/auth/teacher/code',{method:'POST',body:JSON.stringify({code})});location.replace('/teacher/')}catch(e){out.textContent=authResultText(e);btn.disabled=false;input?.select()}
}
function studentLogin(){
 mode='student';window.__adeliaAuthV2=false;window.authMode='password';document.body.classList.remove('desktop-role-auth');
 if(typeof window.render==='function')window.render('studentLogin');else location.reload();
 const wait=setInterval(()=>{const card=document.querySelector('.auth-card');if(!card)return;clearInterval(wait);const back=document.createElement('button');back.type='button';back.className='mini-btn desktop-student-role-back';back.textContent='← Другой тип аккаунта';back.onclick=choose;card.appendChild(back)},100);
 setTimeout(()=>clearInterval(wait),3000);
}
async function boot(){
 const session=await currentSession();
 if(session?.role==='teacher'){location.replace('/teacher/');return}
 if(session?.role==='student'){document.body.classList.remove('desktop-role-auth');return}
 choose();
}
function interceptStudentAuth(){
 if(mode!=='choose'&&mode!=='teacher')return;
 const card=document.querySelector('.auth-card');if(card&&!card.closest('.desktop-role-card')&&!card.classList.contains('desktop-teacher-auth'))choose();
}
new MutationObserver(interceptStudentAuth).observe(document.documentElement,{subtree:true,childList:true});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,0));else setTimeout(boot,0);
})();
