# Аделия | TutorBot

Учебная CRM для репетитора: Telegram-бот (плюс VK-адаптер) для записи на занятия, оплат по минутной модели, расписания, домашних заданий и связи с учениками и родителями. Встроенный ИИ-ассистент «Аделия» (OpenRouter и другие OpenAI-совместимые провайдеры) пишет черновики текстов. Основная логика (БД, суммы, расписание) работает без ИИ.

Правила голоса бренда описаны в [BRAND_ADELIA.md](BRAND_ADELIA.md).

## Возможности по ролям

**Ученик**
- запись на занятия, переносы и отмены, обмен слотами, постоянное расписание, лист ожидания;
- баланс в минутах, абонементы, оплата по реквизитам, отправка чека;
- домашние задания с файлами, формулы и справочники (физика, химия, ЕГЭ), «Моя учёба», «Проверить себя»;
- переписка с преподавателем внутри бота, напоминания 24ч / 2ч / 30м / 10м, личный часовой пояс (МСК±N).

**Родитель**
- семейный кабинет (до двух родителей на ученика), расписание, прогресс, ДЗ, оплата;
- настройка уведомлений по каждому ребёнку, собственный часовой пояс.

**Преподаватель / администратор** (`/admin`)
- главная с задачами на день, «Входящие», «Сообщения от учеников», «Требует внимания», долги и оплаты;
- карточка ученика (360°), блокировка и разблокировка, родители, способы оплаты, тарифы и скидки;
- расписание с чётными и нечётными неделями, синхронизация с Google Calendar;
- мастер ДЗ, пробники, планы экзаменов, отчёты родителям;
- рассылки, посты в канал и статистика канала (с черновиками от Аделии; отправка только после подтверждения);
- утренние, вечерние и недельные сводки, рабочие задачи без ИИ, управление AI-провайдерами.

**Владелец** (дополнительно): `/addadmin`, `/deladmin`, `/addtester`, `/deltester`, тестовая лаборатория (`/testlab`), раздел `/system` (backup, диагностика, техработы, экспорт в Excel).

## Требования

- Python **3.9+**: код использует `zoneinfo`. Точная версия на сервере не указана (TODO).
- `python-telegram-bot` v21.7+ (async API: `Application`, `run_polling`). В репозитории версия пока нигде не закреплена (TODO: закрепить в `requirements.txt`).
- Google Calendar API: `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, а также `credentials.json` и `token.json` в корне проекта.
- `openpyxl` для экспорта в Excel (см. `requirements_stage1.txt`).
- SQLite: база `tutor.db` в корне проекта, тестовая база `../tutorbot_data/tutor_test.db`.

## Установка

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt   # файл добавляется отдельным PR
# до его появления: pip install -r requirements_stage1.txt + зависимости из списка выше
```

Google Calendar: положите `credentials.json` в корень и один раз выполните `python3 calendar_test.py`. Скрипт пройдёт OAuth и создаст `token.json`. Оба файла внесены в `.gitignore`.

## Переменные окружения

На сервере их хранят в `/etc/tutorbot.env` (см. [ADELIA_AI_SETUP.md](ADELIA_AI_SETUP.md), `docs/releases/FINAL_ADELIA_RELEASE.md`). Сервис читает этот файл как systemd `EnvironmentFile`.

