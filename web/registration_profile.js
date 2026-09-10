(()=>{
const PRESETS=[['adelia_01','🌙'],['adelia_02','⭐'],['adelia_03','🪐'],['adelia_04','📚'],['adelia_05','⚡'],['adelia_06','🧠'],['adelia_07','🎯'],['adelia_08','🔭']];
let pending=null,installing=false;
const api=async(path,opt={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'request_failed');return j};
function inject(){
 const btn=document.getElementById('studentSetupButton');if(!btn||document.getElementById('registrationProfileFields'))return;
 const wrap=document.createElement('div');wrap.id='registrationProfileFields';wrap.className='registration-profile-fields';wrap.innerHTML=`<div class="registration-profile-title"><b>Твой профиль в Аделии</b><span>Его увидят участники твоих групп. Контакты другим ученикам не показываются.</span></div><label>Имя в приложении</label><input id="registrationDisplayName" maxlength="40" placeholder="Например, Иван"><label>Выбери аватар</label><div class="registration-avatar-grid">${PRESETS.map((x,i)=>`<button type="button" class="registration-avatar ${i===0?'selected':''}" data-avatar="${x[0]}" aria-label="Аватар ${i+1}">${x[1]}</button>`).join('')}</div><input type="hidden" id="registrationAvatar" value="adelia_01"><label class="registration-online"><input type="checkbox" id="registrationShowOnline"> Показывать другим зелёную точку, когда я в приложении</label><small>Точное время последнего посещения никому не показывается.</small>`;
 btn.parentNode.insertBefore(wrap,btn);wrap.querySelectorAll('[data-avatar]').forEach(x=>x.onclick=()=>{wrap.querySelectorAll('[data-avatar]').forEach(a=>a.classList.toggle('selected',a===x));document.getElementById('registrationAvatar').value=x.dataset.avatar});
 btn.addEventListener('click',()=>{pending={display_name:(document.getElementById('registrationDisplayName')?.value||'').trim(),avatar_value:document.getElementById('registrationAvatar')?.value||'adelia_01',show_online:!!document.getElementById('registrationShowOnline')?.checked};afterAuth()},true);
}
async function afterAuth(){
 if(installing)return;installing=true;
 for(let i=0;i<20;i++){
  await new Promise(r=>setTimeout(r,150));
  try{const me=await api('/auth/me');if(me.authenticated&&me.session?.role==='student'){const body={avatar_kind:'PRESET',avatar_value:pending?.avatar_value||'adelia_01',show_online:!!pending?.show_online};if(pending?.display_name)body.display_name=pending.display_name;await api('/student/profile',{method:'POST',body:JSON.stringify(body)});pending=null;break}}catch{}
 }
 installing=false;
}
const observer=new MutationObserver(inject);observer.observe(document.documentElement,{subtree:true,childList:true});inject();
})();
