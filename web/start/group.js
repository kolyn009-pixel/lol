(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const params = new URLSearchParams(location.search);
  const groupId = Number(params.get('group_id'));
  const form = $('#groupForm');
  const zones = [['Europe/Kaliningrad','Калининград · МСК−1'],['Europe/Moscow','Москва / Санкт-Петербург · МСК'],['Europe/Samara','Самара · МСК+1'],['Asia/Yekaterinburg','Екатеринбург · МСК+2'],['Asia/Omsk','Омск · МСК+3'],['Asia/Krasnoyarsk','Красноярск / Новосибирск · МСК+4'],['Asia/Irkutsk','Иркутск · МСК+5'],['Asia/Yakutsk','Якутск / Чита · МСК+6'],['Asia/Vladivostok','Владивосток / Хабаровск · МСК+7'],['Asia/Magadan','Магадан / Сахалин · МСК+8'],['Asia/Kamchatka','Камчатка / Анадырь · МСК+9']];
  let detected = 'Europe/Moscow';
  try { detected = Intl.DateTimeFormat().resolvedOptions().timeZone || detected; } catch {}
  if (!zones.some(([key]) => key === detected)) zones.push([detected, detected]);
  for (const [key, label] of zones) form.elements.timezone.add(new Option(label, key));
  form.elements.timezone.value = detected;
  const subjects = {PHYSICS:'Физика',CHEMISTRY:'Химия'};
  const goals = {EGE:'ЕГЭ',OGE:'ОГЭ',OLYMPIAD:'Олимпиада',SCHOOL:'Школьная программа'};
  const days = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье'];
  let group;
  function render(data) {
    group = data.group;
    document.title = group.name + ' · Запись · Аделия';
    $('#groupTitle').textContent = group.name;
    $('#groupSubject').textContent = [subjects[group.subject] || group.subject,goals[group.study_goal] || group.study_goal].filter(Boolean).join(' · ');
    $('#groupDescription').textContent = group.description || 'Онлайн-занятия с Николаем Соловьевым в образовательном пространстве «Аделия».';
    const price = Number(group.price_per_lesson);
    const facts = [price === 0 ? 'Бесплатное занятие' : price.toLocaleString('ru-RU')+' ₽ за занятие',group.waitlist ? 'Запись в лист ожидания' : group.seats_left === null ? 'Набор открыт' : 'Свободных мест: '+group.seats_left];
    for (const text of facts) { const el=document.createElement('span'); el.className='fact'; el.textContent=text; $('#groupFacts').append(el); }
    const slots = data.slots || [];
    for (const slot of slots) {const li=document.createElement('li');li.textContent=`${days[slot.weekday] || ''} · ${slot.start_time} · ${slot.duration_minutes} минут`;$('#groupSchedule').append(li);}
    if (!slots.length) {const li=document.createElement('li');li.textContent='Расписание уточняется при наборе группы';$('#groupSchedule').append(li);}
    $('#scheduleZone').textContent = slots.length ? 'Время расписания: '+data.timezone+'. Ваш часовой пояс укажите в заявке.' : '';
    if (group.waitlist) {$('#formTitle').textContent='Лист ожидания';$('#submitButton').textContent='Встать в лист ожидания';}
    $('#groupCard').setAttribute('aria-busy','false');
    $('#loadState').textContent='';form.hidden=false;
  }
  async function load() {
    try {
      if (!Number.isSafeInteger(groupId) || groupId <= 0) throw new Error('Группа не выбрана. Перейдите на главную и выберите группу с открытым набором.');
      const r=await fetch('/api/public/group-registration?group_id='+groupId,{cache:'no-store',credentials:'same-origin'});
      if (!r.ok) throw new Error(r.status===404 ? 'Набор в эту группу закрыт или группа недоступна. Посмотрите другие группы на главной.' : 'Не удалось загрузить группу. Обновите страницу.');
      render(await r.json());
    } catch(e) {$('#groupTitle').textContent='Запись в группу';$('#groupCard').setAttribute('aria-busy','false');$('#loadState').textContent=e.message;}
  }
  const errors={consent_required:'Подтвердите согласие на обработку данных.',invalid_contact:'Проверьте контакт для связи.',invalid_grade:'Выберите класс.',invalid_timezone:'Выберите часовой пояс.',invalid_fields:'Проверьте имя и заполненные поля.',group_not_available:'Набор в эту группу закрыт. Посмотрите другие группы на главной.',too_many_attempts:'Слишком много попыток. Попробуйте через минуту.'};
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const button=$('#submitButton');if(button.disabled || !form.reportValidity())return;
    button.disabled=true;$('#formState').textContent='Отправляем…';
    const fields=new FormData(form);
    const source=['utm_source','utm_medium','utm_campaign'].map(key=>params.get(key)||'').join(' / ').slice(0,200);
    try {
      const r=await fetch('/api/public/group-registration',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({group_id:groupId,name:fields.get('name'),grade:fields.get('grade'),contact:fields.get('contact'),timezone:fields.get('timezone'),note:fields.get('note'),consent:fields.get('consent')==='on',source})});
      const data=await r.json();
      if(!r.ok)throw new Error(errors[data.error]||'Не удалось отправить заявку. Попробуйте ещё раз.');
      form.hidden=true;$('#success').hidden=false;
      $('#successText').textContent=data.waitlist ? 'Вы записаны в лист ожидания группы «'+group.name+'». Николай свяжется с вами по указанному контакту и обсудит варианты участия.' : 'Николай свяжется с вами по указанному контакту, чтобы обсудить подготовку и участие в группе «'+group.name+'».';
      $('#success').focus();
    }catch(e){$('#formState').textContent=e.message;button.disabled=false;}
  });
  load();
})();
