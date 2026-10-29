import unittest
from uuid import uuid4
import self_study_selftest as fixture
from learning.intensive_program import DATA,additional
from learning.language_program import lesson
from web_backend import self_study_practice as practice
from web_backend.self_study_feedback import context_for


class Tests(unittest.TestCase):
    def test_all_fifteen_modules_grade_and_hide_keys(self):
        items=[x for language in DATA for x in additional(language)]
        self.assertEqual(15,len(items));self.assertEqual(60,sum(len(x['checks']) for x in items))
        for item in items:
            public=lesson(item['id'])
            self.assertTrue(all('answers' not in q for q in public['checks']))
            result=fixture.study.submit(701,fixture.correct_body(item['id']))
            self.assertEqual(4,result['correct'])

    def test_cycle_has_clear_goal_transfer_and_realistic_budget(self):
        for language in DATA:
            for item in additional(language):
                self.assertEqual(25,sum(s['minutes'] for s in item['cycle']))
                self.assertTrue(item['objective'] and item['transfer'] and item['writing'] and item['can_do'])
                self.assertIn('Не официальный',item['source'])

    def test_repeat_does_not_create_duplicate_cards(self):
        body=fixture.correct_body('enx-01');fixture.study.submit(702,body)
        first=practice.practice(702,'en')['total']
        fixture.study.submit(702,body)
        self.assertEqual(first,practice.practice(702,'en')['total'])

    def test_alternative_correct_grammar_is_accepted(self):
        body=fixture.correct_body('enx-05');body['answers']['d0']='provided that'
        self.assertEqual(4,fixture.study.submit(703,body)['correct'])

    def test_new_modules_supply_their_own_speaking_context(self):
        for language,identifier in (('en','enx-01'),('de','dex-01'),('es','esx-01'),('fa','fax-01')):
            actual,prompt=context_for(identifier)
            self.assertEqual(language,actual);self.assertEqual(lesson(identifier)['speaking'],prompt)

    def test_missing_or_invented_module_is_rejected(self):
        for identifier in ('enx-99','dex-00','esx-missing','fax-10'):
            with self.assertRaises(ValueError):lesson(identifier)

    def test_task_bands_are_explicit_and_not_exam_certification(self):
        self.assertEqual({'B2','C1'},{x['band'] for x in additional('en')})
        self.assertEqual({'C1'},{x['band'] for x in additional('de')})
        self.assertTrue(all(x['band']=='A1' for code in ('es','fa') for x in additional(code)))


if __name__=='__main__':unittest.main()
