/* One brand, avatar catalogue and editor for web, PWA and desktop roles. */
(()=>{'use strict';
if(window.AdeliaAppearance)return;
const logo='/app/assets/icons/adelia-icon-180.png?v=20261011-ui1';
const presets=Array.from({length:10},(_,i)=>({id:'student_avatar_'+String(i+1).padStart(2,'0'),url:'/app/assets/avatars/student_avatar_'+String(i+1).padStart(2,'0')+'.svg'}));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let own=null,loading=null,queued=false;
function safeUrl(value){try{const u=new URL(value,location.origin);return ['http:','https:'].includes(u.protocol)?u.href:''}catch{return ''}}
function avatarUrl(p={}){
 if(p.avatar_kind==='CUSTOM'){
  try{const u=new URL(p.avatar_value,location.origin);if(u.origin===location.origin&&u.pathname==='/api/profile/avatar')return u.href}catch{}
 }
 let id=p.avatar_value||p.preset||'student_avatar_01';
 if(/^adelia_0[1-8]$/.test(id))id='student_avatar_'+id.slice(-2);
 return presets.find(x=>x.id===id)?.url||presets[0].url;
}
const avatar=p=>'<img class="adelia-avatar-image" src="'+esc(avatarUrl(p))+'" alt="" loading="lazy">';
const request=async(path,opt={})=>{
 const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),12000);
 try{const r=await fetch('/api'+path,{credentials:'same-origin',cache:'no-store',...opt,signal:ctrl.signal});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'request_failed');return d}finally{clearTimeout(timer)}
};
async function load(){if(loading)return loading;loading=request('/profile/appearance').then(p=>{own=p;update();return p}).catch(e=>{if(e.message==='unauthorized')own=null;throw e}).finally(()=>loading=null);return loading}
function update(){
 if(!own)return;
 const setImage=el=>{if(el&&el.querySelector('img')?.getAttribute('src')!==own.url)el.innerHTML='<img class="adelia-avatar-image" src="'+esc(own.url)+'" alt="">'};
 const button=document.querySelector('#roleButton');if(button){setImage(button);button.title='Мой профиль'}
 document.querySelectorAll('.adelia-avatar-button[data-avatar-editor]').forEach(setImage);
 setImage(document.querySelector('.profile-card .big-avatar'));
}
function brand(){
 document.querySelectorAll('.login-brand-mark,.adelia-onboarding-brand,.side-foot>span,.student-chat-avatar').forEach(el=>{if(el.querySelector('.adelia-brand-image'))return;const img=document.createElement('img');img.className='adelia-brand-image';img.src=logo;img.alt='Аделия';el.replaceChildren(img)});
 const eyebrow=document.querySelector('.topbar .eyebrow');if(eyebrow&&!eyebrow.querySelector('img')){const img=document.createElement('img');img.src=logo;img.alt='';img.className='adelia-brand-inline';eyebrow.prepend(img)}
 const parent=document.querySelector('#root > header h1');if(parent&&!parent.querySelector('img')){const img=document.createElement('img');img.src=logo;img.alt='';img.className='adelia-brand-inline';parent.prepend(img)}
 const navNames={home:'home',dashboard:'home',schedule:'calendar',homework:'homework',reviews:'homework',messages:'chat',payments:'payment',finance:'payment',profile:'profile',students:'students',groups:'group',library:'library',formulas:'book',analytics:'analytics',health:'settings'};
 document.querySelectorAll('.nav-item[data-tab],.teacher-shell aside nav button[data-view]').forEach(b=>{const name=navNames[b.dataset.tab||b.dataset.view],slot=b.querySelector('.ico')||b.querySelector('span');if(name&&slot&&!slot.querySelector('svg')&&window.AdeliaIcons)slot.innerHTML=window.AdeliaIcons.icon(name)});
 const header=document.querySelector('.teacher-shell main > header .header-actions')||document.querySelector('.parent-head-actions');
 if(header&&!header.querySelector('[data-avatar-editor]')){const b=document.createElement('button');b.type='button';b.className='adelia-avatar-button';b.dataset.avatarEditor='1';b.setAttribute('aria-label','Изменить аватар');b.innerHTML='<img class="adelia-avatar-image" src="'+(own?esc(own.url):presets[0].url)+'" alt="">';header.append(b)}
 const card=document.querySelector('.profile-card');if(card&&!card.querySelector('[data-avatar-editor]')){const b=document.createElement('button');b.type='button';b.className='ghost';b.dataset.avatarEditor='1';b.textContent='Изменить аватар';card.append(b)}
 update();
}
function queue(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;brand()})}
async function toCanvas(file){
 if(file.size>8*1024*1024)throw new Error('Выберите изображение до 8 МБ.');
 if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw new Error('Выберите фото в формате JPG, PNG или WebP.');
 const url=URL.createObjectURL(file),img=new Image();
 try{img.src=url;await img.decode();if(img.naturalWidth*img.naturalHeight>25_000_000)throw new Error('Изображение слишком большое. Выберите уменьшенную копию.');const canvas=document.createElement('canvas');canvas.width=canvas.height=256;const ctx=canvas.getContext('2d');const side=Math.min(img.naturalWidth,img.naturalHeight);ctx.drawImage(img,(img.naturalWidth-side)/2,(img.naturalHeight-side)/2,side,side,0,0,256,256);return await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('Не удалось подготовить фото.')),'image/png'))}finally{URL.revokeObjectURL(url)}
}
async function edit(){
 if(document.querySelector('#adeliaAvatarEditor'))return;
 let p;try{p=await load()}catch{window.alert('Для изменения аватара войдите в свой кабинет.');return}
 const previous=document.activeElement,dialog=document.createElement('dialog');dialog.id='adeliaAvatarEditor';dialog.className='adelia-avatar-dialog';
 dialog.innerHTML='<header><div><span class="eyebrow">Мой профиль</span><h2>Выберите аватар</h2></div><button type="button" data-close aria-label="Закрыть">×</button></header><p>Один аватар для сайта и приложений. Фото будет обрезано по центру; данные камеры не сохраняются.</p><div class="adelia-avatar-preview"><img src="'+esc(p.url)+'" alt="Предпросмотр аватара"></div><div class="adelia-avatar-grid">'+presets.map((x,i)=>'<button type="button" data-preset="'+x.id+'" aria-label="Аватар '+(i+1)+'" aria-pressed="'+(!p.custom&&p.preset===x.id)+'"><img src="'+x.url+'" alt=""></button>').join('')+'</div><label class="adelia-avatar-upload">Загрузить своё фото<input type="file" accept="image/jpeg,image/png,image/webp" hidden></label><small>JPG, PNG или WebP · до 8 МБ</small><p class="adelia-avatar-error" role="status" aria-live="polite"></p><footer><button type="button" data-close>Отмена</button><button type="button" class="primary" data-save>Сохранить</button></footer>';
 document.body.append(dialog);dialog.showModal();let selected=p.preset,photo=null,previewUrl=null,busy=false,dirty=false;
 dialog.addEventListener('close',()=>{if(previewUrl)URL.revokeObjectURL(previewUrl);dialog.remove();previous?.focus()},{once:true});
 dialog.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{if(!busy)dialog.close()});
 dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault()});
 const error=dialog.querySelector('[role="status"]'),save=dialog.querySelector('[data-save]'),preview=dialog.querySelector('.adelia-avatar-preview img');
 dialog.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{if(busy)return;dirty=true;photo=null;selected=b.dataset.preset;preview.src=presets.find(x=>x.id===selected).url;dialog.querySelectorAll('[data-preset]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));error.textContent=''});
 dialog.querySelector('input').onchange=async e=>{const file=e.target.files?.[0];if(!file||busy)return;busy=true;e.target.disabled=true;save.disabled=true;error.textContent='Готовлю фото…';try{const prepared=await toCanvas(file);photo=prepared;dirty=true;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(photo);preview.src=previewUrl;dialog.querySelectorAll('[data-preset]').forEach(x=>x.setAttribute('aria-pressed','false'));error.textContent=''}catch(err){error.textContent=err.message}finally{busy=false;e.target.disabled=false;save.disabled=false}};
 save.onclick=async()=>{if(busy)return;if(!dirty){dialog.close();return}busy=true;save.disabled=true;error.textContent='Сохраняю…';try{if(photo){const fd=new FormData();fd.append('file',photo,'avatar.png');own=await request('/profile/avatar',{method:'POST',body:fd})}else own=await request('/profile/appearance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preset:selected})});update();window.dispatchEvent(new CustomEvent('adelia:avatar-changed',{detail:own}));dialog.close()}catch{error.textContent='Не удалось сохранить аватар. Проверьте соединение и попробуйте ещё раз.'}finally{busy=false;save.disabled=false}};
}
document.addEventListener('click',e=>{if(e.target.closest('[data-avatar-editor]'))edit()});
new MutationObserver(queue).observe(document.body,{childList:true,subtree:true});
window.addEventListener('adelia:student-authenticated',()=>load().catch(()=>{}));
window.addEventListener('adelia:teacher-login',()=>load().catch(()=>{}));
window.addEventListener('adelia:parent-render',()=>{queue();load().catch(()=>{})});
window.AdeliaAppearance={logo,presets,avatar,avatarUrl,safeUrl,edit,load,get owner(){return own}};
brand();if(document.querySelector('.app-shell,.teacher-shell,#root'))load().catch(()=>{});
})();
