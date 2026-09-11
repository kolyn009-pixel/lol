(()=>{
  const body=document.body;
  const content=document.getElementById('content');
  if(!body||!content)return;
  const sync=()=>{
    const text=(content.textContent||'').toLowerCase();
    const hasPassword=!!content.querySelector('input[type="password"]');
    const hasLogin=!!content.querySelector('input[name*="login" i], input[autocomplete="username"]');
    const authCopy=text.includes('вход в личный кабинет')||text.includes('первый вход')||text.includes('войти');
    const isAuth=hasPassword&&(hasLogin||authCopy);
    body.classList.toggle('adelia-auth-screen',isAuth);
  };
  sync();
  new MutationObserver(sync).observe(content,{childList:true,subtree:true});
})();
