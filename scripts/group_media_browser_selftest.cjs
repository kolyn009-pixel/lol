const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out='/tmp/adelia-group-media';fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.ADELIA_CHROMIUM_EXECUTABLE?{executablePath:process.env.ADELIA_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--no-zygote','--single-process']}:{})});try{const page=await browser.newPage();
for(const width of [1440,390]){
 await page.unroute('https://qa.adelia/**');await page.setViewportSize({width,height:950});
 let group={id:7,name:'ЕГЭ · Физика · Группа 1',subject:'PHYSICS',study_goal:'EGE',price_per_lesson:900,max_members:6,min_attendees:3,recruitment_status:'OPEN',chat_mode:'OPEN',members:[{name:'Кирилл',user_id:1,avatar_kind:'PRESET',avatar_value:'student_avatar_03'}],slots:[{weekday:0,start_time:'19:00',duration_minutes:90}],avatar_kind:'PRESET',avatar_value:'group_01'};
 let profile={display_name:'Кирилл',avatar_kind:'PRESET',avatar_value:'student_avatar_03'},messages=[{id:1,sender_name:'Кирилл',sender_role:'STUDENT',avatar_kind:'PRESET',avatar_value:'student_avatar_03',body:'Здравствуйте! Где посмотреть домашнее задание?',created_at:'2026-10-22T10:00:00',mine:false}],failed=false,keys=[],photo;
 await page.route('https://qa.adelia/**',async route=>{const u=new URL(route.request().url()),p=u.pathname;
  if(p==='/api/teacher/group/settings')return route.fulfill({json:{group,timezone:'Europe/Moscow',invite_path:'/app/group-invite.html?invite='+'a'.repeat(43)}});
  if(p==='/api/student/profile')return route.fulfill({json:profile});
  if(p==='/api/teacher/group/chat'){
   if(route.request().method()==='POST'){const b=route.request().postDataJSON();keys.push(b.client_id);if(!failed){failed=true;return route.fulfill({status:500,json:{error:'server_error'}})}messages.push({id:2,mine:true,sender_role:'TEACHER',body:b.body,created_at:'2026-10-22T10:05:00'});return route.fulfill({json:{status:'ok',message_id:2}})}
   return route.fulfill({json:{items:messages}});
  }
  if(p==='/api/teacher/group/avatar'||p==='/api/student/avatar'){const b=route.request().postDataJSON(),result=b.png?{avatar_kind:'CUSTOM',avatar_value:'/api/visual/avatar/'+'c'.repeat(32)}:{avatar_kind:'PRESET',avatar_value:b.avatar_value};if(b.png){photo=b.png;fs.writeFileSync(out+'/browser-avatar.b64',photo)}if(p.includes('/teacher/'))Object.assign(group,result);else Object.assign(profile,result);return route.fulfill({json:{status:'ok',...result}})}
  if(p.startsWith('/api/visual/avatar/'))return route.fulfill({path:path.join(root,'brand/existing-icon.png')});
  if(p==='/app/teacher.html')return route.fulfill({body:fs.readFileSync(path.join(root,'web/teacher.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,''),contentType:'text/html'});
  const file=path.join(root,'web',p.replace(/^\/app\//,''));if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({path:file});return route.fulfill({body:'',status:200});
 });
 await page.goto('https://qa.adelia/app/teacher.html');for(const f of ['avatar_editor.js','teacher_group_chat.js','teacher_group_settings.js'])await page.addScriptTag({url:'/app/'+f});await page.evaluate(()=>window.AdeliaGroupSettings.open(7));
 await page.locator('[data-goto-chat]').click();await page.getByText('Здравствуйте! Где посмотреть домашнее задание?',{exact:true}).waitFor();
 await page.locator('#teacherGroupMessage').fill('Здравствуйте! Домашнее задание уже в материалах группы.');await page.locator('.agw-chat-compose [type=submit]').click();await page.locator('.agw-chat .agw-notice.is-error').waitFor();assert((await page.locator('#teacherGroupMessage').inputValue()).length>0);
 await page.locator('.agw-chat-compose [type=submit]').click();await page.waitForFunction(()=>document.querySelector('#teacherGroupMessage').value==='');assert.equal(keys[0],keys[1]);
 await page.screenshot({path:out+`/chat-${width}.png`,fullPage:true});
 await page.locator('#gsGroupAvatar').click();await page.locator('[data-preset=group_03]').click();await page.locator('.ava-save').click();await page.locator('.ava-overlay').waitFor({state:'detached'});assert.equal(group.avatar_value,'group_03');
 await page.locator('[data-gs-tab=settings]').click();await page.evaluate(()=>{const button=document.createElement('button');button.dataset.editMyAvatar='';button.id='testMyAvatar';button.textContent='Моя аватарка';document.body.appendChild(button);const image=document.createElement('div');image.className='big-avatar';document.body.appendChild(image)});
 await page.locator('#testMyAvatar').click();await page.locator('[data-preset=student_avatar_10]').click();await page.locator('.ava-save').click();await page.locator('.ava-overlay').waitFor({state:'detached'});assert.equal(profile.avatar_value,'student_avatar_10');
 await page.locator('#testMyAvatar').click();const file=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=160;c.height=120;const ctx=c.getContext('2d');ctx.fillStyle='#8c6ed3';ctx.fillRect(0,0,160,120);ctx.fillStyle='#d5bfef';ctx.fillRect(40,10,70,100);return c.toDataURL('image/png').split(',')[1]});
 await page.locator('#avaFile').setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from(file,'base64')});await page.locator('#avaCrop:not([hidden])').waitFor();await page.locator('#avaZoom').fill('1.5');await page.locator('#avaZoom').dispatchEvent('input');await page.screenshot({path:out+`/avatar-${width}.png`,fullPage:true});await page.locator('.ava-save').click();await page.locator('.ava-overlay').waitFor({state:'detached'});assert(photo);assert.equal(profile.avatar_kind,'CUSTOM');assert.equal(await page.locator('.big-avatar img').count(),1);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));console.log(`GROUP_MEDIA_BROWSER_${width}=OK`);
 await page.evaluate(()=>document.querySelector('#testMyAvatar').remove());
}
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
