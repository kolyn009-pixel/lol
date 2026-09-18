'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=__dirname,repo=path.resolve(root,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const readRepo=p=>fs.readFileSync(path.join(repo,p),'utf8');
const pkg=JSON.parse(read('package.json'));
const files={
  bootstrap:read('bootstrap.js'),main:read('main.js'),preload:read('preload.js'),workspace:read('lesson_workspace.js'),
  ux:read('desktop_ux.js'),layout:read('lesson_layout.js'),role:read('role_startup.js'),system:read('system_polish.js'),
  network:read('network_ux.js'),iconSync:read('generate_assets.js'),startJs:read('start.js'),startHtml:read('start.html'),startCss:read('start.css'),offline:read('offline.html')
};
const web={
  student:readRepo('web/index.html'),teacher:readRepo('web/teacher.html'),parent:readRepo('web/parent/index.html'),landing:readRepo('web/landing.js'),
  individual:readRepo('web/teacher_lesson_flow.js'),group:readRepo('web/teacher_group_live12.js'),event:readRepo('web/teacher_event_live13.js'),
  telemostSettings:readRepo('web/teacher_telemost_settings.js'),lessonUi:readRepo('web/desktop_lesson_workspace.js'),lessonUiCss:readRepo('web/desktop_lesson_workspace.css'),desktopManifest:read('bundled_ui_manifest.js'),parentManifest:readRepo('web/parent/manifest.webmanifest')
};
let failed=false;
function check(ok,label){console.log(`${ok?'OK':'FAIL'} ${label}`);if(!ok)failed=true}
function parseJs(name,source){try{new vm.Script(source,{filename:name});check(true,`syntax ${name}`)}catch(e){console.error(e.stack||e);check(false,`syntax ${name}`)}}
for(const [n,s] of Object.entries({bootstrap:files.bootstrap,main:files.main,preload:files.preload,workspace:files.workspace,desktop_ux:files.ux,lesson_layout:files.layout,role_startup:files.role,system_polish:files.system,network_ux:files.network,generate_assets:files.iconSync,start:files.startJs,teacher_lesson_flow:web.individual,teacher_group_live12:web.group,teacher_event_live13:web.event,teacher_telemost_settings:web.telemostSettings}))parseJs(`${n}.js`,s);

check(pkg.version==='0.2.0','desktop package version');
check(pkg.main==='bootstrap.js','desktop bootstrap entry');
check(pkg.build?.appId==='ru.adeliatutor.desktop','stable app id');
check(pkg.build?.asar===true,'asar enabled');
check(pkg.devDependencies?.electron==='38.0.0','Electron pinned');
check(pkg.devDependencies?.['electron-builder']==='26.0.12','electron-builder pinned');
check(pkg.dependencies?.['electron-updater']==='6.6.2','electron-updater pinned');
check(pkg.build.publish?.[0]?.url==='https://adeliatutor.ru/desktop-updates/','trusted update endpoint');
check(pkg.build.protocols?.[0]?.schemes?.includes('adelia'),'adelia deep-link protocol registered');
check(pkg.build.win?.target?.includes('nsis'),'Windows NSIS target');
check(pkg.build.mac?.target?.includes('dmg')&&pkg.build.mac?.target?.includes('zip'),'macOS DMG + ZIP targets');
check(pkg.scripts?.['sync:icon']==='node generate_assets.js','canonical icon sync script');
check(pkg.scripts?.selftest?.includes('npm run sync:icon'),'selftest syncs canonical icon');
check(pkg.scripts?.['dist:win']?.includes('npm run sync:icon'),'Windows build syncs canonical icon');
check(pkg.scripts?.['dist:mac:arm64']?.includes('--arm64'),'macOS Apple Silicon build');
check(pkg.scripts?.['dist:mac:x64']?.includes('--x64'),'macOS Intel build');
check(pkg.build.nsis?.createDesktopShortcut===true,'Windows desktop shortcut');
check(pkg.build.dmg?.contents?.some(x=>x.path==='/Applications'),'macOS drag-to-Applications installer');
for(const f of ['bootstrap.js','system_polish.js','network_ux.js','offline.html','lesson_workspace.js','desktop_ux.js','lesson_layout.js','role_startup.js','start.html','start.css','start.js','main.js','preload.js','package.json','build/icon.png'])check(pkg.build.files.includes(f),`packaged ${f}`);
check(files.iconSync.includes('https://adeliatutor.ru/assets/icons/adelia-icon-512.png'),'desktop uses canonical server icon');
check(!files.iconSync.includes('roundedRect'),'desktop icon is not generated artwork');

