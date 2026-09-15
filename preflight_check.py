from pathlib import Path
import compileall
import sys

ROOT = Path(__file__).resolve().parent
required = [
    'bot.py', 'admin.py', 'database.py', 'channel_admin.py', 'schedule_admin.py', 'schedule_parity_selftest.py',
    'handlers/musthave_admin.py', 'handlers/musthave_jobs.py', 'handlers/adelia_content.py',
    'handlers/calendar_runtime.py', 'handlers/receipt_center.py', 'handlers/post_lesson_review.py',
    'handlers/teacher_end_notifications.py', 'handlers/schedule_exceptions_v2.py', 'handlers/briefs_v2.py',
    'handlers/college_curriculum_handlers.py', 'core/calendar_policy.py', 'core/lesson_lifecycle.py',
    'core/lesson_time.py', 'core/post_lesson.py', 'core/teacher_tasks.py',
    'vk_adapter/teacher_post_lesson.py', 'vk_adapter/telegram_link.py', 'vk_adapter/app.py',
    'learning/homework_flow.py',
    'ai_assistant/__init__.py', 'ai_assistant/client.py', 'ai_assistant/context.py',
    'crm_plus/jobs.py', 'handlers/admin_inbox_handlers.py',
    'web_backend/api_v5.py', 'web_backend/api_v6.py', 'web_backend/api_v7.py',
    'web_backend/lesson_join.py', 'web_backend/group_lesson_access.py',
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
    'web_backend/api_v5.py': ['AdeliaWeb/5.7', 'student_social_profile', 'event_campaign'],
    'web_backend/api_v6.py': ['class Handler', 'api_v5.Handler'],
    'web_backend/api_v7.py': ['class Handler', 'api_v6.Handler'],
    'web_backend/lesson_join.py': ['board_url', 'student_join'],
    'web_backend/group_lesson_access.py': ['board_visible', 'telemost_visible'],
    'handlers/musthave_jobs.py': ['adelia_homework_watchdog', 'homework_watchdog.tick'],
    'vk_adapter/tutorbot-vk.service': ['-m vk_adapter.runtime', 'EnvironmentFile=-/etc/tutorbot/adelia.env'],
    'web_backend/adelia-web.service': ['-m web_backend.api_v6', 'EnvironmentFile=-/etc/tutorbot/adelia.env'],
    'web_backend/adelia-homework-delivery.service': ['-m web_backend.homework_delivery_worker', 'EnvironmentFile=-/etc/tutorbot/adelia.env'],
    'web_backend/adelia-receipt-archive.service': ['-m web_backend.receipt_archive_worker', 'EnvironmentFile=-/etc/tutorbot/adelia.env', 'ReadWritePaths=/opt/tutorbot'],
    'core/calendar_policy.py': ['COLOR_COMPLETED = "10"', 'COLOR_ATTENTION = "11"', 'Пробное занятие бесплатное', 'PAYMENT_DUE_24H'],
    'handlers/calendar_runtime.py': ['calendar_lesson_state', 'should_keep_lesson_event', 'lesson_external_integrations'],
    'handlers/receipt_center.py': ['🧾 ЦЕНТР ЧЕКОВ', 'payadmin_offer_preview', 'payment_admin_approve'],
    'handlers/post_lesson_review.py': ['📝 Задать ДЗ по этим темам', 'save_draft_marks', 'review_completed'],
    'handlers/briefs_v2.py': ['💜 АДЕЛИЯ • ДОБРОЕ УТРО', '💜 АДЕЛИЯ • ИТОГ ДНЯ', 'После уроков нет ДЗ'],
    'handlers/schedule_exceptions_v2.py': ['Указать промежуток', 'Целый день'],
    'core/teacher_tasks.py': ['unpaid_next:', 'nearest upcoming lesson', 'COALESCE(l.is_trial,0)=0'],
    'vk_adapter/app.py': ['teacher_post_lesson.install', 't_finish|'],
    'vk_adapter/teacher_post_lesson.py': ['🧠 Пройти опрос', '📝 Задать ДЗ по этим темам', 'ОПРОС ПОСЛЕ ЗАНЯТИЯ ПРОЙДЕН В VK'],
    'vk_adapter/telegram_link.py': ['briefs_v2.install', 'calendar_runtime.install', 'schedule_exceptions_v2.install'],
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
 'core/teacher_tasks.py':['teacher_tasks','Оплата следующего занятия'],
}.items():
    _txt=(ROOT/_f).read_text(encoding='utf-8')
    for _t in _tokens:
        assert _t in _txt, f'Missing {_t!r} in {_f}'
print('FINAL OPS PROVIDERS PREFLIGHT: OK')
print('LIVE LESSON / GROUP / EVENT / WORKER PREFLIGHT: OK')
