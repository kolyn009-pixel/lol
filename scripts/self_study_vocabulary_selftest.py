import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import self_study_selftest as fixture
from web_backend import self_study_vocabulary as vocab,self_study_practice as practice


class Tests(unittest.TestCase):
    def setUp(self):
        self.owner=int(uuid4().hex[:7],16)+10000
        self.now=datetime(2026,10,27,12,tzinfo=timezone.utc)
        self.timer=patch.object(vocab,'clock',return_value=self.now);self.timer.start();self.addCleanup(self.timer.stop)
        self.review_timer=patch.object(practice,'clock',return_value=self.now);self.review_timer.start();self.addCleanup(self.review_timer.stop)

    def goal(self,target=30,deadline='2026-11-10'):
        return vocab.save_goal(self.owner,{'language':'en','target':target,'deadline':deadline})

    def test_status_does_not_add_words(self):
        d=vocab.status(self.owner,'en');self.assertEqual(0,d['in_deck']);self.assertFalse(d['claimed']);self.assertGreater(d['available'],0)

    def test_goal_and_budget_set_portion(self):
        slow=self.goal(10,'2026-11-10');fast=self.goal(30,'2026-10-30')
        self.assertGreater(fast['proposed'],slow['proposed']);self.assertLessEqual(fast['proposed'],fast['capacity_per_day'])

    def test_grant_is_idempotent_and_owned(self):
        self.goal();a=vocab.start(self.owner,{'language':'en'});b=vocab.start(self.owner,{'language':'en'})
        self.assertEqual(a['cards'],b['cards']);self.assertEqual(a['added_today'],b['added_today']);self.assertTrue(a['claimed'])
        self.assertGreater(a['added_today'],0);self.assertTrue(all(c['front'] and c['back'] for c in a['cards']))
        self.assertEqual(0,vocab.status(self.owner+1,'en')['in_deck'])

    def test_concurrent_clicks_cannot_double_daily_grant(self):
        self.goal()
        with ThreadPoolExecutor(4) as pool:r=list(pool.map(lambda _:vocab.start(self.owner,{'language':'en'}),range(4)))
        self.assertEqual(1,len({tuple(c['id'] for c in d['cards']) for d in r}))

    def test_new_day_adds_different_cards_without_missed_day_debt(self):
        self.goal();a=vocab.start(self.owner,{'language':'en'})
        with patch.object(vocab,'clock',return_value=self.now+timedelta(days=3)):
            b=vocab.start(self.owner,{'language':'en'})
        self.assertFalse({c['id'] for c in a['cards']}&{c['id'] for c in b['cards']})
        self.assertLessEqual(b['added_today'],b['capacity_per_day'])

    def test_existing_lesson_phrases_are_not_granted_again(self):
        fixture.study.submit(self.owner,fixture.correct_body('en-01'));a=vocab.status(self.owner,'en')
        b=vocab.start(self.owner,{'language':'en'});self.assertEqual(a['in_deck']+b['added_today'],b['in_deck'])
        from learning.language_program import lesson
        self.assertFalse({c['front'] for c in b['cards']}&{p['front'] for p in lesson('en-01')['phrases']})

    def test_granted_vocabulary_is_not_duplicated_when_lesson_is_checked(self):
        self.goal();d=vocab.start(self.owner,{'language':'en'});first=d['cards'][0]['front']
        fixture.study.submit(self.owner,fixture.correct_body('en-01'));practice.practice(self.owner,'en')
        conn=fixture.connect()
        try:self.assertEqual(1,conn.execute("SELECT COUNT(*) FROM personal_study_cards WHERE owner_id=? AND answer=? AND source!='error'",(self.owner,first)).fetchone()[0])
        finally:conn.close()

    def test_large_review_queue_pauses_new_words(self):
        for n in range(1,13):fixture.study.submit(self.owner,fixture.correct_body(f'en-{n:02}'))
        d=self.goal(100,'2026-10-29');self.assertEqual(0,d['proposed']);self.assertIn('разгрузим',d['reason'])
        self.assertFalse(vocab.start(self.owner,{'language':'en'})['claimed'])

    def test_many_recent_errors_reduce_portion(self):
        self.goal(30,'2026-10-28');vocab.ensure_schema();conn=fixture.connect()
        try:
            cid=conn.execute("INSERT INTO personal_study_cards(owner_id,language,lesson_id,source,source_key,prompt,answer,due_at) VALUES(?,'en','test','phrase','test','a','b','2030-01-01')",(self.owner,)).lastrowid
            for i in range(5):conn.execute("INSERT INTO personal_study_reviews(owner_id,request_id,card_id,card_version,answer,correct,created_at,rating) VALUES(?,?,?,0,'?',0,?,'again')",(self.owner,str(uuid4()),cid,self.now.isoformat()))
            conn.commit()
        finally:conn.close()
        self.assertEqual(1,vocab.status(self.owner,'en')['proposed'])

    def test_past_or_unrealistic_goal_reports_limit(self):
        d=self.goal(1000,'2026-10-26');self.assertTrue(d['pace_exceeds_budget']);self.assertTrue(d['bank_shortfall'])
        self.assertLessEqual(d['proposed'],10)

    def test_goal_reached_stops_new_additions(self):
        self.goal(1);d=vocab.start(self.owner,{'language':'en'});self.assertEqual(1,d['in_deck'])
        with patch.object(vocab,'clock',return_value=self.now+timedelta(days=1)):
            self.assertEqual(0,vocab.status(self.owner,'en')['proposed'])

    def test_changing_goal_does_not_allow_second_portion_today(self):
        self.goal(1);a=vocab.start(self.owner,{'language':'en'});self.goal(100)
        b=vocab.start(self.owner,{'language':'en'});self.assertEqual(a['cards'],b['cards'])

    def test_invalid_goal_and_language_rejected(self):
        for n in (True,0,1001,'50'):
            with self.assertRaisesRegex(ValueError,'invalid_word_goal'):self.goal(n)
        with self.assertRaisesRegex(ValueError,'invalid_word_goal'):self.goal(deadline='tomorrow')
        with self.assertRaisesRegex(ValueError,'invalid_language'):vocab.status(self.owner,'invented')

    def test_new_cards_enter_existing_spaced_review_queue(self):
        self.goal();d=vocab.start(self.owner,{'language':'en'});q=practice.practice(self.owner,'en')
        self.assertTrue({c['id'] for c in d['cards']}<={c['id'] for c in q['items']})
        self.assertTrue(all('answer' not in c for c in q['items']))
        card=q['items'][0];r=practice.answer_card(self.owner,{'card_id':card['id'],'version':card['version'],'answer':'?', 'request_id':str(uuid4())})
        practice.rate_card(self.owner,{'review_id':r['review_id'],'rating':'again'})
        self.assertFalse(r['correct']);self.assertTrue(vocab.status(self.owner,'en')['in_deck'])


if __name__=='__main__':unittest.main()
