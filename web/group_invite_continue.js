(()=>{'use strict';
const key='adelia:pending-group-invite',token=new URLSearchParams(location.search).get('group_invite');
if(token&&/^[A-Za-z0-9_-]{40,64}$/.test(token)){try{sessionStorage.setItem(key,JSON.stringify({token,at:Date.now()}))}catch{}}
window.addEventListener('adelia:student-authenticated',()=>{let pending;try{pending=JSON.parse(sessionStorage.getItem(key)||'null')}catch{}if(!pending&&token)pending={token,at:Date.now()};if(!pending||Date.now()-pending.at>3600000||!/^[A-Za-z0-9_-]{40,64}$/.test(pending.token))return;try{sessionStorage.removeItem(key)}catch{}location.replace('/app/group-invite.html?invite='+encodeURIComponent(pending.token))},{once:true});
})();