| Переменная | По умолчанию | Где используется |
|---|---|---|
| `BOT_TOKEN` | обязательна | `bot.py`, без неё бот не стартует |
| `VK_TOKEN` | — | `vk_adapter/app.py`, обязательна для VK |
| `VK_GROUP_ID` | — | `vk_adapter/app.py`, обязательна для VK |
| `VK_API_VERSION` | `5.199` | `vk_adapter/app.py` |
| `OPENROUTER_API_KEY` | — | `ai_assistant/providers.py`; без ключа ИИ выключен |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | `ai_assistant/` |
| `AI_MODEL` | `openrouter/free` | `ai_assistant/` |
| `AI_TIMEOUT_SECONDS` | `25` | `ai_assistant/client.py` |
| `TUTORBOT_AI_PROVIDERS_FILE` | `/etc/tutorbot_ai_providers.json` | ключи дополнительных провайдеров (права 0600) |
| `TUTORBOT_TEST_DATA_DIR`, `TUTORBOT_TEST_DB` | `../tutorbot_data/tutor_test.db` | `database.py`, тестовая лаборатория |
| `OPENROUTER_APP_NAME`, `OPENROUTER_SITE_URL` | — | упомянуты в ADELIA_AI_SETUP.md; использование в коде не проверено (TODO) |
| `OWNER_ID` | — | **TODO:** в коде не читается. ID владельца сейчас захардкожен в `admin.py` (`ADMIN_ID`) |

Пример `/etc/tutorbot.env`:

```env
BOT_TOKEN=...
OPENROUTER_API_KEY=...
AI_MODEL=openrouter/free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_TIMEOUT_SECONDS=25
VK_TOKEN=...
VK_GROUP_ID=...
```

## Запуск

Telegram-бот (точка входа `bot.py`, `main()` с long polling):

```bash
set -a; . /etc/tutorbot.env; set +a
python3 bot.py
```

VK-адаптер работает отдельным процессом через long poll (в модуле относительные импорты, поэтому запускать как модуль):

```bash
python3 -m vk_adapter.app
```

Продакшн: каталог `/opt/tutorbot`, сервис `tutorbot.service`, логи смотрят через `journalctl -u tutorbot`.
- TODO: unit-файла `tutorbot.service` в репозитории нет.
- TODO: unit для VK-адаптера не описан.
- TODO: скрипт `deploy_to_opt.sh` упоминается в заметках о релизах, но в репозитории его нет.
- Обновление с резервной копией и откат: `sh core/safe_update.sh /путь/к/боту` и `sh core/rollback.sh /путь/к/боту`.

Веб-интерфейс: **TODO**, в коде его нет.

## Проверки и тесты

```bash
python3 -m pytest              # TODO: каталога tests/ и конфигурации pytest пока нет
python3 -m compileall -q .
python3 core/post_update_check.py
python3 preflight_check.py
python3 final_freeze_selftest.py   # и другие *_selftest.py в корне
```

Сейчас самопроверки сделаны отдельными скриптами `*_selftest.py`, а не pytest-тестами. Учтите, что pytest по маске `*_test.py` подхватит и `calendar_test.py`: это ручная проверка живого Google API.

## Структура

```
ai_assistant/    ИИ-клиент Аделии, AI-провайдеры, контекст
automation/      этап 3: семья, рассылки, лист ожидания, фоновые задания
core/            роли, аудит, финансовый журнал, backup, диагностика, тест-лаб, скрипты обновления
crm_plus/        переписка с учениками, тихие часы, сегментные рассылки
final_features/  тарифы, минутный журнал, пробники, отчёты, перенос и обмен, прогнозы
handlers/        Telegram-обработчики по разделам
learning/        учебный модуль: темы, ДЗ, материалы, формулы, прогресс
repositories/    слой доступа к данным для learning и automation
ux_final/        компактная админка, быстрые действия, UI-аудит
vk_adapter/      бот ВКонтакте и мост уведомлений и вложений с Telegram
docs/releases/   заметки о релизах
```

В корне лежат `bot.py` (точка входа), `database.py`, `admin.py`, `payments.py`, библиотеки формул и самопроверки.

## Документация

- [BRAND_ADELIA.md](BRAND_ADELIA.md): голос и стиль Аделии
- [ADELIA_AI_SETUP.md](ADELIA_AI_SETUP.md): настройка OpenRouter
- [docs/CHANGELOG.md](docs/CHANGELOG.md): краткая хронология
- [docs/releases/](docs/releases/): полные заметки о релизах
