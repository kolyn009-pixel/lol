#!/bin/sh
set -eu

APP_DIR="${1:-/opt/tutorbot}"
cd "$APP_DIR"
PYTHON="$APP_DIR/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON=python3
TMP="${TMPDIR:-/tmp}/adelia-v4-gate-$$"
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT INT TERM

echo "=== FETCH RELEASE ==="
git fetch origin release/adelia-unified-rc >/dev/null
RELEASE_HEAD="$(git rev-parse origin/release/adelia-unified-rc)"
echo "release: $RELEASE_HEAD"

mkdir -p "$TMP"
git archive "$RELEASE_HEAD" | tar -x -C "$TMP"

cd "$TMP"

echo "=== BASE RELEASE GATE ==="
sh scripts/release_readonly_check.sh "$APP_DIR"

echo "=== V4 REQUIRED FILES ==="
for f in \
  web/teacher.html \
  web/teacher_v4.css \
  web/teacher_v4.js \
  web/index.html \
  web/install_runtime.js \
  web/parent/index.html \
  web/parent/manifest.webmanifest \
  web/landing.html \
  web/landing.js \
  web/assets/icons/adelia-icon.svg; do
  test -f "$f" || { echo "MISSING $f"; exit 40; }
  echo "OK $f"
done

echo "=== V4 HTML CONTRACT ==="
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - <<'PY'
from pathlib import Path
import json

teacher = Path('web/teacher.html').read_text(encoding='utf-8')
student = Path('web/index.html').read_text(encoding='utf-8')
parent = Path('web/parent/index.html').read_text(encoding='utf-8')
landing = Path('web/landing.html').read_text(encoding='utf-8')
landing_js = Path('web/landing.js').read_text(encoding='utf-8')
v4js = Path('web/teacher_v4.js').read_text(encoding='utf-8')
v4css = Path('web/teacher_v4.css').read_text(encoding='utf-8')

# Teacher v4: one clean shell, no old conflicting runtime layers.
for marker in [
    '/app/teacher_v4.css?v=20260914-v4',
    '/app/teacher_v4.js?v=20260914-v4',
    'data-view="dashboard"',
    'data-view="schedule"',
    'data-view="students"',
    'data-view="homework"',
    'data-view="reviews"',
    'data-view="messages"',
    'data-view="payments"',
    'data-view="health"',
    '/app/assets/icons/adelia-icon.svg',
]:
    assert marker in teacher, ('teacher marker', marker)

for forbidden in [
    'stage11_runtime.js',
    'teacher_cascade.js',
    'teacher_crm_plus.js',
    'teacher_homework_modes.js',
    'teacher_homework_bridge.js',
    'teacher_desktop_v2.js',
    'teacher_stage2_workspace.js',
    'teacher_stage2_finance.js',
    'teacher_stage3_learning.js',
    'teacher_stage4_workspace.js',
    'teacher_stage5_polish.js',
    'teacher_runtime_hotfix.js',
]:
    assert forbidden not in teacher, ('old teacher runtime still loaded', forbidden)

assert 'MutationObserver' not in v4js
for marker in ['Аделия работает', '/api/health', 'AdeliaPWA', 'v4-menu-open']:
    assert marker in v4js, ('teacher_v4.js', marker)
for marker in ['.teacher-shell', '.v4-status', '.teacher-more', '@media(max-width:820px)']:
    assert marker in v4css, ('teacher_v4.css', marker)

# Student retains install runtime and canonical icon.
for marker in [
    '/app/assets/icons/adelia-icon.svg',
    '/app/manifest.webmanifest',
    '/app/install_runtime.js',
]:
    assert marker in student, ('student marker', marker)

# Parent paths must live under /app/parent/ and use the canonical icon.
for marker in [
    '/app/parent/manifest.webmanifest',
    '/app/parent/app.css',
    '/app/parent/app.js',
    '/app/parent/pwa.js',
    '/app/assets/icons/adelia-icon.svg',
]:
    assert marker in parent, ('parent marker', marker)
assert 'stage11_runtime.js' not in parent

manifest = json.loads(Path('web/parent/manifest.webmanifest').read_text(encoding='utf-8'))
assert manifest['id'] == '/app/parent/'
assert manifest['start_url'] == '/app/parent/'
assert manifest['scope'] == '/app/parent/'
assert manifest['display'] == 'standalone'
assert manifest['icons'] and manifest['icons'][0]['src'] == '/app/assets/icons/adelia-icon.svg'

# Landing branding is normalized at runtime to the same icon.
assert 'ensureBrandAssets' in landing_js
assert '/app/assets/icons/adelia-icon.svg' in landing_js
assert '<title>Николай Соловьев | Аделия TutorBot</title>' in landing

print('V4_WEB_CONTRACT=PASS')
PY

echo "=== JS STATIC SAFETY ==="
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - <<'PY'
from pathlib import Path
for path in [
    'web/teacher_v4.js',
    'web/landing.js',
]:
    text = Path(path).read_text(encoding='utf-8')
    assert '\x00' not in text, path
    assert '<<<<<<<' not in text and '>>>>>>>' not in text, path
    print('OK', path)
print('V4_JS_STATIC=PASS')
PY

echo "=== RESULT ==="
echo "ADELIA_V4_RELEASE_GATE=PASS"
echo "release: $RELEASE_HEAD"
