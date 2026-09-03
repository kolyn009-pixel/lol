# Аделия AI — финальная настройка OpenRouter

В финальной сборке используется:

```env
AI_MODEL=openrouter/free
```

Причина: конкретные бесплатные `:free` модели OpenRouter могут исчезать и возвращать HTTP 404. `openrouter/free` выбирает доступную бесплатную модель автоматически.

## /etc/tutorbot.env

```env
BOT_TOKEN=ВАШ_TELEGRAM_BOT_TOKEN
OPENROUTER_API_KEY=ВАШ_OPENROUTER_KEY
AI_MODEL=openrouter/free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_APP_NAME=Adelia TutorBot
OPENROUTER_SITE_URL=https://localhost
AI_TIMEOUT_SECONDS=25
```

`deploy_to_opt.sh` сам приводит `AI_MODEL` к `openrouter/free`, но **не меняет BOT_TOKEN и OPENROUTER_API_KEY**.

## Защита от reasoning

Бесплатный роутер иногда выбирает reasoning-модели. Финальный AI-клиент:

1. просит OpenRouter исключать reasoning;
2. требует финальный текст в служебных маркерах;
3. очищает `<think>` и типичные reasoning-префиксы;
4. при плохом ответе делает один корректирующий повтор;
5. если чистого финального ответа всё равно нет — возвращает безопасную ошибку, а не показывает внутренние рассуждения.

Обычные функции TutorBot не зависят от OpenRouter и продолжают работать при его недоступности.
