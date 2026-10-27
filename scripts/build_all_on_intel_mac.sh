#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == Darwin && "$(uname -m)" == x86_64 ]] || { echo 'Run this script on your Intel Mac, not in server SSH.' >&2; exit 2; }
for adelia_tool in git node npm python3 docker; do
 command -v "$adelia_tool" >/dev/null || { echo "Required tool missing: $adelia_tool" >&2; exit 3; }
done
node -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)' || { echo 'Node.js 22 or newer is required.' >&2; exit 4; }
docker info >/dev/null 2>&1 || { echo 'Start Docker Desktop, then run this command again.' >&2; exit 5; }
adelia_repo="$(cd "$(dirname "$0")/.." && pwd)"
[[ -z "$(git -C "$adelia_repo" status --porcelain --untracked-files=no)" ]] || { echo 'Build checkout has modified tracked source files. Use a separate clean checkout.' >&2; exit 6; }
adelia_sha="$(git -C "$adelia_repo" rev-parse HEAD)"
adelia_version="$(cd "$adelia_repo/desktop" && node -p "require('./package.json').version")"
adelia_output="${ADELIA_BUILD_OUTPUT:-$HOME/Desktop/Adelia-${adelia_version}-${adelia_sha:0:12}}"
[[ ! -e "$adelia_output" ]] || { echo "Output already exists: $adelia_output" >&2; exit 7; }
mkdir -p "$adelia_output"
exec > >(tee "$adelia_output/build.log") 2>&1
export ADELIA_BUILD_SHA="$adelia_sha"
export CSC_IDENTITY_AUTO_DISCOVERY=false
cd "$adelia_repo/desktop"
npm install --no-audit --no-fund --package-lock=false
npm run selftest
node ../scripts/student_chat_draft_selftest.cjs
node ../scripts/group_chat_selftest.cjs
node ../scripts/onboarding_confirmation_selftest.cjs
python3 ../scripts/learning_hub_selftest.py
for adelia_arch in x64 arm64; do
 npm run "dist:mac:$adelia_arch" -- --publish never "--config.directories.output=dist/local-macos-$adelia_arch"
 python3 publish_updates.py "dist/local-macos-$adelia_arch" "$adelia_output/macos-$adelia_arch" --platform mac --arch "$adelia_arch" --channel beta --version "$adelia_version" --git-sha "$adelia_sha"
done
adelia_image="${ADELIA_WINDOWS_BUILDER_IMAGE:-electronuserland/builder:wine}"
docker pull --platform linux/amd64 "$adelia_image"
adelia_digest="$(docker image inspect "$adelia_image" --format '{{index .RepoDigests 0}}')"
[[ "$adelia_digest" == *@sha256:* ]] || { echo 'Unable to pin Windows builder image digest.' >&2; exit 8; }
printf '%s\n' "$adelia_digest" > "$adelia_output/windows-builder-image.txt"
docker run --rm --platform linux/amd64 \
 -e ADELIA_BUILD_SHA="$adelia_sha" -e CSC_IDENTITY_AUTO_DISCOVERY=false \
 -v "$adelia_repo:/project" \
 -v adelia-windows-build-node-modules:/project/desktop/node_modules \
 -w /project/desktop "$adelia_digest" \
 /bin/bash -lc 'npm install --no-audit --no-fund --package-lock=false && npm run dist:win -- --publish never --config.directories.output=dist/local-windows-x64'
python3 publish_updates.py dist/local-windows-x64 "$adelia_output/win-x64" --platform win --arch x64 --channel beta --version "$adelia_version" --git-sha "$adelia_sha"
python3 - "$adelia_output" "$adelia_sha" <<'PY'
import hashlib,json,sys,zipfile
from pathlib import Path
root=Path(sys.argv[1]);sha=sys.argv[2]
for name in ('macos-x64','macos-arm64','win-x64'):
 p=root/name;m=json.loads((p/'manifest.json').read_text(encoding='utf-8'))
 assert m['git_sha']==sha
 for item in m['files']:
  f=p/item['name'];assert f.stat().st_size==item['size']
  h=hashlib.sha512()
  with f.open('rb') as stream:
   for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
  assert h.hexdigest()==item['sha512']
 with zipfile.ZipFile(root/(name+'.zip'),'w',compression=zipfile.ZIP_STORED) as archive:
  for f in p.iterdir():
   if f.is_file():archive.write(f,f.name)
print('ALL_THREE_BUNDLES_VERIFIED')
PY
printf 'ALL_DESKTOP_BUILDS_OK\nFiles: %s\n' "$adelia_output"
open "$adelia_output"
