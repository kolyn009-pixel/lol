"""Verify safe contextual migration and idempotency using reviewed fixtures."""
from pathlib import Path
import importlib.util,json,unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer',ROOT/'scripts/install_reschedule_calendar.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Test(unittest.TestCase):
    def test_reviewed_hunks(self):
        delta=json.loads((ROOT/'scripts/reschedule_calendar_delta.json').read_text())
        for name,hunks in delta.items():
            after=(ROOT/name).read_text()
            before=after
            for h in reversed(hunks):
                self.assertEqual(before.count(h['new']),1,name)
                before=before.replace(h['new'],h['old'],1)
            with self.subTest(name=name):
                self.assertEqual(m.patch_text(before,hunks,name),after)
                self.assertEqual(m.patch_text(after,hunks,name),after)
                extra='\n# Unrelated local customization stays here.\n'
                self.assertEqual(m.patch_text(before+extra,hunks,name),after+extra)
    def test_conflict_refused(self):
        with self.assertRaisesRegex(RuntimeError,'no files changed'):
            m.patch_text('def x():\n    return 3\n',[{'old':'def x():\n    return 1\n','new':'def x():\n    return 2\n'}],'test')
if __name__=='__main__':unittest.main()
