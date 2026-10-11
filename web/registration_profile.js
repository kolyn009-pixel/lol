(()=>{'use strict';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const AVATARS=Array.from({length:10},(_,i)=>({id:'student_avatar_'+String(i+1).padStart(2,'0'),url:'/app/assets/avatars/student_avatar_'+String(i+1).padStart(2,'0')+'.svg'}));
const api=async(path,opt={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'request_failed');return j};
let onboardingOpen=false,checked=false,checking=false;
function field(name,...sources){for(const s of sources){if(s&&s[name]!=null&&String(s[name]).trim()!=='')return s[name]}return ''}
function close(){document.getElementById('adeliaOnboarding')?.remove();onboardingOpen=false}
async function openOnboarding(profile,me){
 if(onboardingOpen)return;onboardingOpen=true;
 const initialName=field('display_name',profile,profile?.student,me?.session,me?.student)||field('name',profile,profile?.student,me?.session,me?.student);
 let kind=profile.avatar_kind||'PRESET',value=profile.avatar_value||AVATARS[0].id;
 const host=document.createElement('div');host.id='adeliaOnboarding';host.className='adelia-onboarding-backdrop';document.body.append(host);
 host.innerHTML='<section class="adelia-onboarding-card" role="dialog" aria-modal="true" aria-labelledby="onboardingTitle"><div class="adelia-onboarding-brand">Аделия</div><h2 id="onboardingTitle">Настроим твой профиль</h2><p>Вход создан. Осталось выбрать аватар и проверить имя.</p><label for="adeliaOnboardingName">Имя</label><input id="adeliaOnboardingName" maxlength="40" value="'+esc(initialName)+'" placeholder="Имя"><label>Аватар</label><div class="adelia-onboarding-avatars">'+AVATARS.map((a,i)=>'<button type="button" class="adelia-onboarding-avatar '+(value===a.id?'selected':'')+'" data-avatar="'+a.id+'" aria-label="Аватар '+(i+1)+'"><img src="'+a.url+'" alt="" loading="lazy"></button>').join('')+'</div><button type="button" class="ghost" data-avatar-editor>Загрузить своё фото</button><label class="adelia-onboarding-online"><input type="checkbox" id="adeliaOnboardingOnline" '+(profile.show_online?'checked':'')+'> Показывать статус «онлайн»</label><button type="button" class="adelia-onboarding-save" id="adeliaOnboardingSave">Продолжить</button><div class="adelia-onboarding-error" id="adeliaOnboardingError" role="status"></div></section>';
 host.querySelectorAll('[data-avatar]').forEach(b=>b.onclick=()=>{kind='PRESET';value=b.dataset.avatar;host.querySelectorAll('[data-avatar]').forEach(x=>x.classList.toggle('selected',x===b))});
 const changed=e=>{kind=e.detail.custom?'CUSTOM':'PRESET';value=e.detail.custom?e.detail.url:e.detail.preset;host.querySelectorAll('[data-avatar]').forEach(x=>x.classList.toggle('selected',x.dataset.avatar===value))};
 window.addEventListener('adelia:avatar-changed',changed);
 host.querySelector('#adeliaOnboardingSave').onclick=async()=>{const btn=host.querySelector('#adeliaOnboardingSave'),err=host.querySelector('#adeliaOnboardingError'),name=host.querySelector('#adeliaOnboardingName').value.trim();if(!name){err.textContent='Проверь имя';return}btn.disabled=true;err.textContent='';try{await api('/student/profile',{method:'POST',body:JSON.stringify({display_name:name,avatar_kind:kind,avatar_value:value,show_online:host.querySelector('#adeliaOnboardingOnline').checked})});window.removeEventListener('adelia:avatar-changed',changed);close();window.AdeliaAppearance?.load().catch(()=>{});if(window.AdeliaStudentRender)window.AdeliaStudentRender('home');else location.reload()}catch{err.textContent='Не удалось сохранить профиль. Проверьте соединение и попробуйте ещё раз.';btn.disabled=false}};
 host.querySelector('#adeliaOnboardingName').focus();
}
async function checkAfterAuth(){
 if(checked||checking)return;checking=true;
 try{const me=await api('/auth/me');if(!me.authenticated||me.session?.role!=='student')return;const profile=await api('/student/profile');checked=true;if(!profile?.onboarding_completed)openOnboarding(profile,me)}catch{}finally{checking=false}
}
function hideOldPreAuthProfile(){document.getElementById('registrationProfileFields')?.remove()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{hideOldPreAuthProfile();checkAfterAuth()});else{hideOldPreAuthProfile();checkAfterAuth()}
window.addEventListener('adelia:student-authenticated',()=>{checked=false;checkAfterAuth()});
})();

