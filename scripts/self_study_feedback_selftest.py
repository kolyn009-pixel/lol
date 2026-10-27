import json
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
import self_study_selftest as fixture
from web_backend import self_study_feedback as coach


class Tests(unittest.TestCase):
    def setUp(self):
        coach._recent.clear();coach._active.clear()
        self.providers=ModuleType('providers')
        self.providers.active_provider=Mock(return_value={'id':'test'})
        self.good={'strengths':['Понятная мысль.'],'corrections':['Use: I work, not I working.'],'next_try':['Объясни причину.']}
        self.providers.request_chat=Mock(return_value=json.dumps(self.good))
        package=ModuleType('ai_assistant');package.providers=self.providers
        p=patch.dict(sys.modules,{'ai_assistant':package});p.start();self.addCleanup(p.stop)
        self.body={'lesson_id':'en-01','transcript':'I working online.','consent':True}

    def test_returns_validated_feedback(self):
        result=coach.feedback(101,self.body)
        self.assertEqual(self.good['strengths'],result['strengths'])
        self.assertEqual(25,self.providers.request_chat.call_args.kwargs['timeout'])
        self.assertNotIn("101",str(self.providers.request_chat.call_args))

    def test_consent_and_length_checked_before_provider(self):
        for extra in ({'consent':False},{'transcript':''},{'transcript':'x'*3001}):
            with self.assertRaises(ValueError):coach.feedback(101,{**self.body,**extra})
        self.providers.request_chat.assert_not_called()

    def test_no_provider_clear_error(self):
        self.providers.active_provider.return_value=None
        with self.assertRaisesRegex(RuntimeError,'ai_not_configured'):coach.feedback(101,self.body)

    def test_provider_errors_do_not_leak_secrets(self):
        self.providers.request_chat.side_effect=RuntimeError('Authorization secret example')
        with self.assertRaisesRegex(RuntimeError,'^ai_unavailable$'):coach.feedback(101,self.body)
        self.assertEqual(set(),coach._active)

    def test_malformed_output_not_shown_as_feedback(self):
        for raw in ('not json','[]','{}',json.dumps({**self.good,'corrections':'bad'})):
            self.providers.request_chat.return_value=raw
            with self.assertRaisesRegex(RuntimeError,'ai_invalid_response'):coach.feedback(101,self.body)

    def test_rate_limits_are_per_owner(self):
        for _ in range(6):coach.feedback(101,self.body)
        with self.assertRaisesRegex(RuntimeError,'feedback_rate_limited'):coach.feedback(101,self.body)
        coach.feedback(202,self.body)

    def test_series_context_only_from_catalogue(self):
        coach.feedback(101,{**self.body,'lesson_id':'series:landman'})
        coach.feedback(101,{**self.body,'lesson_id':'series:schwarzes-gold'})
        with self.assertRaises(ValueError):coach.feedback(101,{**self.body,'lesson_id':'series:invented'})

    def test_auth_and_origin_before_provider(self):
        path=fixture.API_ROOT+'/speech/feedback'
        for handler,expected in ((fixture.FakeHandler(teacher=None,body=self.body),401),(fixture.FakeHandler(body=self.body,origin=False),403)):
            self.assertEqual(expected,handler.self_study_route(path,write=True)[0])
        self.providers.request_chat.assert_not_called()


if __name__=='__main__':unittest.main()
