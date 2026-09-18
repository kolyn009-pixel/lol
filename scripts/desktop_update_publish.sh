#!/usr/bin/env bash
set -euo pipefail

BUNDLE="${1:-}"
CHANNEL="${2:-beta}"
TARGET="${3:-}"
ROOT="${ADELIA_DESKTOP_UPDATE_ROOT:-/var/www/adeliatutor/desktop-updates}"
BASE_URL="${ADELIA_DESKTOP_UPDATE_URL:-https://adeliatutor.ru/desktop-updates}"

case "$CHANNEL" in beta|stable) ;; *) echo "FAIL: channel must be beta or stable" >&2; exit 2;; esac
case "$TARGET" in win-x64|macos-arm64|macos-x64) ;; *) echo "FAIL: target must be win-x64, macos-arm64 or macos-x64" >&2; exit 3;; esac
test -d "$BUNDLE" || { echo "FAIL: bundle directory missing" >&2; exit 4; }
test -f "$BUNDLE/manifest.json" || { echo "FAIL: manifest.json missing" >&2; exit 5; }
test -f "$BUNDLE/release.json" || { echo "FAIL: release.json missing" >&2; exit 6; }

META="$(python3 - "$BUNDLE" "$CHANNEL" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve(); channel=sys.argv[2]
m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
r=json.loads((root/'release.json').read_text(encoding='utf-8'))
assert m.get('schema')==2
assert m.get('channel')==channel
assert r.get('channel')==channel
version=str(m.get('version') or '')
sha=str(m.get('git_sha') or '')
assert version and sha
if channel=='beta': assert '-beta.' in version
else: assert '-' not in version
for item in m.get('files') or []:
    p=root/item['name']; assert p.is_file(), p
    assert p.stat().st_size==int(item['size']), p
    h=hashlib.sha512(p.read_bytes()).hexdigest()
    assert h==item['sha512'], p
print(version+'|'+sha)
PY
)"
VERSION="${META%%|*}"
GIT_SHA="${META#*|}"
RELEASE_ID="${VERSION}--${GIT_SHA:0:12}"
RELEASES="$ROOT/releases/$CHANNEL/$TARGET"
LIVE_PARENT="$ROOT/$CHANNEL"
DEST="$RELEASES/$RELEASE_ID"
LIVE="$LIVE_PARENT/$TARGET"
PREVIOUS=""

mkdir -p "$RELEASES" "$LIVE_PARENT"
if [ -L "$LIVE" ]; then PREVIOUS="$(readlink -f "$LIVE" || true)"; fi
if [ -e "$DEST" ]; then
  echo "FAIL: immutable release already exists: $DEST" >&2
  exit 7
fi

TMP="$RELEASES/.incoming-$RELEASE_ID-$$"
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT
mkdir "$TMP"
cp -a "$BUNDLE"/. "$TMP"/
printf '%s\n' "$TARGET" > "$TMP/.adelia-update-target"
printf '%s\n' "$RELEASE_ID" > "$TMP/.adelia-release-id"
chmod -R a-w "$TMP"
mv "$TMP" "$DEST"
trap - EXIT

LINK_TMP="$LIVE_PARENT/.${TARGET}.next.$$"
ln -s "$DEST" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$LIVE"

echo "PUBLISHED_RELEASE=$DEST"
echo "PREVIOUS_RELEASE=${PREVIOUS:-none}"
echo "LIVE_CHANNEL=$LIVE"
echo "LIVE_TARGET=$(readlink -f "$LIVE")"

curl -fsS "$BASE_URL/$CHANNEL/$TARGET/release.json" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['channel']=='$CHANNEL'; assert d['version']=='$VERSION'; assert d['git_sha']=='$GIT_SHA'; print('HTTP_RELEASE_METADATA=OK')"
case "$TARGET" in
  win-x64) curl -fsSI "$BASE_URL/$CHANNEL/$TARGET/Adelia-latest-windows-x64.exe" >/dev/null ;;
  macos-arm64) curl -fsSI "$BASE_URL/$CHANNEL/$TARGET/Adelia-latest-macos-arm64.dmg" >/dev/null ;;
  macos-x64) curl -fsSI "$BASE_URL/$CHANNEL/$TARGET/Adelia-latest-macos-x64.dmg" >/dev/null ;;
esac
echo "HTTP_INSTALLER=OK"
echo "DESKTOP_UPDATE_PUBLISH=PASS"
