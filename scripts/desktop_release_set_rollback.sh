#!/usr/bin/env bash
set -euo pipefail

CHANNEL="${1:-beta}"
RELEASE_ID="${2:-}"
ROOT="${ADELIA_DESKTOP_UPDATE_ROOT:-/var/www/adeliatutor/desktop-updates}"
BASE_URL="${ADELIA_DESKTOP_UPDATE_URL:-https://adeliatutor.ru/desktop-updates}"

case "$CHANNEL" in beta|stable) ;; *) echo "FAIL: channel must be beta or stable" >&2; exit 2;; esac
test -n "$RELEASE_ID" || { echo "FAIL: explicit release-set id required" >&2; exit 3; }

DEST="$ROOT/releases/$CHANNEL/$RELEASE_ID"
LIVE="$ROOT/$CHANNEL"
test -d "$DEST" || { echo "FAIL: release set not found: $DEST" >&2; exit 4; }
test -f "$DEST/release-set.json" || { echo "FAIL: release-set.json missing" >&2; exit 5; }

META="$(python3 - "$DEST/release-set.json" "$CHANNEL" <<'PY'
import json,sys
p,channel=sys.argv[1:]
d=json.load(open(p,encoding="utf-8"))
assert d.get("schema")==1
assert d.get("channel")==channel
assert d.get("targets")==["win-x64","macos-arm64","macos-x64"]
assert d.get("version") and d.get("git_sha")
print(str(d["version"])+"|"+str(d["git_sha"]))
PY
)"
VERSION="${META%%|*}"
GIT_SHA="${META#*|}"

for target in win-x64 macos-arm64 macos-x64; do
  test -f "$DEST/$target/release.json" || { echo "FAIL: $target release metadata missing" >&2; exit 6; }
  test "$(cat "$DEST/$target/.adelia-update-target")" = "$target" || { echo "FAIL: $target identity mismatch" >&2; exit 7; }
done

CURRENT="$(readlink -f "$LIVE" 2>/dev/null || true)"
test "$CURRENT" != "$DEST" || { echo "FAIL: requested release set is already live" >&2; exit 8; }

echo "ROLLBACK_FROM=${CURRENT:-none}"
echo "ROLLBACK_TO=$DEST"

LINK_TMP="$ROOT/.${CHANNEL}.rollback.$$"
ln -s "$DEST" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$LIVE"
test "$(readlink -f "$LIVE")" = "$DEST"

restore_current(){
  rc=$?
  set +e
  if [ -n "$CURRENT" ] && [ -d "$CURRENT" ]; then
    rb="$ROOT/.${CHANNEL}.restore.$$"
    ln -s "$CURRENT" "$rb"
    mv -Tf "$rb" "$LIVE"
    echo "ROLLBACK_VERIFY_RESTORED=$CURRENT"
  fi
  exit "$rc"
}
trap restore_current ERR

for target in win-x64 macos-arm64 macos-x64; do
  curl -fsS "$BASE_URL/$CHANNEL/$target/release.json" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['channel']=='$CHANNEL'; assert d['version']=='$VERSION'; assert d['git_sha']=='$GIT_SHA'"
  echo "HTTP $target=OK"
done

trap - ERR
echo "DESKTOP_RELEASE_SET_ROLLBACK=PASS"
echo "CHANNEL=$CHANNEL"
echo "VERSION=$VERSION"
echo "GIT_SHA=$GIT_SHA"
echo "LIVE_RELEASE_SET=$DEST"
