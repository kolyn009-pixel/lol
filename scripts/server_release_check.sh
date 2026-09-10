#!/bin/sh
set -eu

APP_DIR="${1:-/opt/tutorbot}"
BRANCH="${TUTORBOT_RELEASE_BRANCH:-unified-lesson-flow}"
EXPECTED_BASE="23e621f70fd44dbdbe062c893ed20da57db4a747"

cd "$APP_DIR"

echo "=== 1. CURRENT STATE ==="
printf "dir:    %s\n" "$APP_DIR"
printf "branch: %s\n" "$(git branch --show-current)"
printf "head:   %s\n" "$(git rev-parse HEAD)"
git status --short

echo
echo "=== 2. BACKUP ==="
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$APP_DIR/deploy_backups/release_$STAMP"
mkdir -p "$BACKUP_DIR"
[ -f tutor.db ] && cp -a tutor.db "$BACKUP_DIR/tutor.db"
[ -f token.json ] && cp -a token.json "$BACKUP_DIR/token.json"
[ -f credentials.json ] && cp -a credentials.json "$BACKUP_DIR/credentials.json"
git rev-parse HEAD > "$BACKUP_DIR/git_head.txt"
git status --porcelain > "$BACKUP_DIR/git_status.txt"
echo "backup: $BACKUP_DIR"

echo
echo "=== 3. FETCH RELEASE BRANCH ==="
git fetch origin "$BRANCH" main
REMOTE_HEAD=$(git rev-parse "origin/$BRANCH")
MAIN_HEAD=$(git rev-parse origin/main)
printf "origin/%s: %s\n" "$BRANCH" "$REMOTE_HEAD"
printf "origin/main: %s\n" "$MAIN_HEAD"

if ! git merge-base --is-ancestor "$EXPECTED_BASE" "$REMOTE_HEAD"; then
    echo "ERROR: release branch no longer descends from expected production checkpoint $EXPECTED_BASE"
    exit 10
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: working tree is dirty. Nothing was switched."
    echo "Commit/stash/inspect local production changes first."
    exit 11
fi

echo
echo "=== 4. SWITCH TO RELEASE BRANCH ==="
git checkout -B "$BRANCH" "origin/$BRANCH"
printf "release head: %s\n" "$(git rev-parse HEAD)"

echo
echo "=== 5. PYTHON PREFLIGHT ==="
PYTHON="$APP_DIR/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON=python3
fi
"$PYTHON" preflight_check.py

echo
echo "=== 6. TARGETED IMPORT CHECK ==="
"$PYTHON" - <<'PY'
modules = [
    'core.calendar_policy',
    'core.lesson_lifecycle',
    'core.post_lesson',
    'core.teacher_tasks',
    'handlers.calendar_runtime',
    'handlers.receipt_center',
    'handlers.post_lesson_review',
    'handlers.teacher_end_notifications',
    'handlers.schedule_exceptions_v2',
    'handlers.briefs_v2',
    'vk_adapter.teacher_post_lesson',
]
for name in modules:
    __import__(name)
    print('OK import', name)
PY

echo
echo "=== 7. DIFF SUMMARY VS PRODUCTION CHECKPOINT ==="
git diff --stat "$EXPECTED_BASE"..HEAD
echo
printf "commits since checkpoint: "
git rev-list --count "$EXPECTED_BASE"..HEAD

echo
echo "=== 8. RESULT ==="
echo "RELEASE VALIDATION PASSED"
echo "No service was restarted by this script."
echo "Current checked-out head: $(git rev-parse HEAD)"
echo "Backup: $BACKUP_DIR"
echo
echo "Next: paste this complete output into ChatGPT before restarting TutorBot/VK."
