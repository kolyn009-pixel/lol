import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from deploy_group_workspace_20261022 import delta,html_assets


class Deployment(unittest.TestCase):
    def test_preserves_independent_fix_and_idempotency(self):
        old='import existing\n\ndef handler():\n    return 1\n\ndef unrelated():\n    return 7\n'
        new=old.replace('return 1','return 2')
        live=old.replace('return 7','return 8')
        result=delta(live,old,new,'sample')
        self.assertIn('return 8',result);self.assertIn('return 2',result)
        self.assertEqual(delta(result,old,new,'sample'),result)

    def test_refuses_unknown_overlap(self):
        with self.assertRaises(RuntimeError):delta('unknown','old','new','sample')

    def test_preserves_brand_boot_and_existing_scripts(self):
        html='<html><head><link rel="icon" href="new.png"><script>boot()</script></head><body><script src="/app/teacher_groups.js?v=old"></script></body></html>'
        result=html_assets(html,['teacher_group_settings.js','teacher_groups.js'])
        self.assertIn('new.png',result);self.assertIn('boot()',result)
        self.assertEqual(result.count('teacher_groups.js'),1)
        self.assertEqual(html_assets(result,['teacher_group_settings.js','teacher_groups.js']),result)

    def test_onboarding_alias_does_not_load_registration_twice(self):
        html='<head></head><body><script src="/onboarding/onboarding.js?v=old"></script></body>'
        result=html_assets(html,['onboarding/onboarding.js'])
        self.assertEqual(result.count('<script'),1)
        self.assertIn('/app/onboarding/onboarding.js?v=20261022-group-design1',result)


if __name__=='__main__':unittest.main()