check(files.main.includes('https://adeliatutor.ru/app/'),'desktop opens Adelia origin');
check(/contextIsolation\s*:\s*true/.test(files.main),'context isolation');
check(/nodeIntegration\s*:\s*false/.test(files.main),'node integration disabled');
check(/sandbox\s*:\s*true/.test(files.main),'renderer sandbox');
check(files.main.includes('https://telemost.yandex.ru'),'Telemost allowlist');
check(files.main.includes('myboard.io')&&files.main.includes('trustedBoard'),'board HTTPS allowlist');
check(files.main.includes('requestSingleInstanceLock'),'single-instance desktop app');
check(files.main.includes('new Tray('),'system tray');
check(files.main.includes('closeToTray'),'configurable close-to-tray');
check(files.main.includes('mainWindowBounds')&&files.main.includes('visibleBounds'),'main window geometry persists safely');
check(files.main.includes('closeLessonWindows(true)'),'lesson workspace returns focus to Adelia');
check(files.preload.includes('contextBridge'),'minimal preload bridge');
check(files.preload.includes('openLessonTool')&&files.preload.includes('endLessonWorkspace'),'lesson workspace IPC exposed');
check(files.main.includes("ipcMain.handle('adelia:lesson-tool'")&&files.main.includes("ipcMain.handle('adelia:end-lesson-workspace'"),'lesson workspace IPC handled');
check(files.workspace.includes('function isStudentCabinetUrl')&&files.workspace.includes("u.pathname.startsWith('/app/parent/')"),'desktop polling is scoped to student cabinet');

check(files.bootstrap.includes("require('./system_polish').install()"),'native platform polish installed');
check(files.bootstrap.includes("require('./network_ux').install()"),'network UX installed');
check(files.bootstrap.includes("require('./lesson_workspace').install()"),'lesson workspace installed');
check(files.bootstrap.includes("require('./desktop_ux').install()"),'desktop UX installed');
check(files.bootstrap.includes("require('./lesson_layout').install()"),'lesson layout installed');
check(files.bootstrap.includes("require('./role_startup').install()"),'role chooser installed');

