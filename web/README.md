# Аделия | TutorBot — web portal

Веб-интерфейс TutorBot. Первая версия запускается без сборщика и не затрагивает production-бота.

Откройте `index.html` локально или разместите каталог `web/` на статическом хостинге.

## Лендинг E («Журнал») — предпросмотр

Новая версия главной в стиле дизайн-системы «Журнал»: `landing-e.html` + `landing-e.css` + `landing-e.js`,
общие токены — `tokens.css` (основа и для будущего перевода кабинетов). Старый `landing.html` не тронут.

- Просмотр: каталог `web/` отдаётся nginx как `/app/`, поэтому новая версия открывается по
  `https://adeliatutor.ru/app/landing-e.html` без изменений сервера. Все пути к ресурсам абсолютные (`/app/…`),
  так что страница работает и из корня сайта.
- Сделать главной: главная — это `/var/www/adeliatutor.ru/index.html` (копия `landing.html`). После резервной копии:
  `ln -sfn /opt/adelia-current/web/landing-e.html /var/www/adeliatutor.ru/index.html`.
- Данные: цены — `/api/public/prices`, группы и события — `/api/public/opportunities`,
  отзывы — `/api/public/reviews` (те же API, что у `landing.js`). Без ответа API остаются статические тексты.

TODO:
- Шрифты сейчас из Google Fonts (`<link>` в `landing-e.html`). Перейти на self-host (woff2, кириллица, `font-display: swap`):
  для пользователей из России Google Fonts может грузиться медленно.
- Заглушки в квадратных скобках: размер группы `[N]`, фото, цитата и строка об опыте преподавателя.
