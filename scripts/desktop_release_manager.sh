#!/usr/bin/env bash
set -euo pipefail

WIN_BUNDLE="${1:-}"
MAC_ARM_BUNDLE="${2:-}"
MAC_X64_BUNDLE="${3:-}"
CHANNEL="${4:-beta}"

ROOT="${ADELIA_DESKTOP_UPDATE_ROOT:-/var/www/adeliatutor/desktop-updates}"
BASE_URL="${ADELIA_DESKTOP_UPDATE_URL:-https://adeliatutor.ru/desktop-updates}"

case "$CHANNEL" in beta|stable) ;; *) echo "FAIL: channel must be beta or stable" >&2; exit 2;; esac

declare -A BUNDLES=(
  [win-x64]="$WIN_BUNDLE"
  [macos-arm64]="$MAC_ARM_BUNDLE"
  [macos-x64]="$MAC_X64_BUNDLE"
)
TARGETS=(win-x64 macos-arm64 macos-x64)

for target in "${TARGETS[@]}"; do
  bundle="${BUNDLES[$target]}"
  test -d "$bundle" || { echo "FAIL: $target bundle directory missing: $bundle" >&2; exit 3; }
  test -f "$bundle/manifest.json" || { echo "FAIL: $target manifest.json missing" >&2; exit 4; }
  test -f "$bundle/release.json" || { echo "FAIL: $target release.json missing" >&2; exit 5; }
done

echo "===== 1. PREFLIGHT ALL THREE BUNDLES ====="
META="$(python3 - "$CHANNEL" "$WIN_BUNDLE" "$MAC_ARM_BUNDLE" "$MAC_X64_BUNDLE" <<'PY'
import hashlib,json,sys
from pathlib import Path

channel=sys.argv[1]
entries=[
    ("win-x64",Path(sys.argv[2])),
    ("macos-arm64",Path(sys.argv[3])),
    ("macos-x64",Path(sys.argv[4])),
]
identity=None

for target,root in entries:
    m=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    r=json.loads((root/"release.json").read_text(encoding="utf-8"))
    assert m.get("schema")==2, (target,"schema")
    assert m.get("channel")==channel, (target,"manifest channel",m.get("channel"))
    assert r.get("channel")==channel, (target,"release channel",r.get("channel"))
    version=str(m.get("version") or "")
    sha=str(m.get("git_sha") or "")
    assert version and sha, (target,"identity")
    if channel=="beta":
        assert "-beta." in version, (target,version)
    else:
        assert "-" not in version, (target,version)
    current=(version,sha)
    if identity is None:
        identity=current
    assert current==identity, (target,current,identity)

    files=m.get("files") or []
    assert files, (target,"empty manifest")
    names={item["name"] for item in files}
    if target=="win-x64":
        assert "latest.yml" in names, names
        assert "Adelia-latest-windows-x64.exe" in names, names
    else:
        assert "latest-mac.yml" in names, names
        alias=f"Adelia-latest-macos-{'arm64' if target.endswith('arm64') else 'x64'}.dmg"
        assert alias in names, (target,names)

    for item in files:
        p=root/item["name"]
        assert p.is_file(), (target,p)
        assert p.stat().st_size==int(item["size"]), (target,p,"size")
        h=hashlib.sha512()
        with p.open("rb") as fh:
            for chunk in iter(lambda:fh.read(1024*1024),b""):
                h.update(chunk)
        assert h.hexdigest()==item["sha512"], (target,p,"sha512")
    print(f"PREFLIGHT {target}=OK",file=sys.stderr)

version,sha=identity
print(version+"|"+sha)
PY
)"
VERSION="${META%%|*}"
GIT_SHA="${META#*|}"
RELEASE_ID="${VERSION}--${GIT_SHA:0:12}"
RELEASES="$ROOT/releases/$CHANNEL"
DEST="$RELEASES/$RELEASE_ID"
LIVE="$ROOT/$CHANNEL"
PREVIOUS="$(readlink -f "$LIVE" 2>/dev/null || true)"

