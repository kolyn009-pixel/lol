#!/usr/bin/env python3
"""Static product gate for Teacher, Student, Parent, PWA and Desktop shells."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def read(path): return (ROOT/path).read_text(encoding='utf-8')
def need(data, markers, label):
    missing=[m for m in markers if m not in data]
    if missing: raise AssertionError(f"{label}: missing {missing}")

def manifest(path,start,scope):
    m=json.loads(read(path))
    if m.get('start_url')!=start: raise AssertionError(f"{path}: bad start_url {m.get('start_url')}")
    if m.get('scope')!=scope: raise AssertionError(f"{path}: bad scope {m.get('scope')}")
    if m.get('display')!='standalone': raise AssertionError(f"{path}: display must be standalone")
    if str(m.get('theme_color','')).lower()!='#6847f5': raise AssertionError(f"{path}: wrong theme color")
    icons=m.get('icons') or []
    canonical={'/app/assets/icons/adelia-icon-192.png','/app/assets/icons/adelia-icon-512.png'}
    sources={str(x.get('src','')).split('?',1)[0] for x in icons}
    if not (sources & canonical): raise AssertionError(f"{path}: canonical Adelia icon missing")
    for icon in icons:
        src=str(icon.get('src','')).split('?',1)[0]
        if src=='/app/assets/icons/adelia-icon-192.png' and str(icon.get('sizes',''))!='192x192': raise AssertionError(f"{path}: 192 icon metadata must be 192x192")
        if src=='/app/assets/icons/adelia-icon-512.png' and str(icon.get('sizes',''))!='512x512': raise AssertionError(f"{path}: 512 icon metadata must be 512x512")

teacher=read('web/teacher.html')
student=read('web/index.html')
parent=read('web/parent/index.html')
parent_pwa=read('web/parent/pwa.js')
parent_sw=read('web/parent/service-worker.js')
desktop_start=read('desktop/start.js')
desktop_html=read('desktop/start.html')
desktop_preload=read('desktop/preload.js')
desktop_role=read('desktop/role_startup.js')
desktop_pkg=read('desktop/package.json')
desktop_manifest=read('desktop/bundled_ui_manifest.js')
student_sw=read('web/service-worker.js')
teacher_sw=read('web/teacher-service-worker.js')
pwa=read('web/pwa.js')
teacher_dashboard=read('web/teacher_dashboard_week.js')
finance_reporting=read('web_backend/finance_reporting.py')
minute_balance=read('core/minute_balance.py')

need(teacher,[
    '/app/teacher_clean.css','/app/teacher_clean_sections.css','/app/teacher_clean7.css',
    '/app/teacher_clean_runtime.js','/app/teacher_clean_router.js','/app/teacher_groups.js',
    'data-view="groups"','data-view="messages"','data-view="health"',
    '/app/assets/icons/adelia-icon-32.png','/app/assets/icons/adelia-icon-180.png'
],'teacher')
need(student,[
    '/app/student_clean.css','/app/install_runtime.js','data-tab="home"','data-tab="schedule"',
    'data-tab="homework"','data-tab="messages"','data-tab="profile"',
    '/app/assets/icons/adelia-icon-32.png','/app/assets/icons/adelia-icon-180.png'
],'student')
need(parent,[
    '/app/parent/parent_clean.css','/app/parent/parent_v5.js','/app/parent/pwa.js',
    '/app/assets/icons/adelia-icon-32.png','/app/assets/icons/adelia-icon-180.png'
],'parent')
need(parent_pwa,[
    "BASE='/app/parent/'",
    "SCOPE='/app/parent/'",
    "SW=BASE+'service-worker.js?v='+SW_VERSION",
    "navigator.serviceWorker.register(SW,{scope:SCOPE,updateViaCache:'none'})",
    'controllerchange',
    'beforeinstallprompt'
],'parent pwa')
need(parent_sw,["BASE='/app/parent/'","adelia-parent-v7",'notificationclick','push','adelia-icon-180.png'],'parent service worker')

manifest('web/manifest.webmanifest','/app/','/app/')
manifest('web/teacher-manifest.webmanifest','/teacher/','/teacher/')
manifest('web/parent/manifest.webmanifest','/app/parent/','/app/parent/')

need(desktop_start,['parentRole','openParentCabinet','teacherRole','studentRole'],'desktop chooser')
need(desktop_html.lower(),['преподаватель','ученик','родитель','#6847f5'],'desktop html')
need(desktop_preload,['openParentCabinet','adelia:parent-cabinet'],'desktop preload')
need(desktop_role,["APP_ORIGIN+'/app/parent/'","adelia:parent-cabinet"],'desktop role runtime')
need(desktop_pkg,['verify_icon.js','bundled_ui_manifest.js','build/icon.png'],'desktop package')
need(desktop_manifest,['student:','teacher:','parent:','teacher_v5.css','parent/app.css'],'desktop bundled UI')
need(student_sw,['adelia-shell-v15',"url.pathname==='/app/teacher.html'",'notificationclick','adelia-icon-180.png'],'student service worker')
need(teacher_sw,['adelia-teacher-shell-v5','notificationclick','adelia-icon-180.png'],'teacher service worker')
need(pwa,['desktop_uses_native_notifications',"location.pathname==='/app/teacher.html'",'/api/push/subscribe'],'PWA notification routing')
need(teacher_dashboard,['updateDashboardState','setInterval(()=>fetchDash().then(syncDesktopState)','unreadMessages','activeHomework','unpaidAmount'],'desktop notification state')
need(finance_reporting,['_lesson_earned_expr','reserved_paid_minutes','funding_kind'],'non-cash finance reporting')
need(minute_balance,['admin_adjust_minutes','Positive minutes are non-cash bonus/adjustment minutes',"source_type='BONUS'"],'manual bonus accounting')

if 'generate_assets.js &&' in desktop_pkg:
    raise AssertionError('desktop build still auto-generates branding icon')
for legacy in ('/adelia-favicon-32.png','/adelia-apple-touch-icon-180.png','adelia-icon.svg'):
    if legacy in teacher or legacy in student or legacy in parent:
        raise AssertionError(f'legacy icon reference remains: {legacy}')

for path in ['web/teacher_v5_runtime.js','web/parent/parent_v5.js']:
    if 'new MutationObserver' in read(path):
        raise AssertionError(f'{path}: continuous MutationObserver forbidden')

print('ADELIA_PRODUCT_GATE=PASS')
