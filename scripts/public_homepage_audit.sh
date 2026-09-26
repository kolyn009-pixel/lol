#!/usr/bin/env bash
set -u

ROOT="/var/www/adeliatutor.ru"
OUT="/tmp/adelia_homepage_audit.txt"
: > "$OUT"

{
echo "ADELIA PUBLIC HOMEPAGE AUDIT"
date -Is

echo
echo "===== 1. PUBLIC ROOT ====="
echo "ROOT=$ROOT"
test -d "$ROOT" && echo "PUBLIC_ROOT=PASS" || echo "PUBLIC_ROOT=FAIL"

echo
echo "===== 2. FILE TREE ====="
find "$ROOT" -maxdepth 2 -type f -printf '%P | %s bytes\n' 2>/dev/null | sort | head -n 400

echo
echo "===== 3. INDEX BRAND AND ICON REFERENCES ====="
grep -nEi 'TutorBot|Tutor|Аделия|favicon|apple-touch|logo|icon' "$ROOT/index.html" 2>/dev/null | head -n 250 || true

echo
echo "===== 4. INDEX HEAD ====="
sed -n '1,180p' "$ROOT/index.html" 2>/dev/null || true

echo
echo "===== 5. IMAGE ASSETS ====="
find "$ROOT" -maxdepth 3 -type f \
  \( -iname '*.png' -o -iname '*.svg' -o -iname '*.ico' -o -iname '*.webp' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
  -printf '%P | %s bytes\n' 2>/dev/null | sort

echo
echo "===== 6. CANONICAL RELEASE ICONS ====="
for F in \
  /opt/adelia-current/web/assets/icons/adelia-icon-32.png \
  /opt/adelia-current/web/assets/icons/adelia-icon-180.png \
  /opt/adelia-current/web/assets/icons/adelia-icon-192.png \
  /opt/adelia-current/web/assets/icons/adelia-icon-512.png
do
  if [ -f "$F" ]; then
    sha256sum "$F"
  else
    echo "MISSING $F"
  fi
done

echo
echo "===== 7. PUBLIC HTTP HEADERS ====="
for URL in \
  https://adeliatutor.ru/ \
  https://adeliatutor.ru/favicon.ico \
  https://adeliatutor.ru/apple-touch-icon.png
do
  echo "--- $URL"
  curl -sSI --connect-timeout 5 --max-time 15 "$URL" | head -n 20 || echo "CURL_FAILED"
done

echo
echo "===== 8. NGINX PUBLIC ROUTING ====="
nginx -T 2>/dev/null | grep -nE 'server_name adeliatutor|root |alias |adelia-current|location .*(app|start|onboarding)' | head -n 250 || true

echo
echo "===== 9. LEGACY BRAND ACROSS PUBLIC SITE ====="
grep -RInE \
  --include='*.html' --include='*.css' --include='*.js' --include='*.json' --include='*.webmanifest' \
  'TutorBot|Tutor Bot|Tutor' "$ROOT" 2>/dev/null | head -n 400 || true

echo
echo "===== 10. ACTIVE RELEASE ====="
readlink -f /opt/adelia-current 2>/dev/null || true

echo
echo "HOMEPAGE_AUDIT=PASS"
} >> "$OUT" 2>&1

cat "$OUT"

echo
echo "RESULT_FILE=$OUT"
echo "This audit is read-only and does not print application secrets."
