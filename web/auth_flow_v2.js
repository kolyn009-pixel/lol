(()=>{
'use strict';
const api=async(path,opt={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok){const e=new Error(j.error||'request_failed');e.status=r.status;throw e}return j};
let verifiedCode='';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function host(){return document.querySelector('#content')||document.querySelector('main')||document.body}
function resultText(err){const x=String(err?.message||'');return x==='expired'?'Срок действия кода истёк. Получите новый код в боте.':x==='too_many_attempts'?'Слишком много попыток. Подождите минуту.':'Код не подошёл. Проверьте его или получите новый в боте.'}
function codeScreen(message=''){
 verifiedCode='';
 host().innerHTML=`<section class="form-card auth-card adelia-auth-v2"><span class="status">Аделия 💜</span><h2>Подтвердите код</h2><p>Сначала подтвердим, что это ваш кабинет. Логин и пароль появятся только после успешной проверки кода.</p><label>Код из TutorBot</label><input class="code-input" id="adeliaVerifyCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000"><button class="form-primary" id="adeliaVerifyButton">Подтвердить код</button><button class="mini-btn" id="adeliaExistingLogin">Уже есть логин и пароль</button><div id="adeliaAuthResult" class="form-error">${esc(message)}</div></section>`;
 document.getElementById('adeliaVerifyButton').onclick=verify;
 document.getElementById('adeliaExistingLogin').onclick=()=>{window.__adeliaAuthV2=false;window.authMode='password';if(typeof window.render==='function')window.render('studentLogin');else location.reload()};
}
async function verify(){
 const input=document.getElementById('adeliaVerifyCode'),btn=document.getElementById('adeliaVerifyButton'),out=document.getElementById('adeliaAuthResult');
 const code=(input?.value||'').replace(/\D/g,'');if(code.length!==6){out.textContent='Введите 6 цифр из сообщения TutorBot.';return}
 btn.disabled=true;out.textContent='Проверяю код…';
 try{const d=await api('/auth/student/code/verify',{method:'POST',body:JSON.stringify({code})});verifiedCode=code;credentialsScreen(d.student||{})}catch(e){out.textContent=resultText(e);btn.disabled=false}
}
function credentialsScreen(student){
 host().innerHTML=`<section class="form-card auth-card adelia-auth-v2"><span class="status">Код подтверждён ✓</span><h2>Создайте вход</h2><p>${student?.name?`Кабинет: <b>${esc(student.name)}</b>. `:''}Теперь придумайте постоянный логин и пароль. Код из бота для обычного входа больше не понадобится.</p><label>Логин</label><input id="adeliaNewLogin" autocomplete="username" autocapitalize="none" placeholder="например, ivan.petrov"><label>Пароль</label><input id="adeliaNewPassword" type="password" autocomplete="new-password" placeholder="минимум 8 символов"><button class="form-primary" id="adeliaSaveCredentials">Сохранить и перейти на главную</button><button class="mini-btn" id="adeliaBackToCode">← Другой код</button><div id="adeliaAuthResult" class="form-error"></div></section>`;
 document.getElementById('adeliaSaveCredentials').onclick=setup;
 document.getElementById('adeliaBackToCode').onclick=()=>codeScreen();
}
async function setup(){
 const login=(document.getElementById('adeliaNewLogin')?.value||'').trim().toLowerCase(),password=document.getElementById('adeliaNewPassword')?.value||'',btn=document.getElementById('adeliaSaveCredentials'),out=document.getElementById('adeliaAuthResult');
 if(!/^[a-z0-9._-]{4,32}$/.test(login)){out.textContent='Логин: 4–32 символа, латиница, цифры, точка, _ или -.';return}
 if(password.length<8){out.textContent='Пароль должен содержать минимум 8 символов.';return}
 btn.disabled=true;out.textContent='Создаю кабинет…';
 try{await api('/auth/student/code',{method:'POST',body:JSON.stringify({code:`setup:${verifiedCode}:${login}:${password}`})});location.replace('/app/')}catch(e){const x=String(e.message||'');out.textContent=x==='login_taken'?'Этот логин уже занят. Выберите другой.':x==='expired'?'Код успел истечь. Получите новый код в боте.':'Не удалось сохранить вход. Попробуйте ещё раз.';btn.disabled=false}
}
function intercept(){
 const card=document.querySelector('.auth-card');if(!card||window.__adeliaAuthV2===false)return;
 const oldSetup=card.querySelector('#studentSetupButton');
 if(oldSetup||card.querySelector('#loginCode')){window.__adeliaAuthV2=true;codeScreen()}
}
new MutationObserver(intercept).observe(document.documentElement,{subtree:true,childList:true});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(intercept,0));else setTimeout(intercept,0);
})();