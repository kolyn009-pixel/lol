(()=>{'use strict';
const root=document.querySelector('#legalContent');
const text=(tag,value,parent)=>{const n=document.createElement(tag);n.textContent=value;parent.append(n);return n;};
fetch('/api/public/legal'+location.search,{credentials:'same-origin',cache:'no-store'}).then(async r=>{if(!r.ok)throw Error();return r.json();}).then(({edition:d})=>{
 root.replaceChildren();if(!d){text('p','Документы готовятся к публикации. Принимать их сейчас не требуется.',root);return;}
 text('p','Редакция от '+new Date(d.published_at).toLocaleDateString('ru-RU'),root).className='muted';
 const nav=text('nav','',root);for(const [id,title] of [['details','Реквизиты'],['terms','Условия занятий'],['privacy','Конфиденциальность'],['consent','Согласие на обработку данных']]){const a=text('a',title,nav);a.href='#'+id;}
 const card=text('section','',root);card.className='card';card.id='details';text('h2','Исполнитель и контакты',card);const dl=text('dl','',card);
 for(const [title,val] of [['Самозанятый',d.name],['ИНН',d.inn],['Электронная почта',d.email],['Телефон',d.phone],['Адрес для обращений',d.address]]){text('dt',title,dl);text('dd',val,dl);}
 const prices=text('a','Актуальные направления и тарифы',card);prices.href='/#prices';
 for(const [id,title] of [['terms','Условия оказания услуг'],['privacy','Политика конфиденциальности'],['consent','Согласие на обработку персональных данных']]){const section=text('section','',root);section.id=id;section.className='card';text('h2',title,section);text('div',d[id],section).className='copy';}
 const a=text('a','Постоянная ссылка на эту редакцию',root);a.href='/app/legal.html?version='+encodeURIComponent(d.version);
 if(location.hash)document.getElementById(location.hash.slice(1))?.scrollIntoView();
}).catch(()=>{root.textContent='Не удалось загрузить документы. Проверьте подключение и обновите страницу.';root.className='error';});
})();
