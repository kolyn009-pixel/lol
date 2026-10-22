const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const html=fs.readFileSync(path.join(__dirname,'../web/desktop_install.html'),'utf8');
(async()=>{const browser=await chromium.launch({headless:true,...(process.env.ADELIA_CHROMIUM_EXECUTABLE?{executablePath:process.env.ADELIA_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-gpu','--disable-software-rasterizer','--no-zygote','--single-process']}:{})});try{const page=await browser.newPage({reducedMotion:'reduce'});page.setDefaultTimeout(10000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.route('https://qa.adelia/**',async route=>{if(new URL(route.request().url()).pathname==='/desktop-updates/')return route.fulfill({body:html,contentType:'text/html; charset=utf-8'});const icon=path.join(__dirname,'../brand/existing-icon.png');return route.fulfill({path:icon})});
for(const [width,platform,touch] of [[1440,'Win32',0],[1024,'MacIntel',0],[390,'MacIntel',5],[320,'Linux armv8l',2]]){
 await page.addInitScript(({platform,touch})=>{Object.defineProperty(navigator,'platform',{get:()=>platform,configurable:true});Object.defineProperty(navigator,'maxTouchPoints',{get:()=>touch,configurable:true});Object.defineProperty(navigator,'userAgentData',{get:()=>undefined,configurable:true})},{platform,touch});
 await page.setViewportSize({width,height:950});await page.goto('https://qa.adelia/desktop-updates/');assert.equal(await page.locator('a[download]').count(),3);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 if(width===1440)assert((await page.locator('#deviceHint').textContent()).includes('Windows'));
 if(width===1024)assert((await page.locator('#deviceHint').textContent()).includes('проверьте тип процессора'));
 if(width===390)assert((await page.locator('#deviceHint').textContent()).includes('мобильный кабинет'));
 await page.screenshot({path:`/tmp/adelia-install-guide-${width}.png`,fullPage:false});await page.getByRole('link',{name:'Как установить на Mac',exact:true}).first().click();assert.equal(await page.evaluate(()=>location.hash),'#mac');await page.getByText('Mac не даёт открыть приложение',{exact:true}).click();assert(await page.getByText('Подробная инструкция Apple ↗',{exact:true}).isVisible());assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.evaluate(()=>{document.documentElement.style.scrollBehavior='auto';scrollTo(0,0)});console.log(`INSTALL_GUIDE_BROWSER_${width}=OK`);
}
assert.deepEqual(errors,[]);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
