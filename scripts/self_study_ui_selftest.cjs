/* Browser journeys against the actual stage-1 API and disposable SQLite. */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
const path=require('node:path');
const readline=require('node:readline');

(async()=>{
 const server=spawn('python',[path.join(__dirname,'self_study_selftest.py'),'--serve'],{stdio:['ignore','pipe','pipe']});
 const ready=new Promise((resolve,reject)=>{const lines=readline.createInterface({input:server.stdout});lines.once('line',s=>{try{resolve(JSON.parse(s));}catch(e){reject(e);}});server.once('error',reject);server.once('exit',c=>reject(Error('Fixture exited '+c)));});
 let browser;
 try{
  const {port}=await ready,url=`http://127.0.0.1:${port}`;
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext();await context.addCookies([{name:'role',value:'teacher',url}]);
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url+'/teacher/');await page.locator('[data-self-study]').click();
  await page.locator('[data-ss-language="en"]').waitFor();
  assert.equal(await page.locator('.ss-unit').count(),12);
  assert.equal(await page.locator('#app').isVisible(),false);
  await page.locator('[data-ss-budget="180"]').click();
  await page.waitForFunction(()=>document.querySelector('[data-ss-budget="180"]')?.getAttribute('aria-pressed')==='true');
  assert.match(await page.locator('#selfStudyRoot').innerText(),/120 мин в день/);
  await page.locator('summary').filter({hasText:'Настроить даты'}).click();
  await page.locator('[name=en]').fill('2027-09-15');await page.getByRole('button',{name:'Сохранить даты'}).click();
  await page.waitForFunction(()=>document.querySelector('#selfStudyRoot')?.textContent.includes('2027-09-15'));
  await page.locator('.ss-primary[data-ss-lesson]').click();
  await page.locator('[name=d0]').fill('used to');await page.locator('[data-ss-save]').click();
  await page.getByText('Ответы сохранены на сервере.',{exact:false}).waitFor();
  // Existing teacher renderers can run without destroying the lesson workspace.
  await page.evaluate(()=>document.querySelector('#app').innerHTML='Поздний ответ рабочего кабинета');
  assert.equal(await page.locator('[name=d0]').inputValue(),'used to');
  await page.reload();await page.locator('[data-ss-language="en"]').waitFor();
  await page.locator('.ss-primary[data-ss-lesson]').click();
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
  await page.locator('[data-ss-language="de"]').click();assert.equal(await page.locator('.ss-unit').count(),8);
  await page.locator('[data-ss-language="fa"]').click();assert.equal(await page.locator('.ss-unit').count(),8);
  await page.locator('.ss-primary[data-ss-lesson]').click();
  assert.equal(await page.locator('.ss-reading').getAttribute('dir'),'rtl');
  // Raw content is displayed as text, never executable markup.
  const attack='<img src=x onerror="window.__xss=1">';
  await page.locator('[name=d0]').fill(attack);await page.locator('[data-ss-save]').click();
  await page.getByText('Ответы сохранены на сервере.',{exact:false}).waitFor();
  await page.getByRole('button',{name:'К программе',exact:false}).click();
  await page.locator('[data-ss-language="fa"]').waitFor();await page.locator('.ss-primary[data-ss-lesson]').click();
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
  // Session denial is visible and does not render another user's course.
  await context.clearCookies();await page.reload();await page.getByRole('alert').waitFor();
  assert.match(await page.getByRole('alert').innerText(),/Войди в кабинет/);
  assert.equal(await page.locator('.ss-unit').count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS: teacher launch, budget, dates, draft restore, grading, history, 3 languages, RTL, XSS, existing-render isolation, navigation, mobile layout and auth denial.');
 }finally{await browser?.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
