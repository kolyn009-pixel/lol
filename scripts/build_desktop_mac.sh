#!/usr/bin/env bash
set -euo pipefail
[[ $(uname -s) == Darwin ]] || { echo 'Run in the MacBook terminal, outside SSH.' >&2; exit 2; }
ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
ARCH=${1:-native}
if [[ $ARCH == native ]]; then
  case $(uname -m) in arm64) ARCH=arm64;; x86_64) ARCH=x64;; *) echo 'Unsupported Mac architecture'; exit 2;; esac
fi
case "$ARCH" in arm64|x64|both) ;; *) echo 'Usage: bash scripts/build_desktop_mac.sh native|arm64|x64|both'; exit 2;; esac
for command in node npm python3; do command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 2; }; done
node -e "if(+process.versions.node.split('.')[0]<22)throw new Error('Node.js 22 or newer is required')"
if [[ -z ${ADELIA_BUILD_SHA:-} ]]; then
  ADELIA_BUILD_SHA=$(git -C "$ROOT" rev-parse HEAD)
fi
export ADELIA_BUILD_SHA
export CSC_IDENTITY_AUTO_DISCOVERY=false
cd "$ROOT/desktop"
npm install --no-audit --no-fund --package-lock=false
npm run selftest
targets=($ARCH)
[[ $ARCH != both ]] || targets=(arm64 x64)
for target in "${targets[@]}"; do
  output="dist/macos-$target"
  bundle="beta-bundle/$ADELIA_BUILD_SHA/macos-$target"
  [[ ! -e $bundle ]] || { echo "Build bundle already exists: $bundle. It was preserved." >&2; exit 2; }
  npm run "dist:mac:$target" -- --publish never "--config.directories.output=$output"
  version=$(node -p "require('./package.json').version")
  python3 publish_updates.py "$output" "$bundle" --platform mac --arch "$target" --channel beta --version "$version" --git-sha "$ADELIA_BUILD_SHA"
  echo "MAC_BUILD_OK: $ROOT/desktop/$bundle"
done
open "$ROOT/desktop/beta-bundle/$ADELIA_BUILD_SHA"
