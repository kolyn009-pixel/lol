# Выкладка Аделии с терминала Mac

Текущая схема сервера (29 сентября 2026): `/opt/adelia-current` — ссылка на каталог в `/opt/adelia-releases/`. Nginx читает `/opt/adelia-current/web/` и направляет API на `127.0.0.1:8876`. Шесть служб Аделии работают из `/opt/adelia-current`; веб-служба — `tutorbot-web.service`. SQLite для неё указан явно: `/opt/tutorbot/tutor.db`. Локальная Git-копия `/opt/tutorbot` содержит изменения и данные вне Git. Не выполняйте там `git pull`, `git reset --hard`, `git clean` или `scripts/adelia_release.sh deploy`.

PR #4 ещё открыт. Переключение релиза возможно только после проверки остальных пяти служб, путей данных и содержимого нового релиза. Нативную сборку macOS надо проверить на Mac отдельно; сервер её не собирает.

## Следующая проверка без изменений на сервере

В уже открытом SSH-сеансе выполните:

```bash
for s in tutorbot.service tutorbot-vk.service tutorbot-web.service adelia-homework-delivery.service adelia-receipt-archive.service adelia-telemost-precreate.service; do
  echo "SERVICE $s"
  systemctl show "$s" -p WorkingDirectory -p EnvironmentFiles --no-pager
  systemctl show "$s" -p ExecStart --value | sed -E "s/(token|password|secret|key)[^ ;}]*/[скрыто]/Ig"
done
echo 'RELEASE LINKS'
find /opt/adelia-current -maxdepth 2 -type l -printf '%p -> %l\n'
echo 'DATA DIRS'
find /opt/adelia-current -maxdepth 2 -type d \( -name storage -o -name uploads -o -name data \) -print
echo 'DATABASE FILES'
find /opt/adelia-current -maxdepth 2 -type f \( -name '*.db' -o -name '*.sqlite*' \) -printf '%p\n'
echo 'RELEASE METADATA'
ls -ld /opt/adelia-releases /opt/adelia-current
ls -l /opt/adelia-current/.adelia_release /opt/tutorbot/.adelia_release 2>/dev/null || true
```

Не присылайте содержимое `/etc/tutorbot/*.env`, токенов и базы. Если вывод `ExecStart` всё же содержит секрет, удалите его перед отправкой. Эта проверка нужна, чтобы выяснить, нет ли записываемых файлов внутри каталога релиза и все ли процессы используют постоянную базу.

## Порядок выпуска после проверки

1. В отдельный новый каталог `/opt/adelia-releases/<commit>` извлечь точно зафиксированный commit из Git, не меняя рабочее дерево `/opt/tutorbot`.
2. Сравнить новый каталог с текущим: убедиться, что все активные скрипты и статические ресурсы присутствуют, а данные и конфигурация остаются вне каталога релиза.
3. Проверить Python/JS, ресурсы PWA и маршрут API на копии данных. Сделать online-backup SQLite с учётом WAL и проверить `PRAGMA quick_check`; сохранить старую цель ссылки и SHA.
4. Атомарно переключить `/opt/adelia-current`, перезапустить все шесть служб, проверить локальный и внешний health, кабинеты ученика/родителя/учителя, файл ДЗ, QR и очередь подтверждений. При сбое вернуть ссылку и перезапустить службы. Базу автоматически назад не восстанавливать, чтобы не потерять записи после переключения.

Команды переключения будут зафиксированы после этой проверки путей. Существующий `scripts/adelia_release.sh` рассчитан на Git-копию без ссылки и специально блокирует этот сервер.
