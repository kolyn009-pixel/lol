#!/usr/bin/env bash
set -euo pipefail

CHANNEL="${1:-beta}"
TARGET="${2:-}"
RELEASE_ID="${3:-}"
ROOT="${ADELIA_DESKTOP_UPDATE_ROOT:-/var/www/adeliatutor/desktop-updates}"
BASE_URL="${ADELIA_DESKTOP_UPDATE_URL:-https://adeliatutor.ru/desktop-updates}"

case "$CHANNEL" in beta|stable) ;; *) echo "FAIL: channel must be beta or stable" >&2; exit 2;; esac
case "$TARGET" in win-x64|macos-arm64|macos-x64) ;; *) echo "FAIL: invalid target" >&2; exit 3;; esac
test -n "$RELEASE_ID" || { echo "FAIL: explicit release id required" >&2; exit 4; }

RELEASES="$ROOT/releases/$CHANNEL/$TARGET"
DEST="$RELEASES/$RELEASE_ID"
LIVE_PARENT="$ROOT/$CHANNEL"
LIVE="$LIVE_PARENT/$TARGET"
test -d "$DEST" || { echo "FAIL: rollback release not found: $DEST" >&2; exit 5; }
test -f "$DEST/release.json" || { echo "FAIL: release.json missing in rollback target" >&2; exit 6; }
test "$(cat "$DEST/.adelia-update-target")" = "$TARGET" || { echo "FAIL: target identity mismatch" >&2; exit 7; }

python3 - "$DEST/release.json" "$CHANNEL" <<'PY'
import json,sys
p,channel=sys.argv[1:]
d=json.load(open(p,encoding='utf-8'))
assert d.get('channel')==channel
assert d.get('version')
assert d.get('git_sha')
print('ROLLBACK_METADATA=OK')
PY

CURRENT="$(readlink -f "$LIVE" 2>/dev/null || true)"
test "$CURRENT" != "$DEST" || { echo "FAIL: requested release is already live" >&2; exit 8; }

LINK_TMP="$LIVE_PARENT/.${TARGET}.rollback.$$"
ln -s "$DEST" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$LIVE"

echo "ROLLED_BACK_FROM=${CURRENT:-none}"
echo "ROLLED_BACK_TO=$DEST"
test "$(readlink -f "$LIVE")" = "$DEST"

curl -fsS "$BASE_URL/$CHANNEL/$TARGET/release.json" | python3 - "$DEST/release.json" <<'PY'
import json,sys
expected=json.load(open(sys.argv[1],encoding='utf-8'))
live=json.load(sys.stdin)
assert live.get('channel')==expected.get('channel')
assert live.get('version')==expected.get('version')
assert live.get('git_sha')==expected.get('git_sha')
print('HTTP_ROLLBACK_METADATA=OK')
PY

echo "DESKTOP_UPDATE_ROLLBACK=PASS"
