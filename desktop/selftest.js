'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm');
const root=__dirname,repo=path.resolve(root,'..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const readRepo=p=>fs.readFileSync(path.join(repo,p),'utf8');
const publishScript=readRepo('scripts/desktop_update_publish.sh'),rollbackScript=readRepo('scripts/desktop_update_rollback.sh'),releaseManager=readRepo('scripts/desktop_release_manager.sh'),releaseSetRollback=readRepo('scripts/desktop_release_set_rollback.sh'),nginxUpdates=read('nginx-desktop-updates.conf');
const pkg=JSON.parse(read('package.json'));
const files={
  bootstrap:read('bootstrap.js'),main:read('main.js'),preload:read('preload.js'),workspace:read('lesson_workspace.js'),workspaceShell:read('workspace_shell.js'),bundledUi:read('bundled_ui.js'),
  ux:read('desktop_ux.js'),layout:read('lesson_layout.js'),role:read('role_startup.js'),system:read('system_polish.js'),
  network:read('network_ux.js'),diagnostics:read('diagnostics.js'),report:read('report.js'),reportPreload:read('report_preload.js'),reportHtml:read('report.html'),deviceCheck:read('device_check.js'),deviceCheckPreload:read('device_check_preload.js'),deviceCheckHtml:read('device_check.html'),about:read('about.js'),aboutPreload:read('about_preload.js'),aboutHtml:read('about.html'),iconSync:read('generate_assets.js'),startJs:read('start.js'),startHtml:read('start.html'),startCss:read('start.css'),offline:read('offline.html')
};
const web={
  app:readRepo('web/app.js'),student:readRepo('web/index.html'),teacher:readRepo('web/teacher.html'),parent:readRepo('web/parent/index.html'),landing:readRepo('web/landing.js'),
  individual:readRepo('web/teacher_lesson_flow.js'),group:readRepo('web/teacher_group_live12.js'),event:readRepo('web/teacher_event_live13.js'),
  telemostSettings:readRepo('web/teacher_telemost_settings.js'),teacherDashboard:readRepo('web/teacher_dashboard_week.js'),pwa:readRepo('web/pwa.js'),studentSw:readRepo('web/service-worker.js'),lessonUi:readRepo('web/desktop_lesson_workspace.js'),lessonUiCss:readRepo('web/desktop_lesson_workspace.css'),prelessonUi:readRepo('web/desktop_prelesson.js'),prelessonCss:readRepo('web/desktop_prelesson.css'),desktopManifest:read('bundled_ui_manifest.js'),parentManifest:readRepo('web/parent/manifest.webmanifest')
};
let failed=false;
function check(ok,label){console.log(`${ok?'OK':'FAIL'} ${label}`);if(!ok)failed=true}
function parseJs(name,source){try{new vm.Script(source,{filename:name});check(true,`syntax ${name}`)}catch(e){console.error(e.stack||e);check(false,`syntax ${name}`)}}
for(const [n,s] of Object.entries({bootstrap:files.bootstrap,main:files.main,preload:files.preload,workspace:files.workspace,desktop_ux:files.ux,lesson_layout:files.layout,role_startup:files.role,system_polish:files.system,network_ux:files.network,diagnostics:files.diagnostics,report:files.report,report_preload:files.reportPreload,device_check:files.deviceCheck,device_check_preload:files.deviceCheckPreload,about:files.about,about_preload:files.aboutPreload,generate_assets:files.iconSync,start:files.startJs,teacher_lesson_flow:web.individual,teacher_group_live12:web.group,teacher_event_live13:web.event,teacher_telemost_settings:web.telemostSettings,teacher_dashboard_week:web.teacherDashboard,pwa:web.pwa,student_service_worker:web.studentSw}))parseJs(`${n}.js`,s);

check(pkg.version==='0.3.0-beta.3','desktop beta package version');
check(pkg.main==='bootstrap.js','desktop bootstrap entry');
check(pkg.build?.appId==='ru.adeliatutor.desktop','stable app id');
check(pkg.build?.asar===true,'asar enabled');
check(pkg.devDependencies?.electron==='38.0.0','Electron pinned');
check(pkg.devDependencies?.['electron-builder']==='26.0.12','electron-builder pinned');
check(pkg.dependencies?.['electron-updater']==='6.6.2','electron-updater pinned');
check(pkg.build.publish?.[0]?.url==='https://adeliatutor.ru/desktop-updates/beta/'&&pkg.build.publish?.[0]?.channel==='beta','isolated trusted beta build endpoint');
check(pkg.build.protocols?.[0]?.schemes?.includes('adelia'),'adelia deep-link protocol registered');
check(pkg.build.win?.target?.includes('nsis'),'Windows NSIS target');
check(pkg.build.mac?.target?.includes('dmg')&&pkg.build.mac?.target?.includes('zip'),'macOS DMG + ZIP targets');
check(pkg.build.mac?.icon==='build/icon.icns','macOS package uses native ICNS');
check(pkg.build.win?.icon==='build/icon.ico','Windows package uses native ICO');
check(pkg.build.nsis?.installerIcon==='build/icon.ico'&&pkg.build.nsis?.uninstallerIcon==='build/icon.ico','Windows installer uses native ICO');
check(pkg.scripts?.['sync:icon']==='node generate_assets.js','canonical icon sync script');
check(pkg.scripts?.selftest?.includes('npm run sync:icon'),'selftest syncs canonical icon');
check(pkg.scripts?.['dist:win']?.includes('npm run sync:icon'),'Windows build syncs canonical icon');
check(pkg.scripts?.['dist:mac:arm64']?.includes('--arm64'),'macOS Apple Silicon build');
check(pkg.scripts?.['dist:mac:x64']?.includes('--x64'),'macOS Intel build');
check(pkg.build.nsis?.createDesktopShortcut===true,'Windows desktop shortcut');
check(pkg.build.nsis?.deleteAppDataOnUninstall===false,'Windows uninstall preserves local preferences and session data');
check(pkg.build.nsis?.runAfterFinish===true&&pkg.build.nsis?.differentialPackage===true,'Windows installer update-friendly behavior');
check(pkg.build.dmg?.contents?.some(x=>x.path==='/Applications'),'macOS drag-to-Applications installer');
for(const f of ['bootstrap.js','system_polish.js','network_ux.js','offline.html','lesson_workspace.js','workspace_shell.js','bundled_ui.js','diagnostics.js','report_preload.js','report.html','report.css','report.js','device_check_preload.js','device_check.html','device_check.css','device_check.js','about_preload.js','about.html','about.css','about.js','desktop_ux.js','lesson_layout.js','role_startup.js','start.html','start.css','start.js','main.js','preload.js','package.json','build/icon.png'])check(pkg.build.files.includes(f),`packaged ${f}`);
check(files.iconSync.includes("brand=path.join(root,'brand','adelia_icon')")&&files.iconSync.includes("source=path.join(brand,'adelia-icon-512.png')"),'desktop uses repository canonical brand icon');
check(!files.iconSync.includes('https.get')&&!files.iconSync.includes('ADELIA_DESKTOP_ICON_URL'),'desktop icon sync is offline and cannot fall back to stale server artwork');
check(files.iconSync.includes('resizeSquare(canonical,1024)')&&!files.iconSync.includes('removeConnectedOuterBackground'),'desktop native icon preserves exact canonical artwork without alternate background stripping');
check(files.iconSync.includes('png2icons.createICNS')&&files.iconSync.includes('png2icons.createICO'),'native platform icon assets generated');
check(files.bundledUi.includes("logo.dataset.adeliaDesktopBrand='canonical'")&&files.bundledUi.includes("path.join(__dirname,'build','icon-macos.png')")&&files.bundledUi.includes('data:image/png;base64'),'teacher desktop shell uses packaged transparent native logo');

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
check(files.main.includes("persist:adelia-device-check")&&files.main.includes('deviceCheckMediaAllowed'),'device check uses isolated media partition');
check(files.main.includes("ipcMain.handle('adelia:about-info'")&&files.main.includes("ipcMain.handle('adelia:about-check-updates'")&&files.preload.includes('openAbout'),'desktop release center IPC wired');
check(files.main.includes("status:'downloading'")&&files.main.includes("status:'downloaded'")&&files.main.includes('buildSha()'),'desktop update state and build identity');
check(files.main.includes("UPDATE_CHANNEL")&&files.main.includes("UPDATE_TARGET")&&files.main.includes("desktop-updates/${UPDATE_CHANNEL}/${UPDATE_TARGET}/")&&files.main.includes("autoUpdater.allowPrerelease=UPDATE_CHANNEL==='beta'"),'explicit channel and platform updater isolation');
check(publishScript.includes('immutable release already exists')&&publishScript.includes('mv -Tf')&&publishScript.includes('HTTP_RELEASE_METADATA=OK'),'atomic desktop update publisher');
check(rollbackScript.includes('explicit release id required')&&rollbackScript.includes('mv -Tf')&&rollbackScript.includes('HTTP_ROLLBACK_METADATA=OK'),'explicit desktop update rollback');
check(releaseManager.includes('PREFLIGHT ALL THREE BUNDLES')&&releaseManager.includes('release-set.json')&&releaseManager.includes('AUTO_ROLLBACK_TO=')&&releaseManager.includes('DESKTOP_RELEASE_MANAGER=PASS'),'atomic three-platform release manager');
check(releaseSetRollback.includes('explicit release-set id required')&&releaseSetRollback.includes('ROLLBACK_VERIFY_RESTORED=')&&releaseSetRollback.includes('DESKTOP_RELEASE_SET_ROLLBACK=PASS'),'atomic whole-release rollback');
check(nginxUpdates.includes('win-x64|macos-arm64|macos-x64')&&nginxUpdates.includes('One channel symlink switches all three'),'atomic release-set nginx policy');
check(files.about.includes('checkUpdates')&&files.about.includes('installUpdate')&&files.about.includes('onUpdateState'),'release center update actions');
check(files.aboutPreload.includes('adelia:about-info')&&files.aboutPreload.includes('adelia:about-update-state'),'release center minimal preload');
check(files.aboutHtml.includes('Проверить обновления')&&files.aboutHtml.includes('Перезапустить и обновить'),'release center UI present');
check(files.diagnostics.includes('MAX_BYTES = 512 * 1024')&&files.diagnostics.includes('uncaughtExceptionMonitor')&&files.diagnostics.includes('render_process_gone'),'bounded local crash diagnostics');
check(files.diagnostics.includes('session-open.json')&&files.diagnostics.includes('unclean_previous_session_detected')&&files.diagnostics.includes('markSessionClean'),'unclean-exit recovery marker');
check(files.diagnostics.includes('Аделия восстановилась после сбоя')&&files.diagnostics.includes('Сохранить отчёт'),'post-crash diagnostics offer');
check(files.diagnostics.includes("'[redacted]'")&&files.diagnostics.includes('[email-redacted]')&&files.diagnostics.includes('sanitizeData'),'diagnostic redaction rules');
check(files.diagnostics.includes("ipcMain.handle('adelia:report-export'")&&files.reportPreload.includes('adelia:report-export'),'problem report export IPC isolated');
check(files.reportHtml.includes('содержимое чатов')&&files.reportHtml.includes('Токены')&&files.reportHtml.includes('Сохранить отчёт'),'problem report privacy disclosure');
check(files.main.includes('Сообщить о проблеме')&&files.main.includes("require('./diagnostics').openReportWindow()"),'problem report available from tray');
check(files.main.includes("ipcMain.handle('adelia:device-check'")&&files.preload.includes('openDeviceCheck'),'device check IPC wired');
check(files.deviceCheck.includes('getUserMedia')&&files.deviceCheck.includes('enumerateDevices')&&files.deviceCheck.includes('createAnalyser'),'real camera and microphone diagnostics');
check(files.deviceCheckPreload.includes('device-check-complete')&&files.deviceCheckPreload.includes('device-check-cancel')&&files.deviceCheckPreload.includes('contextBridge'),'device check preload is minimal');
check(files.deviceCheckHtml.includes('cameraSelect')&&files.deviceCheckHtml.includes('micSelect'),'device selectors present');
check(pkg.build.mac?.extendInfo?.NSCameraUsageDescription&&pkg.build.mac?.extendInfo?.NSMicrophoneUsageDescription,'macOS camera and microphone usage descriptions');
check(files.preload.includes('contextBridge'),'minimal preload bridge');
check(files.preload.includes('openLessonTool')&&files.preload.includes('endLessonWorkspace'),'lesson workspace IPC exposed');
check(files.main.includes("ipcMain.handle('adelia:lesson-tool'")&&files.main.includes("ipcMain.handle('adelia:end-lesson-workspace'"),'lesson workspace IPC handled');
check(files.workspace.includes('function isStudentCabinetUrl')&&files.workspace.includes("u.pathname.startsWith('/app/parent/')"),'desktop polling is scoped to student cabinet');

check(files.bootstrap.includes("require('./diagnostics').install()"),'privacy-safe diagnostics installed before runtime');
check(files.bootstrap.includes("require('./system_polish').install()"),'native platform polish installed');
check(files.bootstrap.includes("require('./network_ux').install()"),'network UX installed');
check(files.bootstrap.includes("require('./lesson_workspace').install()"),'lesson workspace installed');
check(files.bootstrap.includes("require('./desktop_ux').install()"),'desktop UX installed');
check(files.bootstrap.includes("require('./lesson_layout').install()"),'lesson layout installed');
check(files.bootstrap.includes("require('./role_startup').install()"),'role chooser installed');

check(files.role.includes("loadFile(path.join(__dirname,'start.html'))"),'role chooser loads packaged start screen');
check(files.role.includes("'/api/auth/teacher/code'"),'teacher code login wired');
check(files.role.includes("APP_ORIGIN+'/app/parent/'"),'parent cabinet wired');
check(files.role.includes("APP_ORIGIN+'/app/teacher.html'"),'desktop teacher opens canonical document without redirect');
check(web.pwa.includes("location.pathname==='/app/teacher.html'"),'PWA runtime recognizes canonical teacher document');
check(web.studentSw.includes("url.pathname==='/app/teacher.html'"),'student service worker never intercepts canonical teacher document');
check((web.teacher.includes('teacherBootRetry')||web.teacher.includes('AdeliaTeacherBootGuard')),'teacher boot watchdog prevents endless loading state');
check(files.workspaceShell.includes("u.pathname.startsWith('/teacher')")&&files.workspaceShell.includes("u.pathname==='/app/teacher.html'")&&files.bundledUi.includes("pathname.startsWith('/teacher')")&&files.bundledUi.includes("pathname==='/app/teacher.html'"),'canonical teacher routes remain desktop teacher role');
check(files.role.includes("APP_ORIGIN+'/api/auth/me'")&&files.role.includes("role==='teacher'")&&files.role.includes("role==='parent'")&&files.role.includes("role==='student'"),'authenticated desktop role is restored');
check(files.main.includes("createWindow(startupDeep ? parseDeepLink(startupDeep).target : null)")&&files.main.includes("if (!startupDeep) await restoreMainRole()")&&files.main.includes("win.loadFile(path.join(__dirname,'start.html'))"),'desktop startup is role-gated before remote cabinet load');
check(files.network.includes("require('./role_startup').restoreAuthenticatedRole()")&&!files.network.includes("win.loadURL(APP_URL).catch"),'desktop reconnect restores authenticated role instead of forcing student cabinet');
check(files.startJs.includes('teacherLogin')&&files.startJs.includes('openStudentLogin')&&files.startJs.includes('openParentCabinet'),'role actions wired');
check(files.startJs.includes("FIRST_RUN_KEY='adelia.desktop.welcome.v1'")&&files.startJs.includes('welcomeContinue'),'first-run welcome is one-time');
check(files.startJs.includes('проверить камеру и звук')&&files.startJs.includes('технический отчёт'),'first-run explains lesson readiness and support');
check(files.startHtml.includes('./build/icon.png')&&files.startHtml.includes('start.js')&&files.startHtml.includes('start.css'),'branded start assets linked');
check(files.startCss.includes('.role')&&files.startCss.includes('.intro'),'start screen styles present');
check(pkg.build.files.includes('bundled_ui_manifest.js'),'desktop bundled UI manifest packaged');
check(files.bundledUi.includes("catch(()=>false)")&&files.bundledUi.includes("adelia-desktop-")&&files.bundledUi.includes("did-navigate-in-page")&&files.bundledUi.includes("setTimeout(run,900)"),'desktop bundled UI injection retries and marks role only after load');
check(readRepo('web/desktop_teacher_app.css').includes('html.adelia-desktop-teacher')&&readRepo('web/desktop_teacher_app.css').includes('grid-template-areas:none!important'), 'teacher desktop compact workspaces are marker-scoped');
check(!web.desktopManifest.includes('desktop_teacher_density.js')&&web.desktopManifest.includes('desktop_workspace_v3.js'),'canonical desktop workspace replaces density runtime');
check(web.desktopManifest.includes('teacher_groups.js')&&web.desktopManifest.includes('teacher_groups_polish.css')&&web.desktopManifest.includes('teacher_health.js')&&web.desktopManifest.includes('teacher_health.css'),'rebuilt groups and health workspaces are packaged for teacher desktop');
check(web.desktopManifest.includes('teacher_messages_stage10.js')&&web.desktopManifest.includes('teacher_messages_polish.css'),'redesigned teacher messenger is packaged for teacher desktop');
check(web.desktopManifest.includes('teacher_students_clean8.js')&&web.desktopManifest.includes('teacher_students_clean8.css')&&web.desktopManifest.includes('teacher_students_polish.css'),'polished teacher student workspace is packaged for teacher desktop');
check(web.desktopManifest.includes('student_stage1_home.js')&&web.desktopManifest.includes('student_stage4_workspace.js')&&web.desktopManifest.includes('student_clean.css'),'polished student workspace is packaged for student desktop');
check(web.desktopManifest.includes('parent/parent_v5.js')&&web.desktopManifest.includes('parent/parent_v5.css')&&web.desktopManifest.includes('desktop_parent_app.css'),'polished parent workspace is packaged for parent desktop');
check(web.desktopManifest.includes('teacher_lesson_context.js')&&web.desktopManifest.includes('teacher_lesson_context.css')&&web.desktopManifest.includes('teacher_post_lesson.js'),'redesigned teacher lesson workspace and post-lesson flow are packaged for teacher desktop');
check(files.system.includes("path.join(__dirname, 'build', 'icon-macos.png')")&&!files.system.includes("path.join(__dirname, 'build', 'icon.png')"),'macOS runtime Dock uses transparent native icon');
check(readRepo('web/desktop_teacher_density.js').includes('.health-card:not(.health-card-primary)')&&readRepo('web/desktop_teacher_density.js').includes('.health-card-primary,.v4-page-head'),'dark primary cards keep light text after runtime contrast pass');
check(readRepo('web/desktop_teacher_density.js').includes('data-adelia-desktop-density')||readRepo('web/desktop_teacher_density.js').includes('adeliaDesktopDensity'),'teacher density runtime leaves diagnostic marker');
check(readRepo('web/desktop_teacher_density.js').includes('MutationObserver')&&readRepo('web/desktop_teacher_density.js').includes("setProperty(prop,val,'important')"),'teacher density runtime survives SPA rerenders');
check(readRepo('web/desktop_teacher_app.css').includes('color:#202538!important')&&readRepo('web/desktop_teacher_app.css').includes('font-size:17px!important'),'teacher desktop contrast system covers dark heroes and light work cards');
check(readRepo('web/desktop_teacher_density.js').includes("linear-gradient(135deg,#242943,#343966)")&&readRepo('web/desktop_teacher_density.js').includes("rgba(255,255,255,.82)")&&readRepo('web/desktop_teacher_density.js').includes("#211d2a"),'teacher desktop runtime reapplies readable contrast after rerenders');

check(files.startCss.includes('prefers-reduced-motion'),'start screen respects reduced motion');
check(files.offline.includes('Нет подключения')&&files.offline.includes('Аделия продолжит проверять соединение')&&files.offline.includes('Проверить подключение'),'branded offline screen');
check(files.network.includes("loadFile(offlineFile())")&&files.network.includes('setInterval'),'offline reconnect loop');
check(files.network.includes("removeAllListeners('update-available')")&&files.network.includes('downloadUpdate'),'polished updater flow');
check(files.system.includes('setUserTasks'),'Windows quick actions');
check(files.system.includes('app.dock.setMenu'),'macOS dock actions');
check(files.system.includes('download-progress')&&files.system.includes('setProgressBar'),'native update progress');
check(files.ux.includes("HOTKEY = 'CommandOrControl+Shift+A'"),'global Adelia hotkey');
check(files.ux.includes('setOverlayIcon'),'Windows unread badge');
check(files.ux.includes("title:'ДЗ ждёт проверки'")&&files.ux.includes("app.emit('adelia-open-route','homework')"),'native homework review notification routes correctly');
check(files.ux.includes("title:'Оплата требует внимания'")&&files.ux.includes("app.emit('adelia-open-route','finance')"),'native payment attention notification routes correctly');
check(files.layout.includes("'together','board-focus','mini-video','hide-video'"),'lesson layout modes');
check(web.lessonUi.includes('setLessonLayout')&&web.lessonUi.includes('toggleLessonVideo')&&web.lessonUi.includes('endLessonWorkspace'),'desktop lesson controller actions');
check(web.lessonUi.includes('dual-screen')&&web.lessonUi.includes('board-focus')&&web.lessonUi.includes('mini-video'),'desktop lesson controller modes');
check(web.lessonUiCss.includes('.adelia-desktop-lessonbar'),'desktop lesson controller styles');
check(web.desktopManifest.includes('desktop_lesson_workspace.css')&&web.desktopManifest.includes('desktop_lesson_workspace.js'),'lesson controller bundled into desktop UI');
check(web.prelessonUi.includes("D.getUxState()")&&web.prelessonUi.includes("D.openRoute('lesson',lesson.id)"),'desktop pre-lesson uses dashboard state and canonical lesson route');
check(web.prelessonUi.includes('D.openDeviceCheck(lesson.id)'),'pre-lesson opens real device check');
check(web.prelessonUi.includes('d>30')&&web.prelessonUi.includes('snoozeUntil'),'desktop pre-lesson timing and snooze');
check(web.prelessonCss.includes('.adelia-prelesson')&&web.prelessonCss.includes('.apl-open'),'desktop pre-lesson styles');
check(web.desktopManifest.includes('desktop_prelesson.css')&&web.desktopManifest.includes('desktop_prelesson.js'),'student pre-lesson bundled into desktop UI');

check(web.individual.includes("openLessonTool('meeting'")&&web.individual.includes("openLessonTool('board'")&&web.individual.includes('endLessonWorkspace()'),'individual desktop lifecycle');
check(web.group.includes("openLessonTool('meeting'")&&web.group.includes("openLessonTool('board'")&&web.group.includes('endLessonWorkspace()'),'group desktop lifecycle');
check(web.event.includes("openLessonTool('meeting'")&&web.event.includes("openLessonTool('board'")&&web.event.includes('endLessonWorkspace()'),'event desktop lifecycle');
check(web.individual.includes('started_at:r.started_at')&&web.individual.includes('Таймер начнётся после прихода ученика'),'individual start does not imply factual start');
check(web.group.includes("if(status==='STARTED')return['Доступ открыт — ждём первого ученика'")&&web.group.includes('mark_actual_start')===false,'group UI separates access from factual timer');
check(web.event.includes("e.status==='IN_PROGRESS'?'Доступ открыт — ждём первого ученика'")&&web.event.includes('Фактический таймер ещё не запущен'),'event UI separates access from factual timer');
for(const [name,source] of Object.entries({individual:web.individual,group:web.group,event:web.event,telemost_settings:web.telemostSettings}))check(!source.includes('MutationObserver'),`no persistent MutationObserver in ${name}`);

check(web.app.includes('startupHomework')&&web.app.includes('bootStudentRoute')&&web.app.includes('afterStudentLogin'),'student homework deep links survive auth and boot routing');
check(web.student.includes('/app/student_clean.css'),'student clean shell linked');
check(web.teacher.includes('/app/teacher_clean.css')&&web.teacher.includes('/app/teacher_clean7.css'),'teacher clean7 shell linked');
check(web.parent.includes('/app/parent/parent_clean.css'),'parent clean shell linked');
check(web.landing.includes('Adelia-latest-windows-x64.exe')&&readRepo('web/landing.html').includes('Adelia-latest-macos-arm64.dmg')&&readRepo('web/landing.html').includes('Adelia-latest-macos-x64.dmg'),'stable desktop download aliases linked');
const parentManifest=JSON.parse(web.parentManifest);
check(parentManifest.name.startsWith('Аделия'),'parent PWA branded Adelia');
check(parentManifest.icons?.some(x=>/^\/app\/assets\/icons\/adelia-(icon|mark)-192\.png/.test(x.src)&&x.sizes==='192x192'),'parent canonical 192 icon');
check(parentManifest.icons?.some(x=>/^\/app\/assets\/icons\/adelia-(icon|mark)-512\.png/.test(x.src)&&x.sizes==='512x512'),'parent canonical 512 icon');
check(parentManifest.icons?.some(x=>/^\/app\/assets\/icons\/adelia-(icon|mark)-512\.png/.test(x.src)&&x.sizes==='512x512'&&x.purpose==='maskable'),'parent canonical maskable icon');

if(failed)process.exit(1);
console.log('Desktop release selftest passed.');


