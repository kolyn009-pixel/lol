#!/usr/bin/env bash
set -euo pipefail

ROOT="/var/www/adeliatutor.ru"
CURRENT="/opt/adelia-current"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="/opt/tutorbot/deploy_backups/public_homepage_$STAMP"

FAV_NAME="adelia-brand-favicon-32-20260926.png"
LOGO_NAME="adelia-brand-logo-192-20260926.png"
TOUCH_NAME="adelia-brand-touch-180-20260926.png"
CACHE="20260926-brand6"

echo "===== 1. PRECHECK ====="
test -f "$ROOT/index.html"
test -f "$ROOT/landing.js"
test -f "$CURRENT/web/assets/icons/adelia-icon-32.png"
test -f "$CURRENT/web/assets/icons/adelia-icon-180.png"
test -f "$CURRENT/web/assets/icons/adelia-icon-192.png"

python3 - <<'PY'
from pathlib import Path
import struct
checks=[
 (Path("/opt/adelia-current/web/assets/icons/adelia-icon-32.png"),32),
 (Path("/opt/adelia-current/web/assets/icons/adelia-icon-180.png"),180),
 (Path("/opt/adelia-current/web/assets/icons/adelia-icon-192.png"),192),
]
for p,n in checks:
    raw=p.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", p
    w,h=struct.unpack(">II",raw[16:24])
    assert (w,h)==(n,n),(p,w,h)
    print("PNG_SOURCE_OK",p,n)
PY
echo "PRECHECK=PASS"

echo
echo "===== 2. BACKUP ====="
mkdir -p "$BACKUP"
cp -a "$ROOT/index.html" "$BACKUP/index.html"
cp -a "$ROOT/landing.js" "$BACKUP/landing.js"
for f in favicon.ico adelia-favicon-32.png adelia-apple-touch-icon-180.png adelia-tab-20260915_151502.png "$FAV_NAME" "$LOGO_NAME" "$TOUCH_NAME"; do
  [ -f "$ROOT/$f" ] && cp -a "$ROOT/$f" "$BACKUP/$f"
done
echo "BACKUP=$BACKUP"

echo
echo "===== 3. COPY CANONICAL ICONS WITH NEW URLS ====="
cp -a "$CURRENT/web/assets/icons/adelia-icon-32.png"  "$ROOT/$FAV_NAME"
cp -a "$CURRENT/web/assets/icons/adelia-icon-192.png" "$ROOT/$LOGO_NAME"
cp -a "$CURRENT/web/assets/icons/adelia-icon-180.png" "$ROOT/$TOUCH_NAME"
echo "CANONICAL_ICON_FILES=PASS"

echo
echo "===== 4. UPDATE HOMEPAGE ====="
FAV_NAME="$FAV_NAME" LOGO_NAME="$LOGO_NAME" TOUCH_NAME="$TOUCH_NAME" CACHE="$CACHE" python3 - <<'PY'
from pathlib import Path
import os,re

root=Path("/var/www/adeliatutor.ru")
fav=os.environ["FAV_NAME"]; logo=os.environ["LOGO_NAME"]; touch=os.environ["TOUCH_NAME"]; cache=os.environ["CACHE"]

p=root/"index.html"
s=p.read_text(encoding="utf-8")

s=s.replace("Аделия TutorBot — единая система обучения.","Аделия — единое пространство обучения.")
s=s.replace("<title>Николай Соловьев | Аделия TutorBot</title>","<title>Николай Соловьев | Аделия</title>")
s=s.replace("<small>TutorBot</small>","<small>Образовательное пространство</small>")
s=s.replace('<span class="kicker">Не просто бот</span>','<span class="kicker">Единое пространство</span>')
s=s.replace('<div class="sync-badge">● Синхронизировано с TutorBot</div>','<div class="sync-badge">● Синхронизировано с Аделией</div>')
s=s.replace('<p class="muted section-intro">Стоимость синхронизируется с TutorBot.</p>','<p class="muted section-intro">Актуальная стоимость загружается автоматически.</p>')
s=s.replace("<span>TutorBot</span>","<span>Образовательное пространство</span>")

# Remove every old favicon/touch declaration, regardless of which previous fix produced it.
s=re.sub(r'<link\s+rel=["\']icon["\'][^>]*>','',s,flags=re.I)
s=re.sub(r'<link\s+rel=["\']apple-touch-icon["\'][^>]*>','',s,flags=re.I)

new_icons=(
 f'<link rel="icon" type="image/png" sizes="32x32" href="/{fav}?v={cache}">'
 f'<link rel="apple-touch-icon" sizes="180x180" href="/{touch}?v={cache}">'
)
s=s.replace("</title>","</title>"+new_icons,1)