check(files.role.includes("loadFile(path.join(__dirname,'start.html'))"),'role chooser loads packaged start screen');
check(files.role.includes("'/api/auth/teacher/code'"),'teacher code login wired');
check(files.role.includes("APP_ORIGIN+'/app/parent/'"),'parent cabinet wired');
check(files.role.includes("APP_ORIGIN+'/api/auth/me'")&&files.role.includes("role==='teacher'")&&files.role.includes("role==='parent'")&&files.role.includes("role==='student'"),'authenticated desktop role is restored');
check(files.startJs.includes('teacherLogin')&&files.startJs.includes('openStudentLogin')&&files.startJs.includes('openParentCabinet'),'role actions wired');
check(files.startHtml.includes('./build/icon.png')&&files.startHtml.includes('start.js')&&files.startHtml.includes('start.css'),'branded start assets linked');
check(files.startCss.includes('.role')&&files.startCss.includes('.intro'),'start screen styles present');
check(pkg.build.files.includes('bundled_ui_manifest.js'),'desktop bundled UI manifest packaged');
check(files.startCss.includes('prefers-reduced-motion'),'start screen respects reduced motion');
check(files.offline.includes('Нет подключения')&&files.offline.includes('Аделия сама попробует восстановить соединение'),'branded offline screen');
check(files.network.includes("loadFile(offlineFile())")&&files.network.includes('setInterval'),'offline reconnect loop');
check(files.network.includes("removeAllListeners('update-available')")&&files.network.includes('downloadUpdate'),'polished updater flow');
check(files.system.includes('setUserTasks'),'Windows quick actions');
check(files.system.includes('app.dock.setMenu'),'macOS dock actions');
check(files.system.includes('download-progress')&&files.system.includes('setProgressBar'),'native update progress');
check(files.ux.includes("HOTKEY = 'CommandOrControl+Shift+A'"),'global Adelia hotkey');
check(files.ux.includes('setOverlayIcon'),'Windows unread badge');
check(files.layout.includes("'together','board-focus','mini-video','hide-video'"),'lesson layout modes');
check(web.lessonUi.includes('setLessonLayout')&&web.lessonUi.includes('toggleLessonVideo')&&web.lessonUi.includes('endLessonWorkspace'),'desktop lesson controller actions');
check(web.lessonUi.includes('dual-screen')&&web.lessonUi.includes('board-focus')&&web.lessonUi.includes('mini-video'),'desktop lesson controller modes');
check(web.lessonUiCss.includes('.adelia-desktop-lessonbar'),'desktop lesson controller styles');
check(web.desktopManifest.includes('desktop_lesson_workspace.css')&&web.desktopManifest.includes('desktop_lesson_workspace.js'),'lesson controller bundled into desktop UI');

check(web.individual.includes("openLessonTool('meeting'")&&web.individual.includes("openLessonTool('board'")&&web.individual.includes('endLessonWorkspace()'),'individual desktop lifecycle');
check(web.group.includes("openLessonTool('meeting'")&&web.group.includes("openLessonTool('board'")&&web.group.includes('endLessonWorkspace()'),'group desktop lifecycle');
check(web.event.includes("openLessonTool('meeting'")&&web.event.includes("openLessonTool('board'")&&web.event.includes('endLessonWorkspace()'),'event desktop lifecycle');
check(web.individual.includes('started_at:r.started_at')&&web.individual.includes('Таймер начнётся после прихода ученика'),'individual start does not imply factual start');
check(web.group.includes("if(status==='STARTED')return['Доступ открыт — ждём первого ученика'")&&web.group.includes('mark_actual_start')===false,'group UI separates access from factual timer');
check(web.event.includes("e.status==='IN_PROGRESS'?'Доступ открыт — ждём первого ученика'")&&web.event.includes('Фактический таймер ещё не запущен'),'event UI separates access from factual timer');
for(const [name,source] of Object.entries({individual:web.individual,group:web.group,event:web.event,telemost_settings:web.telemostSettings}))check(!source.includes('MutationObserver'),`no persistent MutationObserver in ${name}`);

check(web.student.includes('/app/student_clean.css'),'student clean shell linked');
check(web.teacher.includes('/app/teacher_clean.css')&&web.teacher.includes('/app/teacher_clean7.css'),'teacher clean7 shell linked');
check(web.parent.includes('/app/parent/parent_clean.css'),'parent clean shell linked');
check(web.landing.includes('Adelia-latest-windows-x64.exe')&&web.landing.includes('Adelia-latest-macos-arm64.dmg')&&web.landing.includes('Adelia-latest-macos-x64.dmg'),'stable desktop download aliases linked');
const parentManifest=JSON.parse(web.parentManifest);
check(parentManifest.name.startsWith('Аделия'),'parent PWA branded Adelia');
check(parentManifest.icons?.some(x=>x.src==='/adelia-favicon-32.png'&&x.sizes==='32x32'),'parent canonical 32 icon');
check(parentManifest.icons?.some(x=>x.src==='/adelia-apple-touch-icon-180.png'&&x.sizes==='180x180'),'parent canonical 180 icon');
check(!web.parentManifest.includes('192x192')&&!web.parentManifest.includes('512x512'),'parent manifest does not fake icon sizes');

if(failed)process.exit(1);
console.log('Desktop release selftest passed.');
