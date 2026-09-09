"""Fast static checks for Stage 14.5 student web self-service."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / 'web_backend' / 'api_v3.py').read_text(encoding='utf-8')
service = (ROOT / 'web_backend' / 'student_self_service.py').read_text(encoding='utf-8')
ui = (ROOT / 'web' / 'student_self_service.js').read_text(encoding='utf-8')
index = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
lesson = (ROOT / 'web' / 'lesson' / 'index.html').read_text(encoding='utf-8')

checks = {
    'authenticated self-service API': "path.startswith('/api/student/self-service/')" in api,
    'regular schedule GET': 'student_regular_schedules' in api,
    'ownership validation': '_lesson_owned' in service and '_schedule_owned' in service,
    'canonical sickness rules': 'database.request_sickness' in service,
    'canonical cancellation rules': 'database.cancel_lesson_by_student' in service,
    'late cancellation recalculated server-side': 'database.get_hours_until_lesson' in service,
    'canonical regular schedule pause': 'database.pause_regular_schedule' in service,
    'canonical regular schedule resume': 'database.resume_regular_schedule' in service,
    'reschedule request': 'database.create_pending_reschedule' in service,
    'student cabinet loads UI': '/app/student_self_service.js' in index,
    'lesson page loads UI': '/app/student_self_service.js' in lesson,
    'destructive cancel confirmation': 'confirm(warning)' in ui,
    'pause date bounded server-side': 'timedelta(days=180)' in service,
}
failed = False
for label, ok in checks.items():
    print(('OK   ' if ok else 'FAIL ') + label)
    failed = failed or not ok
if failed:
    raise SystemExit(1)
print('Stage 14.5 self-service selftest passed.')
