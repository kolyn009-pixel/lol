async function loadPrices(){
  const root=document.querySelector('#priceGrid');
  if(!root)return;
  try{
    const r=await fetch('/api/public/prices',{headers:{Accept:'application/json'}});
    if(!r.ok)throw new Error('prices_unavailable');
    const items=await r.json();
    root.innerHTML=items.map(x=>`<article class="price-card"><span>${x.title}</span><b>${Number(x.hourly_rate).toLocaleString('ru-RU')} ₽</b><small>за 60 минут</small></article>`).join('');
  }catch(e){
    root.innerHTML='<div class="data-note">Актуальные направления и цены появятся после подключения сайта к TutorBot.</div>';
  }
}

async function loadReviews(){
  const root=document.querySelector('#reviewsGrid');
  if(!root)return;
  try{
    const r=await fetch('/api/public/reviews',{headers:{Accept:'application/json'}});
    if(!r.ok)throw new Error('reviews_unavailable');
    const items=await r.json();
    root.innerHTML=items.slice(0,6).map(x=>`<article class="review-card"><div class="stars">★★★★★</div><p>${escapeHtml(x.text)}</p><footer><b>${escapeHtml(x.author||'Ученик')}</b><span>${escapeHtml(x.source||'Профи.ру')}</span></footer></article>`).join('');
  }catch(e){
    root.innerHTML='<div class="data-note">Отзывы с Профи.ру добавим после импорта подтверждённых отзывов.</div>';
  }
}
function escapeHtml(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
loadPrices();loadReviews();