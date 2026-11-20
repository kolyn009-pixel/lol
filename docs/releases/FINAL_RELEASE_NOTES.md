# TutorBot ADELIA FINAL

Единая финальная сборка для `/opt/tutorbot`.

## Что включено

- Админка от лица Аделии.
- Ученики: **класс → список → карточка**, поиск и заблокированные.
- Блокировка/разблокировка ученика с Telegram-уведомлением без удаления данных.
- Родители отдельным разделом и связи родитель ↔ ученик.
- Несколько способов оплаты и выбор реквизитов перед предложением оплаты.
- Входящие + «Отметить всё решённым» с подтверждением.
- `⚠️ Требует внимания`, долги и история ученика.
- Утренняя сводка 08:30, вечерняя 21:00, недельный отчёт.
- Тихая статистика канала JOIN/LEAVE; никаких автоматических приветствий в канал.
- Аделия для сообщений конкретному ученику/родителю с предпросмотром.
- Аделия для постов в канал: идея → черновик → подтверждение → публикация.
- Аделия для рассылок всем ученикам или сегментам (класс, ЕГЭ/ОГЭ, предмет) с предпросмотром.
- `💜 Спросить Аделию` и контекстный помощник в карточке ученика.

## AI — финальное исправление

- Бесплатный режим снова использует `AI_MODEL=openrouter/free`. Конкретные `:free` slug не фиксируются: OpenRouter может снимать их без предупреждения.
- Добавлен фильтр, который не показывает администратору reasoning/thinking process.
- Для текстовых ответов используется протокол `<<<FINAL>>>...<<<END>>>`.
- Если бесплатная модель всё равно прислала анализ, TutorBot делает один корректирующий повтор; если финальный ответ так и не получен, показывает безопасную ошибку вместо chain-of-thought.
- Добавлен `reasoning.exclude=true` для моделей/провайдеров, которые поддерживают отдельный reasoning.
- Placeholder-ключи (`ВСТАВЬ_СЮДА...`) считаются отсутствующим AI-ключом, чтобы не отправлять мусор в HTTP Authorization.
- TutorBot продолжает работать, даже если OpenRouter недоступен.

## Деплой

`deploy_to_opt.sh`:

- делает полный backup `/opt/tutorbot`;
- сохраняет `tutor.db`, `venv`, `credentials.json`, `token.json`, `.env` и backups;
- проверяет Python и обязательные функции;
- запускает локальный AI self-test;
- если `/etc/tutorbot.env` существует, нормализует `AI_MODEL=openrouter/free`, не меняя `BOT_TOKEN` и `OPENROUTER_API_KEY`;
- запускает `tutorbot.service` и проверяет статус.

## Settings Center update
- Expanded `⚙️ Настройки` into a central control screen.
- Added `🔔 Уведомления` with persistent DB-backed toggles for lesson reminders (24h/2h/30m/10m), homework, payments, weekly summary and channel events.
- Added enable-all / disable-all controls.
- Added quiet-hours setting display/toggle (default 22:00-08:00).
- Added weekly-summary time presets (08:00/09:00/10:00), persisted in `bot_settings`.
- Added notification self-test button.
- Lesson scheduling now respects the four lesson-reminder toggles.
- Weekly summary respects its toggle and configured time after restart.
