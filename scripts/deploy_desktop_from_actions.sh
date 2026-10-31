#!/usr/bin/env bash
# Download and publish all three verified platform bundles from a pinned build.
set -euo pipefail
adelia_sha="${1:?Full reviewed commit required}"
adelia_run="${2:?Successful GitHub Actions run ID required}"
[[ "$adelia_sha" =~ ^[0-9a-f]{40}$ && "$adelia_run" =~ ^[0-9]+$ ]] || exit 2
command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required on this server.' >&2; exit 3; }
gh auth status >/dev/null 2>&1 || { echo 'Authenticate GitHub CLI for kolyn009-pixel/lol before publishing.' >&2; exit 4; }
adelia_metadata="$(gh api "repos/kolyn009-pixel/lol/actions/runs/$adelia_run" --jq '[.head_sha,.conclusion,.name]|@tsv')"
[[ "$adelia_metadata" == "$adelia_sha"$'\t''success'$'\t''Adelia desktop installers' ]] || { echo 'Run must have succeeded for the exact reviewed commit.' >&2; exit 5; }
adelia_live=/var/www/adeliatutor/desktop-updates/beta
[[ ! -e "$adelia_live" || -L "$adelia_live" ]] || { echo 'Existing beta feed is a directory; inspect nginx and migrate it before publication.' >&2; exit 6; }
adelia_stage="$(mktemp -d /opt/tutorbot/desktop-stage.XXXXXX)"
chmod 700 "$adelia_stage"
for adelia_target in windows-x64 macos-arm64 macos-x64; do
 gh run download "$adelia_run" --repo kolyn009-pixel/lol --name "adelia-desktop-$adelia_target-$adelia_sha" --dir "$adelia_stage/$adelia_target"
done
python3 - "$adelia_stage" "$adelia_sha" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sha=sys.argv[2]
for target in ('windows-x64','macos-arm64','macos-x64'):
 p=root/target
 if any(x.is_symlink() for x in p.rglob('*')):raise SystemExit('Unexpected symlink in bundle')
 m=json.loads((p/'manifest.json').read_text(encoding='utf-8'))
 if m.get('git_sha')!=sha:raise SystemExit('Bundle commit mismatch')
 for item in m.get('files',[]):
  name=item['name']
  if Path(name).name!=name or not name:raise SystemExit('Unexpected bundle path')
PY
git -C /opt/tutorbot show "$adelia_sha:scripts/desktop_release_manager.sh" > "$adelia_stage/publish.sh"
bash "$adelia_stage/publish.sh" "$adelia_stage/windows-x64" "$adelia_stage/macos-arm64" "$adelia_stage/macos-x64" beta
echo "Verified source bundles retained: $adelia_stage"
