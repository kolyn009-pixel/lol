"""Exercise the actual mobile installer's merge and rollback logic."""
import importlib.util
from pathlib import Path
import unittest

if __name__=='__main__':
 path=Path(__file__).with_name('deploy_merge_selftest.py')
 spec=importlib.util.spec_from_file_location('merge_tests',path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 module.SCRIPT=Path(__file__).with_name('deploy_study_experience_20261015.sh').read_text(encoding='utf-8')
 module.MERGE=module.SCRIPT.split('python3 - "$REPO" "$BASE" "$TARGET" "$NEW" "$BACKUP" <<\'PY\'\n',1)[1].split('\nPY\n',1)[0]
 result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(module))
 raise SystemExit(0 if result.wasSuccessful() else 1)
