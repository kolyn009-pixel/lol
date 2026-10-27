import unittest
import self_study_selftest as fixture
from learning.entry_diagnostic import questions
from learning.beginner_languages import units
from web_backend import self_study_entry as entry
from web_backend.self_study_api import ROOT


class Student(fixture.FakeHandler):
    def _student(self):return {'id':101,'role':'student'} if self.teacher else None
    def _teacher(self):return None


class Tests(unittest.TestCase):
    def setUp(self):
        fixture.study.ensure_schema();entry.ensure_schema();conn=fixture.connect()
        for table in ('personal_study_profiles','personal_study_attempts','personal_study_entry','personal_study_drafts'):
            conn.execute('DELETE FROM '+table)
        conn.commit();conn.close()

    def test_student_profile_and_teacher_profile_do_not_mix(self):
        status,data=Student().self_study_route(ROOT.replace('/teacher/','/student/'))
        self.assertEqual(200,status);self.assertEqual(-101,data['owner_id']);self.assertTrue(all('checks' not in x for items in data['courses'].values() for x in items))
        self.assertEqual({'en','es'},set(data['profile']['languages']))
        self.assertEqual({'en','de','fa'},set(fixture.study.profile(101)['languages']))
        self.assertEqual('2027-05-01',data['profile']['languages']['en']['target_date'])

    def test_english_target_and_budget_survive_settings_save(self):
        p=fixture.study.save_profile(-101,{'daily_minutes':180})
        self.assertEqual(180,sum(x['minutes'] for x in p['languages'].values()))
        self.assertEqual('2027-05-01',p['languages']['en']['target_date'])

    def test_question_bank_does_not_reveal_answers(self):
        bank=entry.get(-101)['questions'];self.assertEqual(23,len(bank))
        self.assertTrue(all('answer' not in q for q in bank))

    def test_unknown_results_in_foundation_route(self):
        result=entry.submit(-101,{'answers':{q['id']:'unknown' for q in questions()}})
        self.assertEqual('A1',result['working_band'])
        self.assertEqual('en0-01',fixture.study.overview(-101)['courses']['en'][0]['id'])

    def test_high_result_selects_b2_route_without_foundation(self):
        result=entry.submit(-101,{'answers':{q['id']:q['answer'] for q in questions(True)}})
        self.assertEqual('B2',result['working_band'])
        overview=fixture.study.overview(-101)
        self.assertEqual('en-01',overview['courses']['en'][0]['id'])
        self.assertFalse(overview['profile']['diagnostic_required'])
        self.assertIsNone(entry.result(101))

    def test_incomplete_or_invalid_answer_does_not_change_route(self):
        for answers in ({},{q['id']:'invented' for q in questions()}):
            with self.assertRaises(ValueError):entry.submit(-101,{'answers':answers})
        self.assertIsNone(entry.result(-101))

    def test_beginner_modules_grade_for_student(self):
        for code in ('en','es'):
            for item in units(code):
                body=fixture.correct_body(item['id'])
                result=fixture.study.submit(-101,body)
                self.assertEqual(4,result['correct'])
        self.assertEqual([],fixture.study.overview(101)['history'])

    def test_student_cannot_use_teacher_route_or_change_identity(self):
        self.assertEqual(401,Student().self_study_route(ROOT)[0])
        path=(ROOT+'/entry/submit').replace('/teacher/','/student/')
        body={'answers':{q['id']:'unknown' for q in questions()},'owner_id':101}
        self.assertEqual(200,Student(body=body).self_study_route(path,write=True)[0])
        self.assertIsNone(entry.result(101));self.assertIsNotNone(entry.result(-101))

    def test_student_endpoint_requires_session_and_same_origin(self):
        path=(ROOT+'/entry/submit').replace('/teacher/','/student/')
        self.assertEqual(401,Student(teacher=None,body={}).self_study_route(path,write=True)[0])
        self.assertEqual(403,Student(body={},origin=False).self_study_route(path,write=True)[0])


if __name__=='__main__':unittest.main()