echo "VERSION=$VERSION"
echo "GIT_SHA=$GIT_SHA"
echo "RELEASE_ID=$RELEASE_ID"
echo "PREVIOUS_RELEASE=${PREVIOUS:-none}"

test ! -e "$DEST" || { echo "FAIL: immutable release set already exists: $DEST" >&2; exit 6; }

echo
echo "===== 2. STAGE IMMUTABLE RELEASE SET ====="
mkdir -p "$RELEASES"
TMP="$RELEASES/.incoming-$RELEASE_ID-$$"
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT INT TERM
mkdir -p "$TMP"

for target in "${TARGETS[@]}"; do
  mkdir "$TMP/$target"
  cp -a "${BUNDLES[$target]}"/. "$TMP/$target"/
  printf '%s\n' "$target" > "$TMP/$target/.adelia-update-target"
done

python3 - "$TMP" "$CHANNEL" "$VERSION" "$GIT_SHA" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
payload={
  "schema":1,
  "channel":sys.argv[2],
  "version":sys.argv[3],
  "git_sha":sys.argv[4],
  "targets":["win-x64","macos-arm64","macos-x64"],
}
(root/"release-set.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
PY
printf '%s\n' "$RELEASE_ID" > "$TMP/.adelia-release-set-id"
chmod -R a-w "$TMP"
mv "$TMP" "$DEST"
trap - EXIT INT TERM

echo "STAGED_RELEASE_SET=$DEST"

echo
echo "===== 3. ATOMIC CHANNEL SWITCH ====="
LINK_TMP="$ROOT/.${CHANNEL}.next.$$"
ln -s "$DEST" "$LINK_TMP"
mv -Tf "$LINK_TMP" "$LIVE"
test "$(readlink -f "$LIVE")" = "$DEST"
echo "LIVE_RELEASE_SET=$(readlink -f "$LIVE")"

rollback_live(){
  rc=$?
  set +e
  if [ -n "$PREVIOUS" ] && [ -d "$PREVIOUS" ]; then
    rb="$ROOT/.${CHANNEL}.rollback.$$"
    ln -s "$PREVIOUS" "$rb"
    mv -Tf "$rb" "$LIVE"
    echo "AUTO_ROLLBACK_TO=$PREVIOUS"
  else
    rm -f "$LIVE"
    echo "AUTO_ROLLBACK_TO=none"
  fi
  exit "$rc"
}
trap rollback_live ERR

echo
echo "===== 4. HTTP VERIFY WHOLE RELEASE SET ====="
for target in "${TARGETS[@]}"; do
  curl -fsS "$BASE_URL/$CHANNEL/$target/release.json" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['channel']=='$CHANNEL'; assert d['version']=='$VERSION'; assert d['git_sha']=='$GIT_SHA'"
  case "$target" in
    win-x64)
      curl -fsSI "$BASE_URL/$CHANNEL/$target/Adelia-latest-windows-x64.exe" >/dev/null
      curl -fsS "$BASE_URL/$CHANNEL/$target/latest.yml" >/dev/null
      ;;
    macos-arm64)
      curl -fsSI "$BASE_URL/$CHANNEL/$target/Adelia-latest-macos-arm64.dmg" >/dev/null
      curl -fsS "$BASE_URL/$CHANNEL/$target/latest-mac.yml" >/dev/null
      ;;
    macos-x64)
      curl -fsSI "$BASE_URL/$CHANNEL/$target/Adelia-latest-macos-x64.dmg" >/dev/null
      curl -fsS "$BASE_URL/$CHANNEL/$target/latest-mac.yml" >/dev/null
      ;;
  esac
  echo "HTTP $target=OK"
done

trap - ERR
echo
echo "========================================"
echo "DESKTOP_RELEASE_MANAGER=PASS"
echo "CHANNEL=$CHANNEL"
echo "VERSION=$VERSION"
echo "GIT_SHA=$GIT_SHA"
echo "LIVE_RELEASE_SET=$DEST"
echo "PREVIOUS_RELEASE_SET=${PREVIOUS:-none}"
echo "========================================"