# The visible brand image gets a fresh URL and a larger canonical source.
s=re.sub(
 r'<img\s+src=["\']/[^"\']*(?:adelia-favicon-32|adelia-brand-logo-[^"\']*)\.png(?:\?[^"\']*)?["\']\s+alt=["\']Аделия["\']\s+width=["\'](?:28|32)["\']\s+height=["\'](?:28|32)["\']>',
 lambda m: m.group(0).replace(re.search(r'src=["\'][^"\']+["\']',m.group(0)).group(0),f'src="/{logo}?v={cache}"'),
 s,
 flags=re.I
)
# Catch header/footer image forms even if attribute order differs.
s=s.replace('src="/adelia-favicon-32.png"',f'src="/{logo}?v={cache}"')
s=re.sub(r'src=["\']/adelia-brand-logo-[^"\']+\.png(?:\?[^"\']*)?["\']',f'src="/{logo}?v={cache}"',s)

p.write_text(s,encoding="utf-8")

p=root/"landing.js"
s=p.read_text(encoding="utf-8")
s=s.replace(
 "Актуальные направления и цены появятся после подключения сайта к TutorBot.",
 "Актуальные направления и цены временно недоступны. Попробуйте обновить страницу чуть позже."
)
s=s.replace(
 "Стоимость, оплаты, чеки и история операций всегда под рукой и синхронизированы с TutorBot.",
 "Стоимость, оплаты, чеки и история операций всегда под рукой и синхронизированы с Аделией."
)
p.write_text(s,encoding="utf-8")
PY
echo "HOMEPAGE_UPDATED=PASS"

echo
echo "===== 5. LOCAL VERIFICATION ====="
grep -q "/$FAV_NAME?v=$CACHE" "$ROOT/index.html"
grep -q "/$LOGO_NAME?v=$CACHE" "$ROOT/index.html"
grep -q "/$TOUCH_NAME?v=$CACHE" "$ROOT/index.html"

if grep -nE 'adelia-tab-20260915_151502|src="/adelia-favicon-32\.png"' "$ROOT/index.html"; then
  echo "OLD_ICON_REFERENCE=FAIL"
  cp -a "$BACKUP/index.html" "$ROOT/index.html"
  cp -a "$BACKUP/landing.js" "$ROOT/landing.js"
  exit 1
fi

if grep -nEi 'TutorBot|Tutor Bot' "$ROOT/index.html" "$ROOT/landing.js" | grep -vE 'https://t\.me/AdeliaTutorBot(["/?#]|$)'; then
  echo "LEGACY_HOMEPAGE_BRAND=FAIL"
  cp -a "$BACKUP/index.html" "$ROOT/index.html"
  cp -a "$BACKUP/landing.js" "$ROOT/landing.js"
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
import struct
checks=[
 (Path("/var/www/adeliatutor.ru/adelia-brand-favicon-32-20260926.png"),32),
 (Path("/var/www/adeliatutor.ru/adelia-brand-touch-180-20260926.png"),180),
 (Path("/var/www/adeliatutor.ru/adelia-brand-logo-192-20260926.png"),192),
]
for p,n in checks:
    raw=p.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", p
    w,h=struct.unpack(">II",raw[16:24])
    assert (w,h)==(n,n),(p,w,h)
    print("PUBLIC_PNG_OK",p,n)
PY
echo "LOCAL_VERIFICATION=PASS"

echo
echo "===== 6. NGINX / LIVE VERIFICATION ====="
nginx -t
curl -fsS --connect-timeout 5 --max-time 15 https://adeliatutor.ru/ -o /tmp/adelia-homepage-live.html

grep -q "/$FAV_NAME?v=$CACHE" /tmp/adelia-homepage-live.html
grep -q "/$LOGO_NAME?v=$CACHE" /tmp/adelia-homepage-live.html
grep -q "/$TOUCH_NAME?v=$CACHE" /tmp/adelia-homepage-live.html

for FILE in "$FAV_NAME" "$LOGO_NAME" "$TOUCH_NAME"; do
  URL="https://adeliatutor.ru/$FILE?v=$CACHE"
  META="$(curl -sS -o /dev/null -w '%{http_code} %{content_type}' --connect-timeout 5 --max-time 15 "$URL")"
  echo "$META $URL"
  case "$META" in
    "200 image/png"*) ;;
    *) echo "LIVE_ICON_RESPONSE=FAIL"; exit 1 ;;
  esac
done

if grep -iE 'TutorBot|Tutor Bot' /tmp/adelia-homepage-live.html | grep -vE 'https://t\.me/AdeliaTutorBot(["/?#]|$)'; then
  echo "LIVE_LEGACY_BRAND=FAIL"
  exit 1
fi

echo "LIVE_HOMEPAGE=PASS"

echo
echo "===== 7. RELEASE UNCHANGED ====="
echo "ACTIVE_RELEASE=$(readlink -f "$CURRENT")"
echo "TG=$(systemctl is-active tutorbot.service)"
echo "VK=$(systemctl is-active tutorbot-vk.service)"
echo "WEB=$(systemctl is-active tutorbot-web.service)"
echo "No service restart was required."

echo
echo "===== RESULT ====="
echo "BACKUP=$BACKUP"
echo "PUBLIC_HOMEPAGE_ICON_CACHE_BUST=PASS"
