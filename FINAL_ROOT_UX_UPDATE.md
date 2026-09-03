# ADELIA FINAL ROOT UX UPDATE

This build connects the real `/admin`, `/start` admin branch, and `🏠 Главная` admin branch to the same compact teacher dashboard.

## Teacher home
- Dynamic `💜 АДЕЛИЯ • ГЛАВНАЯ` text with counts for today's lessons, unread messages, unpaid lessons, and attention items.
- One-tap `🌅 Подготовить день` / `🌙 Закрыть день` / `▶️ Разобрать всё` depending on local time.
- Compact daily actions: Today, Students, Messages, Book, Payments, Search, Channel, Parents, Ask Adelia.
- Rare functions moved under `••• Ещё`; nothing is removed.
- Settings remain one tap away.

## Navigation
- `/admin`, admin `/start`, and admin `🏠 Главная` now render the same home screen.
- UX settings screens use consistent `⬅️ Назад` + `🏠 Главная` navigation where applicable.
- Channel root uses the existing working `admin_free_windows` callback.

## Full function access
`••• Ещё` includes students, lessons, schedule, windows, statistics, prices, parents, payment methods, swaps, Adelia broadcasts, Adelia channel posts, system, and teacher information.

## Safety
- No database, `.env`, Telegram token, OpenRouter key, Google credentials, or server venv are included in the release archive.
- Existing `/opt/tutorbot/tutor.db`, server credentials, and venv are preserved by `deploy_to_opt.sh`.
