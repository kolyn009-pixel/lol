const navItems=[...document.querySelectorAll('.nav-item')];
navItems.forEach(item=>item.addEventListener('click',()=>{
  navItems.forEach(x=>x.classList.remove('active'));
  item.classList.add('active');
  const labels={home:'Главная',schedule:'Занятия',homework:'Домашнее задание',profile:'Профиль'};
  if(item.dataset.tab!=='home'){
    document.querySelector('#content').innerHTML=`<section class="hero-card"><div class="hero-copy"><span class="pill">Аделия 💜</span><h2>${labels[item.dataset.tab]}</h2><p>Раздел подключается к данным TutorBot.</p></div><button class="primary-btn" id="backHome">На главную</button></section>`;
    document.querySelector('#backHome').addEventListener('click',()=>location.reload());
  }
}));
