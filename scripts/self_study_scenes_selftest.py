import unittest
from uuid import uuid4
from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import self_study_selftest as fixture
from web_backend import self_study_scenes as scenes
from web_backend import self_study_practice as practice
from web_backend.self_study_feedback import context_for


class Tests(unittest.TestCase):
    def setUp(self):
        scenes.ensure_schema();fixture.study.ensure_schema();conn=fixture.connect()
        for name in ('scenes','cards','reviews','attempts','practice_sync'):conn.execute('DELETE FROM personal_study_'+name)
        conn.commit();conn.close()
        self.data={'resource_id':'landman','season':1,'episode':1,'start_seconds':30,'end_seconds':180,
                   'summary':'Конфликт интересов.','comprehension':'gist','phrases':[{'expression':'at stake','meaning':'на кону'}],
                   'request_id':str(uuid4())}

    def test_save_and_private_read(self):
        record=scenes.save_scene(101,self.data)['scene']
        self.assertEqual('en',record['language']);self.assertEqual([],scenes.list_scenes(202,'en')['items'])
        self.assertEqual(record,scenes.get_scene(101,record['id']))
        with self.assertRaisesRegex(ValueError,'scene_not_found'):scenes.get_scene(202,record['id'])

    def test_retry_does_not_duplicate_scene_or_cards(self):
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:scenes.save_scene(101,self.data),range(3)))
        self.assertTrue(all(x==results[0] for x in results))
        self.assertEqual(1,len(scenes.list_scenes(101,'en')['items']))
        self.assertEqual(1,practice.practice(101,'en')['total'])

    def test_request_conflict(self):
        scenes.save_scene(101,self.data)
        with self.assertRaisesRegex(ValueError,'request_conflict'):scenes.save_scene(101,{**self.data,'summary':'changed'})

    def test_cards_due_tomorrow_and_recall_works(self):
        current=practice.clock()
        with patch.object(practice,'clock',lambda:current):scenes.save_scene(101,self.data)
        self.assertEqual(0,practice.practice(101,'en')['due'])
        with patch.object(practice,'clock',lambda:current+timedelta(days=1,seconds=1)):
            card=practice.practice(101,'en')['items'][0]
            result=practice.answer_card(101,{'card_id':card['id'],'version':card['version'],'answer':'at stake','request_id':str(uuid4())})
            self.assertTrue(result['correct']);self.assertIn('тобой',result['explanation'])

    def test_bad_time_and_invalid_fields(self):
        for extra in ({'season':True},{'episode':0},{'start_seconds':-1},{'end_seconds':20},
                      {'end_seconds':1000},{'resource_id':'invented'},{'summary':[]},{'comprehension':'C1'},
                      {'request_id':None},{'phrases':[{'expression':'x','meaning':''}]}):
            with self.assertRaises(ValueError):scenes.save_scene(101,{**self.data,**extra})
        self.assertEqual([],scenes.list_scenes(101,'en')['items'])

    def test_maximum_three_phrases_and_duplicates(self):
        for phrases in ([{'expression':str(i),'meaning':'m'} for i in range(4)],self.data['phrases']*2):
            with self.assertRaises(ValueError):scenes.save_scene(101,{**self.data,'phrases':phrases})

    def test_scene_without_phrases_and_german_language(self):
        scenes.save_scene(101,{**self.data,'resource_id':'schwarzes-gold','phrases':[]})
        self.assertEqual(1,len(scenes.list_scenes(101,'de')['items']))
        self.assertEqual(0,practice.practice(101,'de')['total'])

    def test_feedback_context_is_scoped_to_owner(self):
        item=scenes.save_scene(101,self.data)['scene']
        language,prompt=context_for('scene:'+str(item['id']),101)
        self.assertEqual('en',language);self.assertIn(self.data['summary'],prompt)
        with self.assertRaises(ValueError):context_for('scene:'+str(item['id']),202)

    def test_scene_reports_do_not_change_test_scores(self):
        scenes.save_scene(101,self.data)
        overview=fixture.study.overview(101)
        self.assertEqual([],overview['history']);self.assertEqual(0,overview['profile']['languages']['en']['completed'])

    def test_route_auth_and_payload_identity(self):
        path=fixture.API_ROOT+'/scenes/save'
        self.assertEqual(401,fixture.FakeHandler(teacher=None,body=self.data).self_study_route(path,write=True)[0])
        self.assertEqual(403,fixture.FakeHandler(body=self.data,origin=False).self_study_route(path,write=True)[0])
        status,_=fixture.FakeHandler(body={**self.data,'owner_id':202}).self_study_route(path,write=True)
        self.assertEqual(200,status);self.assertEqual([],scenes.list_scenes(202,'en')['items'])


if __name__=='__main__':unittest.main()
