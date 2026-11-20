# CHANGELOG

Сжатая хронология по [docs/releases/](releases/). Даты указаны только там, где они есть в самих заметках. Порядок недатированных релизов восстановлен по пометкам вида «основано на …» и может быть неточным.

## Базовые этапы (без дат)

- **Этап 1 — надёжность** (`STAGE1_README.txt`, `SERVER_UPDATE.txt`): модуль `core/`, владелец и несколько админов, аудит, неизменяемый финансовый журнал, центр событий, режим техработ, backup и откат, экспорт в Excel.
- **Этап 2 — обучение** (`STAGE2_README.txt`): `learning/`, `handlers/`, `repositories/`. Дерево тем, цели, диагностика, пробники, планы занятий, материалы, предурочная сводка.
- **Этап 3 — автоматизация и семья** (`STAGE3_README.txt`): `automation/`. Лист ожидания, семейный кабинет, рассылки, рефералы, паузы и больничные, уведомления родителям.

## FINAL-линейка (без дат)

- **FINAL: минутная модель** (`FINAL_RELEASE_NOTES.txt`, `MINUTE_UPDATE_README.txt`): баланс в минутах, базовая длительность занятия у каждого ученика, бонусные минуты за недоработку, единые «Входящие».
- **FINAL MEGA** (`FINAL_MEGA_README.txt`): 18 функций, в том числе карточка 360°, тарифы, минутный журнал, сверка, пробники, план экзамена, неделя преподавателя.
- **Перенос и обмен** (`EXCHANGE_UPDATE_README.txt`): своё время и обмен слотами между учениками с многошаговым подтверждением.
- **EXCHANGE UI FIX** (`UI_FIX_RELEASE_NOTES.txt`): из интерфейса пробников и планов убраны технические ID, введены пошаговые мастера.
- **CRM+** (`CRM_PLUS_RELEASE_NOTES.txt`): переписка из карточки, тихие часы, сегментные рассылки, «Что важно сегодня», поиск.
- **MESSENGER UX** (`MESSENGER_UX_RELEASE_NOTES.txt`): диалоги внутри бота, часы приёма сообщений, очередь доставки.
- **UX FINAL / UX + SPEED** (`UX_FINAL_RELEASE_NOTES.txt`, `UX_SPEED_FINAL.md`): компактная админка, быстрые действия, ИИ вынесен из event loop, индексы SQLite, `/uicheck`.
- **FINAL FREEZE** (`FINAL_FREEZE_*.txt`): общая тестовая лаборатория, роль TESTER, глобальный `/home`. Hotfix (`FINAL_UX_README.txt`): сетевые ошибки Telegram больше не считаются критичными.

## Август 2026

- **2026-08-23 — ребрендинг в «Аделию»** (`ADELIA_REBRAND_NOTES.txt`, `ADELIA_UX_POLISH_NOTES.txt`): все тексты переписаны голосом Аделии, добавлен `BRAND_ADELIA.md`, логика не менялась.
- **2026-08-26 — админ-помощник** (`ADELIA_ADMIN_UPGRADE_NOTES.txt`): блокировка учеников, раздел «Родители», несколько способов оплаты, «Отметить всё решённым».
- **Статистика канала** (`ADELIA_CHANNEL_STATS_UPDATE.txt`): автоприветствия убраны, вместо них тихий учёт JOIN/LEAVE и отчёт в 08:30.
- **MUST-HAVE** (`MUSTHAVE_ADELIA_UPDATE.txt`): «Требует внимания», «Долги и оплаты», «Спросить Аделию», недельный отчёт.
- **Adelia Final / V2 / RC1** (`FINAL_ADELIA_RELEASE*.md`, `RC1_RELEASE_NOTES.md`, `FINAL_RELEASE_NOTES.md`): деплой в `/opt/tutorbot`, ИИ-черновики постов и рассылок, `AI_MODEL=openrouter/free`, фильтр reasoning, центр настроек.
- **UX + BRIEFS** (`FINAL_UX_BRIEFS_UPDATE.md`): утренние и вечерние сводки с настраиваемым временем и тестовой отправкой.
- **2026-08-27 — ROOT UX** (`FINAL_ROOT_UX_UPDATE.md`, `BUILD_INFO.txt`): `/admin`, `/start` и «Главная» ведут на одну динамическую главную преподавателя.
- **Часовые пояса** (`FINAL_TIMEZONE_STUDENT_MORNING.md`, `FINAL_PERSONAL_TIMEZONES_MSK.md`): часовой пояс бота, личные пояса МСК±N, утренняя сводка ученика.
- **Настройки и роли** (`FINAL_QUALITY_SETTINGS_REVIEW.md`, `FINAL_ROLE_UX_GUIDE.md`): рабочие экраны настроек, самодиагностика, упрощённые главные ученика и родителя.
- **Расписание** (`FINAL_TEACHER_SCHEDULE_PARITY.md`): чётные и нечётные недели, несколько интервалов в день.
- **2026-08-28 — FINAL OPS + AI PROVIDERS** (`FINAL_RELEASE_2026-08-28.md`, `FINAL_OPS_AI_PROVIDERS.md`): рабочие задачи без ИИ, управление AI-провайдерами из Telegram с переключением на резервный.
- **Учебный центр, этапы 1–3** (`STAGE1_FORMULA_STUDY_RELEASE.md`, `STAGE2_HOMEWORK_RELEASE.md`, `STAGE3_ROLE_UX_RELEASE.md`): поиск, избранное и самопроверка по формулам; мастер ДЗ на 5 шагов; учебные экраны ученика и родителя.
- **2026-08-29 — исправления миграций** (`FINAL_STAGE3_MIGRATION_FIX.md`, `FINAL_TESTDB_SCHEMA_FIX.md`): упавший старт (`no such column: draft_id`), апгрейд тестовой БД, проба миграции на копии и автооткат при деплое.
- **Совместимость схемы** (`FINAL_STAGE3_ATTACHMENT_MIGRATION_FIX.md`, `FINAL_TESTDB_*_FIX.md`, `FINAL_TEACHER_TASKS_STARTUP_FIX.md`): `file_id` и `telegram_file_id` во вложениях, колонки старой таблицы `users`, падение `teacher_tasks.initialize()`.
