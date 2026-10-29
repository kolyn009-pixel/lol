/* Browser journeys against the actual stage-1 API and disposable SQLite. */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
const path=require('node:path');
const readline=require('node:readline');
const fs=require('node:fs/promises');

(async()=>{
 const server=spawn('python',[path.join(__dirname,'self_study_selftest.py'),'--serve'],{stdio:['ignore','pipe','pipe']});
 const ready=new Promise((resolve,reject)=>{const lines=readline.createInterface({input:server.stdout});lines.once('line',s=>{try{resolve(JSON.parse(s));}catch(e){reject(e);}});server.once('error',reject);server.once('exit',c=>reject(Error('Fixture exited '+c)));});
 let browser,page;
 const errors=[];
 try{
  const {port}=await ready,url=`http://127.0.0.1:${port}`;
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext();await context.addCookies([{name:'role',value:'teacher',url}]);
  async function completeFamilyPlacement(page){
   await page.locator('[data-placement-required]').first().waitFor();
   while(await page.locator('[data-placement-required]').count()){
    await page.locator('[data-placement-required]').first().click();
    while(true){
     await page.locator('[data-placement-form]').waitFor();
     await page.locator('[data-placement-form] input[value="unknown"]').check();
     const submit=page.locator('[data-placement-form] button[type=submit]');
     const last=(await submit.innerText()).includes('Получить маршрут');
     await submit.click();if(last)break;
    }
    await page.getByRole('heading',{name:/Сначала выберем точку старта|Результаты и ближайшие цели/}).waitFor();
   }
   await page.locator('[data-onboarding-done]').click();
  }
  page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url+'/teacher/');await page.locator('[data-self-study]').click();
  await page.locator('[data-ss-language="en"]').waitFor();
  assert.equal(await page.locator('.ss-unit').count(),18);
  assert.equal(await page.locator('#app').isVisible(),false);
  await page.locator('[data-ss-budget="180"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-ss-budget="180"]')?.getAttribute('aria-pressed')==='true');
  assert.match(await page.locator('#selfStudyRoot').innerText(),/120 мин в день/);
  await page.locator('[data-ss-view=program]').click();
  await page.locator('summary').filter({hasText:'Настроить даты'}).click();
  await page.locator('[name=en]').fill('2027-09-15');await page.getByRole('button',{name:'Сохранить даты'}).click();
  await page.waitForFunction(()=>document.querySelector('#selfStudyRoot')?.textContent.includes('2027-09-15'));
  await page.locator('[data-ss-view=today]').click();await page.locator('.ss-primary[data-ss-lesson]').click();
  await page.locator('[name=d0]').fill('used to');await page.locator('[data-ss-save]').click();
  await page.getByText('Ответы сохранены на сервере.',{exact:false}).waitFor();
  // Existing teacher renderers can run without destroying the lesson workspace.
  await page.evaluate(()=>document.querySelector('#app').innerHTML='Поздний ответ рабочего кабинета');
  assert.equal(await page.locator('[name=d0]').inputValue(),'used to');
  await page.reload();await page.locator('[data-ss-language="en"]').waitFor();
  await page.locator('[data-ss-view=today]').click();await page.locator('.ss-primary[data-ss-lesson]').click();
  assert.equal(await page.locator('[name=d0]').inputValue(),'used to');
  await page.getByLabel('Students explain their reasoning first.',{exact:true}).check();
  await page.getByLabel('The effect on exam results.',{exact:true}).check();
  await page.locator('[name=d1]').fill('struggle to');
  await page.getByRole('button',{name:'Проверить ответы',exact:true}).click();
  await page.getByText('Результат сохранён',{exact:true}).waitFor();
  assert.equal(await page.locator('.ss-feedback[data-correct=true]').count(),4);
  await page.getByRole('button',{name:'К программе',exact:true}).click();
  await page.locator('[data-ss-language="en"]').waitFor();
  assert.match(await page.locator('.ss-unit').first().innerText(),/4\/4/);
  // New lesson expressions are recalled, revealed, then scheduled separately.
  await page.locator('[data-ss-view=practice]').click();await page.locator('[data-ss-review]').click();
  await page.locator('[data-ss-card-form] [name=answer]').fill('struggle to');
  await page.getByRole('button',{name:'Проверить выражение',exact:true}).click();
  await page.locator('[data-ss-rating=good]').click();
  await page.locator('[data-ss-card-form] [name=answer]').fill('used to');
  await page.getByRole('button',{name:'Проверить выражение',exact:true}).click();
  await page.getByText('Вспомнил верно',{exact:true}).waitFor();
  await page.locator('[data-ss-back]').click();await page.locator('[data-ss-view=practice]').click();await page.locator('[data-ss-review]').click();
  await page.getByText('Вспомнил верно',{exact:true}).waitFor(); // persisted reveal
  await page.locator('[data-ss-rating=hard]').click();
  await page.locator('[data-ss-card-form] [name=answer]').fill('wrong');
  await page.getByRole('button',{name:'Проверить выражение',exact:true}).click();
  assert.equal(await page.locator('[data-ss-rating=good]').isDisabled(),true);
  await page.locator('[data-ss-rating=again]').click();
  await page.getByText('На сейчас всё готово',{exact:true}).waitFor();
  await page.getByRole('button',{name:'К программе',exact:true}).click();
  await page.locator('[data-ss-view=practice]').click();await page.locator('[data-ss-checkpoint]').click();
  await page.getByLabel('Some visitors worked during the day.',{exact:true}).check();
  await page.locator('[name=r0]').fill('used to');
  await page.locator('[data-ss-checkpoint-save]').click();
  await page.getByText('Ответы сохранены. Можно продолжить позже.',{exact:true}).waitFor();
  await page.locator('[data-ss-back]').click();await page.locator('[data-ss-view=practice]').click();await page.locator('[data-ss-checkpoint]').click();
  assert.equal(await page.locator('[name=r0]').inputValue(),'used to');
  await page.getByLabel('There were fewer noise complaints.',{exact:true}).check();
  await page.getByLabel('Whether learning improved.',{exact:true}).check();
  await page.locator('[name=r1]').fill('first');await page.locator('[name=r2]').fill('depend on');
  await page.getByRole('button',{name:'Завершить контрольную',exact:true}).click();
  await page.getByText('Контрольная сохранена',{exact:false}).waitFor();
  assert.equal(await page.locator('.ss-feedback[data-correct=true]').count(),6);
  await page.getByRole('button',{name:'К программе',exact:true}).click();
  await page.getByText('Следующий новый вариант:',{exact:false}).waitFor();
  assert.match(await page.locator('[data-ss-checkpoint-panel]').innerText(),/Чтение/);
  await page.locator('[data-ss-scenes]').click();
  await page.locator('[name=start]').fill('2:00');await page.locator('[name=end]').fill('4:30');
  await page.locator('[name=summary]').fill('Разговор о договорённости.');
  await page.locator('[name=expression0]').fill('at stake');await page.locator('[name=meaning0]').fill('на кону');
  await page.getByRole('button',{name:'Сохранить сцену',exact:true}).click();
  await page.getByText('Сцена сохранена.',{exact:false}).waitFor();
  assert.match(await page.locator('[data-scenes-list]').innerText(),/2:00–4:30/);
  await page.locator('[data-scene-speak]').click();
  await page.getByRole('button',{name:'Записать ответ',exact:true}).waitFor();
  await page.locator('[data-scenes-back]').click();await page.locator('[data-ss-language="de"]').waitFor();
  await page.locator('[data-ss-language="de"]').click();assert.equal(await page.locator('.ss-unit').count(),11);
  await page.locator('[data-ss-language="fa"]').click();assert.equal(await page.locator('.ss-unit').count(),11);
  await page.locator('[data-ss-view=today]').click();await page.locator('.ss-primary[data-ss-lesson]').click();
  assert.equal(await page.locator('.ss-reading').getAttribute('dir'),'rtl');
  // Raw content is displayed as text, never executable markup.
  const attack='<img src=x onerror="window.__xss=1">';
  await page.locator('[name=d0]').fill(attack);await page.locator('[data-ss-save]').click();
  await page.getByText('Ответы сохранены на сервере.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'К программе',exact:false}).click();
  await page.locator('[data-ss-language="fa"]').waitFor();await page.locator('[data-ss-view=today]').click();await page.locator('.ss-primary[data-ss-lesson]').click();
  assert.equal(await page.locator('[name=d0]').inputValue(),attack);
  assert.equal(await page.evaluate(()=>window.__xss),undefined);
  // A validation failure preserves typed answers.
  await page.locator('[name=d1]').fill('خوشبختم');
  await page.getByRole('button',{name:'Проверить ответы',exact:true}).click();
  assert.equal(await page.locator('[name=d0]').inputValue(),attack);
  await page.locator('[data-ss-save]').click();await page.getByText('Ответы сохранены на сервере.',{exact:false}).waitFor();
  await page.locator('aside [data-view=dashboard]').click();
  assert.equal(await page.locator('#selfStudyRoot').count(),0);assert.equal(await page.locator('#app').isVisible(),true);
  // Responsive layout: no horizontal overflow at a phone viewport.
  await page.setViewportSize({width:390,height:844});await page.locator('[data-self-study]').click();
  await page.locator('[data-ss-language="en"]').waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  if(process.env.ADELIA_BROWSER_TEST_ARTIFACT_DIR){
   await fs.mkdir(process.env.ADELIA_BROWSER_TEST_ARTIFACT_DIR,{recursive:true});
   await page.screenshot({path:path.join(process.env.ADELIA_BROWSER_TEST_ARTIFACT_DIR,'self-study-mobile.png'),fullPage:true});
  }
  // Session denial is visible and does not render another user's course.
  const invitation=await page.request.post(url+'/api/teacher/self-study/access/invite',{headers:{Origin:url},data:{account_role:'student',account_id:101}});
  const studentToken=(await invitation.json()).token;
  const parentInvitation=await page.request.post(url+'/api/teacher/self-study/access/invite',{headers:{Origin:url},data:{account_role:'parent',account_id:101}});
  const parentToken=(await parentInvitation.json()).token;
  await context.clearCookies();await page.reload();await page.getByRole('alert').waitFor();
  assert.match(await page.getByRole('alert').innerText(),/Войди в свой кабинет/);
  assert.equal(await page.locator('.ss-unit').count(),0);
  await context.addCookies([{name:'role',value:'student',url}]);
  await page.goto(url+'/app/self-study.html#invite='+studentToken);
  await completeFamilyPlacement(page);
  await page.locator('[data-ss-language="es"]').waitFor();
  assert.equal(await page.locator('[data-ss-language="de"]').count(),0);
  await page.locator('.ss-tools>summary').click();await page.locator('[data-ss-entry]').click();
  await page.locator('[data-entry-form]').waitFor();
  for(const radio of await page.locator('[data-entry-form] input[value="unknown"]').all())await radio.check();
  await page.getByRole('button',{name:'Получить маршрут',exact:true}).click();
  await page.getByRole('button',{name:'Открыть программу',exact:true}).click();
  await page.locator('[data-ss-language="es"]').waitFor();
  assert.match(await page.locator('.ss-primary[data-ss-lesson]').getAttribute('data-ss-lesson'),/^en0-/);
  await page.locator('[data-ss-language="es"]').click();assert.equal(await page.locator('.ss-unit').count(),23);
  await context.clearCookies();await context.addCookies([{name:'role',value:'parent',url}]);
  await page.goto(url+'/app/self-study.html?role=parent#invite='+parentToken);
  await completeFamilyPlacement(page);
  await page.locator('[data-ss-language="en"]').waitFor();
  assert.equal(await page.locator('#studyBack').getAttribute('href'),'/app/parent/');
  await page.locator('.ss-tools>summary').click();await page.locator('[data-ss-settings]').click();
  await page.locator('[data-settings-form]').waitFor();
  await page.locator('input[name=courses][value=en]').uncheck();
  await page.locator('select[name=priority]').selectOption('es');
  await page.locator('select[name=daily_minutes]').selectOption('30');
  await page.locator('input[name=topics][value=travel]').check();
  await page.getByRole('button',{name:'Сохранить и обновить программу',exact:true}).click();
  await page.locator('[data-ss-language="es"]').waitFor();
  assert.equal(await page.locator('[data-ss-language="en"]').count(),0);
  assert.match(await page.locator('#selfStudyRoot').innerText(),/30 мин в день/);
  await page.locator('[data-ss-view=program]').click();await page.locator('.ss-unit[data-ss-lesson="esx-01"]').click();
  await page.getByRole('heading',{name:'Цель и цикл практики',exact:true}).waitFor();
  await page.locator('[data-intensive-writing]').fill('Quiero cambiar la hora.');
  await page.getByText('Черновик и самопроверка сохранены на этом устройстве.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'← К программе',exact:true}).click();
  await page.locator('[data-ss-view=today]').click();await page.locator('[data-day-start="5"]').click();
  await page.locator('[data-day-next]').waitFor();
  await page.locator('[data-day-pause]').click();
  await page.getByRole('heading',{name:'Можно продолжить, когда удобно',exact:true}).waitFor();
  await page.reload();await page.locator('[data-day-resume]').click();
  await page.getByRole('button',{name:'Продолжить',exact:true}).click();
  await page.locator('[data-day-next]').click();
  await page.locator('[data-day-lesson]').waitFor();
  await page.locator('[data-day-next]').click();
  await page.getByText('Сначала выполни задания этого урока и сохрани проверку.',{exact:true}).waitFor();
  await page.locator('[data-day-lesson]').click();
  await page.getByRole('button',{name:'Проверить ответы',exact:true}).waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: teacher launch, budget, dates, drafts, grading, spaced review/reveal recovery, checkpoint drafts/results, history, 3 languages, RTL, XSS, existing-render isolation, navigation, mobile layout and auth denial.');
 }catch(error){
  if(page&&process.env.ADELIA_BROWSER_TEST_ARTIFACT_DIR){
   const dir=process.env.ADELIA_BROWSER_TEST_ARTIFACT_DIR;
   try{await fs.mkdir(dir,{recursive:true});await page.screenshot({path:path.join(dir,'failure.png'),fullPage:true});await fs.writeFile(path.join(dir,'failure.html'),await page.content());await fs.writeFile(path.join(dir,'failure.txt'),String(error)+'\nPage errors: '+JSON.stringify(errors));}catch(artifactError){console.error('Could not save failure artifacts:',artifactError.message);}
  }
  throw error;
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
