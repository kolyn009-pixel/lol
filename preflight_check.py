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
]
missing = [x for x in required if not (ROOT / x).is_file()]
if missing:
    print('MISSING FILES:')
    for x in missing:
        print(' -', x)
    sys.exit(2)

checks = {
    'admin.py': ['💬 Написать', '💜 Спросить Аделию об ученике', '👨‍👩‍👧 Родители', '💜 АДЕЛИЯ • ГЛАВНАЯ', '••• Ещё', 'Заблокировать ученика'],
    'handlers/musthave_admin.py': ['💜 Подготовить с Аделией', '👨‍👩‍👧 Родителям с Аделией', 'mh_senddraft'],
    'ux_final/service.py': ['💳 Способы оплаты', '📣 Рассылка с Аделией', '💜 Пост с Аделией'],
    'crm_plus/jobs.py': ["'08:30'", "'21:00'"],
    'channel_admin.py': ['Nothing is ever posted to the channel', 'Утренний отчёт по подпискам: 08:30'],
    'handlers/admin_inbox_handlers.py': ['Отметить всё решённым'],
    'handlers/adelia_content.py': ['💜 АДЕЛИЯ • ПОСТ В КАНАЛ', 'РАССЫЛКА С АДЕЛИЕЙ', 'ac_broadcast_send', 'ac_channel_publish'],
    'ai_assistant/client.py': ['draft_channel_post', 'draft_broadcast'],
    'bot.py': ['admin_students is intentionally handled by admin.py'],
    'schedule_admin.py': ['⚙️ МОЁ РАСПИСАНИЕ', 'schedule_week|ODD', 'schedule_week|EVEN', '31 августа – 6 сентября 2026', 'Сделать выходным'],
    'database.py': ['ODD_WEEK_ANCHOR = date(2026, 8, 31)', 'get_effective_working_hours', 'teacher_week_day_off'],
    'core/calendar_policy.py': ['COLOR_COMPLETED = "10"', 'COLOR_ATTENTION = "11"', 'Пробное занятие бесплатное', 'PAYMENT_DUE_24H'],
    'handlers/calendar_runtime.py': ['calendar_lesson_state', 'calendar_special_events', 'should_delete_lesson_event'],
    'handlers/receipt_center.py': ['🧾 ЦЕНТР ЧЕКОВ', 'payadmin_offer_preview', 'payment_admin_approve'],
    'handlers/post_lesson_review.py': ['📝 Задать ДЗ по этим темам', 'save_draft_marks', 'review_completed'],
    'handlers/briefs_v2.py': ['💜 АДЕЛИЯ • ДОБРОЕ УТРО', '💜 АДЕЛИЯ • ИТОГ ДНЯ', 'Темы выбраны / ДЗ не отправлено'],
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

# RC1 navigation assertions
_admin = (ROOT / 'admin.py').read_text(encoding='utf-8')
for token in ['Выберите класс:', '⬅️ К классам', '🏠 Главная', 'mh_blocked_students']:
    if token not in _admin and token != 'mh_blocked_students':
        raise SystemExit(f'PREFLIGHT FAIL: missing RC1 token {token}')
_mh = (ROOT / 'handlers/musthave_admin.py').read_text(encoding='utf-8')
if 'mh_blocked_students' not in _mh:
    raise SystemExit('PREFLIGHT FAIL: blocked students handler missing')

# FINAL AI safety assertions
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

# FINAL OPS / PROVIDERS checks
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
