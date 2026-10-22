#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'Run inside SSH as root.'; exit 1; }
target=${1:?A pinned commit is required}
[[ $target =~ ^[0-9a-f]{40}$ ]] || { echo 'Expected a full commit SHA.'; exit 1; }
media=e1bcfcaf3c1fab94c69839f70bb7ca7cfca873bf
work=$(mktemp -d /root/adelia-media-receipts-XXXXXX)
trap 'rm -rf "$work"' EXIT

# Native OCR stays on this server; receipt files are not sent to an AI service.
if ! python3 - <<'PY'
import shutil,subprocess,sys
if not all(shutil.which(x) for x in ('tesseract','pdftotext','pdftoppm')):sys.exit(1)
r=subprocess.run(['tesseract','--list-langs'],capture_output=True,text=True,timeout=10)
sys.exit(0 if r.returncode==0 and 'rus' in r.stdout.splitlines() and 'eng' in r.stdout.splitlines() else 1)
PY
then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus poppler-utils
fi

git -C /opt/tutorbot show "$media:scripts/fix_landing_brand_runtime_20261022.py" > "$work/brand.py"
python3 "$work/brand.py" "$media"
git -C /opt/tutorbot show "$media:scripts/deploy_group_media_20261022.py" > "$work/groups.py"
if python3 - "$media" <<'PY'
import subprocess,sys
from pathlib import Path
root=Path('/opt/adelia-current').resolve()
files=['web_backend/group_visuals.py','web_backend/group_media_api.py','web/avatar_editor.js','web/avatar_editor.css',
       'web/teacher_group_chat.js','web/teacher_group_settings.js','web/teacher_group_settings.css']
for p in files:
 expected=subprocess.check_output(['git','-C','/opt/tutorbot','show',sys.argv[1]+':'+p])
 if not (root/p).is_file() or (root/p).read_bytes()!=expected:sys.exit(1)
if 'GroupMediaMixin' not in (root/'web_backend/api_v7.py').read_text():sys.exit(1)
for html in ['web/teacher.html','web/index.html']:
 if 'avatar_editor.js' not in (root/html).read_text():sys.exit(1)
PY
then
  echo 'GROUP_MEDIA_ALREADY_INSTALLED'
else
  python3 "$work/groups.py" "$media"
fi
receipts=e4a1d07993253aaa7ae0a05b6009b2adf20c7867
if python3 - "$receipts" <<'PYR'
import subprocess,sys
from pathlib import Path
root=Path('/opt/adelia-current').resolve()
for p in ['web_backend/receipt_review_tools.py','web_backend/receipt_tools_api.py','web/teacher_receipt_review_tools.js','web/teacher_receipt_review_tools.css']:
 expected=subprocess.check_output(['git','-C','/opt/tutorbot','show',sys.argv[1]+':'+p])
 if not (root/p).is_file() or (root/p).read_bytes()!=expected:sys.exit(1)
if 'ReceiptToolsMixin' not in (root/'web_backend/api_v7.py').read_text():sys.exit(1)
if 'teacher_receipt_review_tools.js' not in (root/'web/teacher.html').read_text():sys.exit(1)
PYR
then
  echo 'RECEIPT_TOOLS_ALREADY_INSTALLED'
else
  git -C /opt/tutorbot show "$receipts:scripts/deploy_receipt_tools_20261022.py" > "$work/receipts.py"
  python3 "$work/receipts.py" "$receipts"
fi
git -C /opt/tutorbot show "$target:scripts/deploy_day_off_20261022.py" > "$work/dayoff.py"
python3 "$work/dayoff.py" "$target"
echo 'ADELIA_FULL_UPDATE_OK'
