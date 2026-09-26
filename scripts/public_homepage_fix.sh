#!/usr/bin/env bash
set -euo pipefail
ROOT="/var/www/adeliatutor.ru"
CURRENT="/opt/adelia-current"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="/opt/tutorbot/deploy_backups/public_homepage_$STAMP"

echo "===== 1. PRECHECK ====="
test -f "$ROOT/index.html"; test -f "$ROOT/landing.js"
test -f "$CURRENT/web/assets/icons/adelia-icon-32.png"
test -f "$CURRENT/web/assets/icons/adelia-icon-180.png"
test -f "$CURRENT/web/assets/icons/adelia-icon-32.png"
echo "PRECHECK=PASS"

echo "===== 2. BACKUP ====="
mkdir -p "$BACKUP"
cp -a "$ROOT/index.html" "$BACKUP/index.html"
cp -a "$ROOT/landing.js" "$BACKUP/landing.js"
for f in favicon.ico adelia-favicon-32.png adelia-apple-touch-icon-180.png adelia-tab-20260915_151502.png; do [ -f "$ROOT/$f" ] && cp -a "$ROOT/$f" "$BACKUP/$f"; done
echo "BACKUP=$BACKUP"

echo "===== 3. CANONICAL ICONS ====="
cp -a "$CURRENT/web/assets/icons/adelia-icon-32.png" "$ROOT/adelia-favicon-32.png"
cp -a "$CURRENT/web/assets/icons/adelia-icon-180.png" "$ROOT/adelia-apple-touch-icon-180.png"
cp -a "$CURRENT/web/assets/icons/adelia-icon-32.png" "$ROOT/favicon.ico"
echo "ICONS_COPIED=PASS"

echo "===== 4. HOMEPAGE BRANDING ====="
python3 - <<'PY'
from pathlib import Path
root=Path("/var/www/adeliatutor.ru")
p=root/"index.html"; s=p.read_text(encoding="utf-8")
for old,new in {
"Аделия TutorBot — единая система обучения.":"Аделия — единое пространство обучения.",
"<title>Николай Соловьев | Аделия TutorBot</title>":"<title>Николай Соловьев | Аделия</title>",
'<link rel="icon" type="image/png" href="/adelia-tab-20260915_151502.png">':'<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/adelia-favicon-32.png?v=20260926-brand5"><link rel="apple-touch-icon" sizes="180x180" href="/adelia-apple-touch-icon-180.png?v=20260926-brand5">',
"<small>TutorBot</small>":"<small>Образовательное пространство</small>",
'<span class="kicker">Не просто бот</span>':'<span class="kicker">Единое пространство</span>',
'<div class="sync-badge">● Синхронизировано с TutorBot</div>':'<div class="sync-badge">● Синхронизировано с Аделией</div>',
'<p class="muted section-intro">Стоимость синхронизируется с TutorBot.</p>':'<p class="muted section-intro">Актуальная стоимость загружается автоматически.</p>',
"<span>TutorBot</span>":"<span>Образовательное пространство</span>",
}.items():
    if old not in s: print("WARN_MISSING_INDEX_PATTERN=",old)
    s=s.replace(old,new)
p.write_text(s,encoding="utf-8")

p=root/"landing.js"; s=p.read_text(encoding="utf-8")
for old,new in {
"Актуальные направления и цены появятся после подключения сайта к TutorBot.":"Актуальные направления и цены временно недоступны. Попробуйте обновить страницу чуть позже.",
"Стоимость, оплаты, чеки и история операций всегда под рукой и синхронизированы с TutorBot.":"Стоимость, оплаты, чеки и история операций всегда под рукой и синхронизированы с Аделией.",
}.items():
    if old not in s: print("WARN_MISSING_JS_PATTERN=",old)
    s=s.replace(old,new)
p.write_text(s,encoding="utf-8")
PY
echo "BRANDING_UPDATED=PASS"

echo "===== 5. VERIFY ====="
if grep -nEi 'TutorBot|Tutor Bot' "$ROOT/index.html" "$ROOT/landing.js" \
  | grep -vE 'https://t\.me/AdeliaTutorBot(["/?#]|$)'; then
  echo "LEGACY_HOMEPAGE_BRAND=FAIL"; cp -a "$BACKUP/index.html" "$ROOT/index.html"; cp -a "$BACKUP/landing.js" "$ROOT/landing.js"; exit 1
fi
echo "LEGACY_HOMEPAGE_BRAND=PASS"
test "$(sha256sum "$CURRENT/web/assets/icons/adelia-icon-32.png"|awk '{print $1}')" = "$(sha256sum "$ROOT/adelia-favicon-32.png"|awk '{print $1}')"
test "$(sha256sum "$CURRENT/web/assets/icons/adelia-icon-180.png"|awk '{print $1}')" = "$(sha256sum "$ROOT/adelia-apple-touch-icon-180.png"|awk '{print $1}')"
echo "ICON_HASHES=PASS"

echo "===== 6. NGINX / LIVE ====="
nginx -t
curl -fsS --connect-timeout 5 --max-time 15 https://adeliatutor.ru/ -o /tmp/adelia-homepage-live.html
grep -q '<title>Николай Соловьев | Аделия</title>' /tmp/adelia-homepage-live.html
! grep -iE 'TutorBot|Tutor Bot' /tmp/adelia-homepage-live.html \
  | grep -vE 'https://t\.me/AdeliaTutorBot(["/?#]|$)'
echo "LIVE_HOMEPAGE_BRAND=PASS"
for URL in "https://adeliatutor.ru/favicon.ico" "https://adeliatutor.ru/adelia-favicon-32.png?v=20260926-brand5" "https://adeliatutor.ru/adelia-apple-touch-icon-180.png?v=20260926-brand5"; do CODE="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15 "$URL")"; echo "$CODE $URL"; test "$CODE" = "200"; done
echo "LIVE_ICONS=PASS"

echo "===== 7. RELEASE UNCHANGED ====="
echo "ACTIVE_RELEASE=$(readlink -f "$CURRENT")"
echo "TG=$(systemctl is-active tutorbot.service)"
echo "VK=$(systemctl is-active tutorbot-vk.service)"
echo "WEB=$(systemctl is-active tutorbot-web.service)"
echo "===== RESULT ====="
echo "BACKUP=$BACKUP"
echo "PUBLIC_HOMEPAGE_FIX=PASS"
