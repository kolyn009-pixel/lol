"""Stage-2 scheduling, independent check and privacy regressions on SQLite."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import self_study_selftest as fixture
from learning.language_checkpoints import FORMS, checkpoint
from web_backend import self_study_practice as practice

study=fixture.study


class PracticeTests(unittest.TestCase):
    def setUp(self):
        study.ensure_schema();practice.ensure_schema()
        conn=fixture.connect()
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'personal_study_%'")]
        for name in tables:conn.execute('DELETE FROM '+name)
        conn.commit();conn.close()
        self.time=datetime(2026,11,1,12,tzinfo=timezone.utc)
        self.clock=patch.object(practice,'clock',lambda:self.time);self.clock.start();self.addCleanup(self.clock.stop)

    def seed(self,wrong=False):
        body=fixture.correct_body()
        if wrong:body['answers']['d0']='wrong'
        study.submit(101,body)
        return practice.practice(101,'en')

    def answer(self,card,answer=None,owner=101):
        if answer is None:
            conn=fixture.connect();answer=conn.execute('SELECT answer FROM personal_study_cards WHERE id=?',(card['id'],)).fetchone()[0];conn.close()
        return practice.answer_card(owner,{'card_id':card['id'],'version':card['version'],'answer':answer,'request_id':str(uuid4())})

    def complete_check(self,item,owner=101,wrong=False):
        answers={q['id']:('wrong' if wrong else q['answers'][0]) for q in checkpoint(item['id'],True)['checks']}
        body={'attempt_id':item['attempt_id'],'answers':answers}
        return practice.save_checkpoint(owner,body,True),body

    def test_existing_lessons_backfill_without_duplicate_cards(self):
        data=self.seed()
        self.assertEqual(3,data['due']);self.assertEqual(3,data['total'])
        self.assertEqual(3,practice.practice(101,'en')['total'])
        self.assertTrue(all('answer' not in card and 'expected' not in card for card in data['items']))
        self.assertEqual(0,practice.practice(202,'en')['total'])

    def test_error_sync_is_idempotent_and_prioritises_errors(self):
        data=self.seed(True)
        self.assertEqual(4,data['due']);self.assertEqual('error',data['items'][0]['source'])
        for _ in range(3):self.assertEqual(1,practice.practice(101,'en')['errors'][0]['wrong_count'])

    def test_review_reveal_is_restored_after_reload(self):
        card=self.seed()['items'][0];reveal=self.answer(card)
        data=practice.practice(101,'en')
        self.assertEqual(reveal,data['items'][0]['pending'])

    def test_reveal_retry_is_idempotent(self):
        card=self.seed()['items'][0]
        body={'card_id':card['id'],'version':card['version'],'answer':'struggle to','request_id':str(uuid4())}
        self.assertEqual(practice.answer_card(101,body),practice.answer_card(101,body))
        body['answer']='changed'
        with self.assertRaisesRegex(ValueError,'request_conflict'):practice.answer_card(101,body)

    def test_correct_review_moves_one_day_then_expands(self):
        card=self.seed()['items'][0];reveal=self.answer(card)
        result=practice.rate_card(101,{'review_id':reveal['review_id'],'rating':'good'})
        self.assertEqual(1,result['interval_days']);self.assertEqual(2,practice.practice(101,'en')['due'])
        self.time+=timedelta(days=1,seconds=1)
        card=next(c for c in practice.practice(101,'en')['items'] if c['id']==card['id'])
        result=practice.rate_card(101,{'review_id':self.answer(card)['review_id'],'rating':'good'})
        self.assertEqual(2,result['interval_days'])

    def test_wrong_answer_cannot_be_graded_as_success(self):
        card=self.seed()['items'][0];reveal=self.answer(card,'wrong')
        self.assertFalse(reveal['correct'])
        result=practice.rate_card(101,{'review_id':reveal['review_id'],'rating':'good'})
        self.assertEqual('again',result['rating'])
        self.assertEqual(self.time+timedelta(minutes=10),datetime.fromisoformat(result['due_at']))

    def test_rating_retry_does_not_double_schedule(self):
        reveal=self.answer(self.seed()['items'][0]);body={'review_id':reveal['review_id'],'rating':'hard'}
        result=practice.rate_card(101,body);self.time+=timedelta(hours=1)
        self.assertEqual(result,practice.rate_card(101,body))
        with self.assertRaisesRegex(ValueError,'request_conflict'):
            practice.rate_card(101,{**body,'rating':'good'})

    def test_two_tabs_cannot_schedule_same_card_twice(self):
        card=self.seed()['items'][0];a=self.answer(card);b=self.answer(card)
        practice.rate_card(101,{'review_id':a['review_id'],'rating':'good'})
        with self.assertRaisesRegex(ValueError,'stale_review'):
            practice.rate_card(101,{'review_id':b['review_id'],'rating':'good'})

    def test_concurrent_ratings_are_idempotent(self):
        reveal=self.answer(self.seed()['items'][0]);body={'review_id':reveal['review_id'],'rating':'good'}
        with ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:practice.rate_card(101,body),range(3)))
        self.assertTrue(all(r==results[0] for r in results))

    def test_unrevealed_or_foreign_review_cannot_be_rated(self):
        card=self.seed()['items'][0]
        with self.assertRaisesRegex(ValueError,'card_not_found'):self.answer(card,'answer',owner=202)
        reveal=self.answer(card)
        with self.assertRaisesRegex(ValueError,'review_not_found'):
            practice.rate_card(202,{'review_id':reveal['review_id'],'rating':'good'})
        with self.assertRaisesRegex(ValueError,'review_not_found'):
            practice.rate_card(101,{'review_id':999999,'rating':'good'})

    def test_scheduled_card_cannot_be_recalled_early(self):
        card=self.seed()['items'][0]
        practice.rate_card(101,{'review_id':self.answer(card)['review_id'],'rating':'good'})
        with self.assertRaisesRegex(ValueError,'card_not_due'):self.answer({**card,'version':card['version']+1})

    def test_error_needs_success_on_separate_days(self):
        card=self.seed(True)['items'][0]
        practice.rate_card(101,{'review_id':self.answer(card)['review_id'],'rating':'good'})
        self.assertEqual('PRACTICING',practice.practice(101,'en')['errors'][0]['status'])
        self.time+=timedelta(days=1,seconds=1)
        card=next(c for c in practice.practice(101,'en')['items'] if c['id']==card['id'])
        practice.rate_card(101,{'review_id':self.answer(card)['review_id'],'rating':'good'})
        self.assertEqual('RESOLVED',practice.practice(101,'en')['errors'][0]['status'])

    def test_familiar_lesson_pass_does_not_erase_error_journal(self):
        self.seed(True);study.submit(101,fixture.correct_body())
        self.assertEqual('OPEN',practice.practice(101,'en')['errors'][0]['status'])

    def test_new_mistake_invalidates_an_outstanding_review(self):
        card=self.seed(True)['items'][0];reveal=self.answer(card)
        self.seed(True)
        with self.assertRaisesRegex(ValueError,'stale_review'):
            practice.rate_card(101,{'review_id':reveal['review_id'],'rating':'good'})

    def test_invalid_input_cannot_mutate_review_queue(self):
        card=self.seed()['items'][0]
        base={'card_id':card['id'],'version':card['version'],'answer':'x','request_id':str(uuid4())}
        for update in ({'card_id':True},{'version':True},{'answer':[]},{'answer':''},{'request_id':None}):
            with self.assertRaises(ValueError):practice.answer_card(101,{**base,**update})
        self.assertTrue(all(x['pending'] is None for x in practice.practice(101,'en')['items']))

    def test_all_nine_control_forms_grade_and_hide_keys(self):
        self.assertEqual(9,len(FORMS));self.assertEqual(54,sum(len(f['checks']) for f in FORMS))
        for language in ('en','de','fa'):
            for _ in range(3):
                item=practice.start_checkpoint(101,{'language':language})
                self.assertTrue(item['fresh'])
                self.assertTrue(all('answers' not in q for q in item['checks']))
                result,_=self.complete_check(item)
                self.assertEqual((6,6),(result['correct'],result['total']))
                self.assertEqual({'comprehension':{'correct':3,'total':3},'recall':{'correct':3,'total':3}},result['skills'])
                self.time+=timedelta(days=28,seconds=1)
            self.assertEqual(0,practice.checkpoint_status(101,language)['new_forms_remaining'])

    def test_start_is_idempotent_and_resumes_draft(self):
        item=practice.start_checkpoint(101,{'language':'en'})
        self.assertEqual(item,practice.start_checkpoint(101,{'language':'en'}))
        practice.save_checkpoint(101,{'attempt_id':item['attempt_id'],'answers':{'r0':'used to'}})
        resumed=practice.start_checkpoint(101,{'language':'en'})
        self.assertEqual({'r0':'used to'},resumed['answers'])

    def test_new_form_has_28_day_spacing_but_familiar_practice_allowed(self):
        item=practice.start_checkpoint(101,{'language':'en'});self.complete_check(item)
        with self.assertRaisesRegex(ValueError,'checkpoint_not_due'):
            practice.start_checkpoint(101,{'language':'en'})
        repeated=practice.start_checkpoint(101,{'language':'en','practice_form':item['id']})
        self.assertFalse(repeated['fresh']);self.complete_check(repeated)
        state=practice.checkpoint_status(101,'en')
        self.assertEqual([True,False],[x['fresh'] for x in state['results']])
        self.time+=timedelta(days=28)
        next_item=practice.start_checkpoint(101,{'language':'en'})
        self.assertNotEqual(item['id'],next_item['id'])

    def test_completed_check_cannot_be_overwritten_and_retry_is_safe(self):
        item=practice.start_checkpoint(101,{'language':'de'});result,body=self.complete_check(item)
        self.assertEqual(result,practice.save_checkpoint(101,body,True))
        body['answers']['r0']='wrong'
        with self.assertRaisesRegex(ValueError,'checkpoint_finished'):practice.save_checkpoint(101,body,True)

    def test_unfinished_check_cannot_be_counted_as_progress(self):
        practice.start_checkpoint(101,{'language':'en'})
        self.assertEqual([],practice.checkpoint_status(101,'en')['results'])

    def test_checkpoint_identity_and_validation(self):
        item=practice.start_checkpoint(101,{'language':'fa'})
        with self.assertRaisesRegex(ValueError,'checkpoint_not_found'):practice.get_checkpoint(202,item['attempt_id'])
        with self.assertRaisesRegex(ValueError,'checkpoint_not_found'):self.complete_check(item,owner=202)
        with self.assertRaises(ValueError):practice.start_checkpoint(101,{'language':'xx'})
        with self.assertRaises(ValueError):practice.save_checkpoint(101,{'attempt_id':item['attempt_id'],'answers':{}},True)
        self.assertEqual([],practice.checkpoint_status(101,'fa')['results'])

    def test_practice_cannot_expose_an_unseen_variant(self):
        with self.assertRaisesRegex(ValueError,'checkpoint_not_found'):
            practice.start_checkpoint(101,{'language':'en','practice_form':'en-C'})

    def test_stage2_routes_authenticate_and_enforce_origin(self):
        from web_backend.self_study_api import ROOT,POST_PATHS
        for path in POST_PATHS:
            handler=fixture.FakeHandler(teacher=None,body={})
            self.assertEqual(401,handler.self_study_route(path,write=True)[0]);self.assertFalse(handler.body_read)
            handler=fixture.FakeHandler(body={},origin=False)
            self.assertEqual(403,handler.self_study_route(path,write=True)[0]);self.assertFalse(handler.body_read)
        handler=fixture.FakeHandler(body={'language':'en','owner_id':202})
        status,item=handler.self_study_route(ROOT+'/checkpoint/start',write=True)
        self.assertEqual(200,status)
        self.assertEqual(None,practice.checkpoint_status(202,'en')['active_id'])
        self.assertEqual(item['attempt_id'],practice.checkpoint_status(101,'en')['active_id'])


if __name__=='__main__':unittest.main()
