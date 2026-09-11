(()=>{
const AVATARS=Array.from({length:10},(_,i)=>({
  id:`student_avatar_${String(i+1).padStart(2,'0')}`,
  url:`/app/assets/avatars/students/student_avatar_${String(i+1).padStart(2,'0')}.png`
}));
const api=async(path,opt={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'request_failed');return j};
let onboardingOpen=false;

function field(name,...sources){for(const s of sources){if(s&&s[name]!=null&&String(s[name]).trim()!=='')return s[name]}return ''}

function overlay(){
 let host=document.getElementById('adeliaOnboarding');
 if(host)return host;
 host=document.createElement('div');host.id='adeliaOnboarding';host.className='adelia-onboarding-backdrop';document.body.append(host);return host;
}

function close(){document.getElementById('adeliaOnboarding')?.remove();onboardingOpen=false}

async function openOnboarding(profile,me){
 if(onboardingOpen)return;onboardingOpen=true;
 const initialName=field('display_name',profile,profile?.student,me?.session,me?.student)||field('name',profile,profile?.student,me?.session,me?.student);
 const currentAvatar=profile?.avatar_value||AVATARS[0].id;
 const showOnline=!!profile?.show_online;
 const host=overlay();
 host.innerHTML=`<section class="adelia-onboarding-card" role="dialog" aria-modal="true"><div class="adelia-onboarding-brand">Аделия 💜</div><h2>Настроим твой профиль</h2><p>Код подтверждён. Мы уже подставили данные из первой регистрации — осталось выбрать аватар и проверить имя.</p><label>Имя</label><input id="adeliaOnboardingName" maxlength="40" value="${String(initialName||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;')}" placeholder="Имя"><label>Аватар</label><div class="adelia-onboarding-avatars">${AVATARS.map((a,i)=>`<button type="button" class="adelia-onboarding-avatar ${(currentAvatar===a.id||(!profile?.avatar_value&&i===0))?'selected':''}" data-avatar="${a.id}"><img src="${a.url}" alt="Аватар ${i+1}"></button>`).join('')}</div><input type="hidden" id="adeliaOnboardingAvatar" value="${currentAvatar}"><label class="adelia-onboarding-online"><input type="checkbox" id="adeliaOnboardingOnline" ${showOnline?'checked':''}> Показывать статус «онлайн»</label><button type="button" class="adelia-onboarding-save" id="adeliaOnboardingSave">Продолжить</button><div class="adelia-onboarding-error" id="adeliaOnboardingError"></div></section>`;
 host.querySelectorAll('[data-avatar]').forEach(b=>b.onclick=()=>{host.querySelectorAll('[data-avatar]').forEach(x=>x.classList.toggle('selected',x===b));document.getElementById('adeliaOnboardingAvatar').value=b.dataset.avatar});
 document.getElementById('adeliaOnboardingSave').onclick=async()=>{
   const btn=document.getElementById('adeliaOnboardingSave'),err=document.getElementById('adeliaOnboardingError');
   const name=(document.getElementById('adeliaOnboardingName').value||'').trim();
   if(!name){err.textContent='Проверь имя';return}
   btn.disabled=true;err.textContent='';
   try{
     await api('/student/profile',{method:'POST',body:JSON.stringify({display_name:name,avatar_kind:'PRESET',avatar_value:document.getElementById('adeliaOnboardingAvatar').value,show_online:!!document.getElementById('adeliaOnboardingOnline').checked,onboarding_completed:true})});
     close();
     if(typeof window.render==='function')window.render('home');else location.reload();
   }catch(e){err.textContent='Не удалось сохранить профиль';btn.disabled=false}
 };
}

async function checkAfterAuth(){
 try{
   const me=await api('/auth/me');
   if(!me.authenticated||me.session?.role!=='student')return;
   const profile=await api('/student/profile');
   if(!profile?.onboarding_completed)openOnboarding(profile,me);
 }catch{}
}

function hideOldPreAuthProfile(){
 const old=document.getElementById('registrationProfileFields');if(old)old.remove();
}

const obs=new MutationObserver(()=>{hideOldPreAuthProfile();checkAfterAuth()});
obs.observe(document.documentElement,{subtree:true,childList:true});
window.addEventListener('load',()=>{hideOldPreAuthProfile();setTimeout(checkAfterAuth,150)});
setTimeout(checkAfterAuth,250);
})();
