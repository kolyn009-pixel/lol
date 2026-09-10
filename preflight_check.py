from pathlib import Path
import compileall
import sys

ROOT = Path(__file__).resolve().parent
required = [
    'bot.py', 'admin.py', 'database.py', 'channel_admin.py', 'schedule_admin.py', 'schedule_parity_selftest.py',
    'handlers/musthave_admin.py', 'handlers/musthave_jobs.py', 'handlers/adelia_content.py',
    'ai_assistant/__init__.py', 'ai_assistant/client.py', 'ai_assistant/context.py',
    'crm_plus/jobs.py', 'handlers/admin_inbox_handlers.py',
    'web_backend/api_v5.py', 'web_backend/lesson_join.py', 'web_backend/group_lesson_access.py',
    'web_backend/event_campaign.py', 'web_backend/open_event_admin.py', 'web_backend/open_event_policy.py',
    'web_backend/student_social_profile.py', 'web_backend/group_portal.py',
    'web_backend/homework_watchdog.py', 'web_backend/homework_notifications.py',
    'web_backend/homework_delivery_worker.py', 'web_backend/receipt_archive_worker.py',
    'web_backend/receipt_cloud_archive.py', 'vk_adapter/runtime.py', 'vk_adapter/payment_receipts.py',
    'vk_adapter/tutorbot-vk.service', 'web_backend/adelia-web.service',
    'web_backend/adelia-homework-delivery.service', 'web_backend/adelia-receipt-archive.service',
]
missing = [x for x in required if not (ROOT / x).is_file()]
if missing:
    print('MISSING FILES:')
    for x in missing:
        print(' -', x)
    sys.exit(2)

checks = {
    'admin.py': ['💬 Написать', '💜 Спросить Аделию об ученике', '👨‍👩‍👧 Родители', '💜 АДЕЛИЯ • ГЛАВНАЯ', '••• Ещё', 'Заблокировать ученика'],
    'handlers/musthave_admin.py': ['💜 Подготовить с Аделией', '👨‍👩‍👧 Родителям с Аделией', 'mh_senddraft', 'mh_blocked_students'],
    'ux_final/service.py': ['💳 Способы оплаты', '📣 Рассылка с Аделией', '💜 Пост с Аделией'],
    'crm_plus/jobs.py': ["'08:30'", "'21:00'"],
    'channel_admin.py': ['Nothing is ever posted to the channel', 'Утренний отчёт по подпискам: 08:30'],
    'handlers/admin_inbox_handlers.py': ['Отметить всё решённым'],
    'handlers/adelia_content.py': ['💜 АДЕЛИЯ • ПОСТ В КАНАЛ', 'РАССЫЛКА С АДЕЛИЕЙ', 'ac_broadcast_send', 'ac_channel_publish'],
    'ai_assistant/client.py': ['draft_channel_post', 'draft_broadcast'],
    'bot.py': ['admin_students is intentionally handled by admin.py'],
    'schedule_admin.py': ['⚙️ МОЁ РАСПИСАНИЕ', 'schedule_week|ODD', 'schedule_week|EVEN', '31 августа – 6 сентября 2026', 'Сделать выходным'],
    'database.py': ['ODD_WEEK_ANCHOR = date(2026, 8, 31)', 'get_effective_working_hours', 'teacher_week_day_off'],
    'web_backend/api_v5.py': ['AdeliaWeb/5.6', 'ADELIA_OTP_SECRET', 'student_social_profile', 'event_campaign'],
    'web_backend/lesson_join.py': ['board_url', 'student_join'],
    'web_backend/group_lesson_access.py': ['board_visible', 'telemost_visible'],
    'handlers/musthave_jobs.py': ['adelia_homework_watchdog', 'homework_watchdog.tick'],
    'vk_adapter/tutorbot-vk.service': ['-m vk_adapter.runtime', 'EnvironmentFile=-/etc/tutorbot/adelia.env'],
    'web_backend/adelia-web.service': ['-m web_backend.api_v5', 'EnvironmentFile=-/etc/tutorbot/adelia.env'],
    'web_backend/adelia-homework-delivery.service': ['-m web_backend.homework_delivery_worker', 'EnvironmentFile=-/etc/tutorbot/adelia.env'],
    'web_backend/adelia-receipt-archive.service': ['-m web_backend.receipt_archive_worker', 'EnvironmentFile=-/etc/tutorbot/adelia.env', 'ReadWritePaths=/opt/tutorbot'],
}
failed = []
for name, markers in checks.items():
    text = (ROOT / name).read_text(encoding='utf-8')
    for marker in markers:
        if marker not in text:
            failed.append(f'{name}: {marker}')
if failed:
    print('FEATURE CHECK FAILED:')
    for x in failed:
        print(' -', x)
    sys.exit(3)

ok = compileall.compile_dir(str(ROOT), quiet=1)
if not ok:
    print('COMPILEALL FAILED')
    sys.exit(4)
print('PREFLIGHT OK')

_ai = (ROOT / 'ai_assistant/client.py').read_text(encoding='utf-8')
for token in [
    "MODEL = os.getenv('AI_MODEL', 'openrouter/free')",
    "'reasoning': {'exclude': True}",
    '<<<FINAL>>>',
    '_sanitize_final_text',
    '_looks_like_placeholder',
    'AI returned reasoning instead of a usable final answer',
]:
    if token not in _ai:
        raise SystemExit(f'PREFLIGHT FAIL: missing AI safety token {token}')
print('FINAL PREFLIGHT OK')

for _f,_tokens in {
 'handlers/task_admin.py':['📌 МОИ ЗАДАЧИ','task_add_user'],
 'handlers/ai_provider_admin.py':['AI-ПРОВАЙДЕРЫ','API-КЛЮЧ'],
 'ai_assistant/providers.py':['openrouter_env','gemini','deepseek'],
 'core/teacher_tasks.py':['teacher_tasks','Проверить оплату'],
}.items():
    _txt=(ROOT/_f).read_text(encoding='utf-8')
    for _t in _tokens:
        assert _t in _txt, f'Missing {_t!r} in {_f}'
print('FINAL OPS PROVIDERS PREFLIGHT: OK')
print('LIVE LESSON / GROUP / EVENT / WORKER PREFLIGHT: OK')
