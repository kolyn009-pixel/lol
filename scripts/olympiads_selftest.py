"""Isolated integration tests; never import the production database module."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
tmp=tempfile.TemporaryDirectory();db=Path(tmp.name)/'test.sqlite'
def connect():
    c=sqlite3.connect(db,timeout=10);c.row_factory=sqlite3.Row;return c
sys.modules['database']=types.SimpleNamespace(connect=connect)
from web_backend import olympiad_store as st,olympiad_sources as src,olympiad_worker as worker,olympiad_journey as journey
from web_backend.olympiad_api import OlympiadMixin
spec=importlib.util.spec_from_file_location('olympiad_installer',ROOT/'scripts/install_olympiads.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)


class Tests(unittest.TestCase):
    def setUp(self):
        if db.exists():db.unlink()
        c=connect();c.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,active INTEGER); INSERT INTO users VALUES(1,'Иван',1),(2,'Мария',1); CREATE TABLE lessons(id INTEGER PRIMARY KEY,price INTEGER); INSERT INTO lessons VALUES(1,1800);");c.commit();c.close()
        self.clock=datetime(2026,11,20,6,tzinfo=timezone.utc)
        self.time=patch.object(st,'now',lambda:self.clock);self.time.start()
        src.seed();self.oid=st.identity('2026/2027',35,'PHYSICS')

    def tearDown(self):self.time.stop()

    def event(self,**kw):
        d=src._event('test','Проверка','QUALIFIER',(self.clock+timedelta(days=1)).isoformat(),(self.clock+timedelta(days=1,hours=2)).isoformat(),'TIME',format='ONLINE',source=src.MSU)
        return dict(d,**kw)

    def test_seed_idempotent_and_preserves_legacy(self):
        src.seed();c=connect()
        self.assertEqual(c.execute('SELECT COUNT(*) FROM olympiad_catalog').fetchone()[0],39)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM olympiad_events').fetchone()[0],48)
        self.assertEqual(c.execute('SELECT price FROM lessons').fetchone()[0],1800)
        c.close()

    def test_owner_and_recommendation_isolation(self):
        st.subscribe('student',1,self.oid,['WEB']);st.recommend(2,self.oid,'Подготовить механику',True)
        one=st.overview('student',1,student_id=2);two=st.overview('student',2)
        self.assertTrue(next(x for x in one['items'] if x['id']==self.oid)['channels'])
        self.assertFalse(next(x for x in one['items'] if x['id']==self.oid)['recommendation'])
        self.assertTrue(next(x for x in two['items'] if x['id']==self.oid)['recommendation']['goal'])
        self.assertNotIn('students',one)

    def test_revision_conflict_manual_and_change_dedupe(self):
        st.subscribe('student',1,self.oid,['WEB','VK'])
        d=self.event();a=st.save_event(self.oid,d)
        self.assertEqual(a['revision'],1)
        b=st.save_event(self.oid,d);self.assertFalse(b['changed'])
        with self.assertRaisesRegex(ValueError,'stage_changed'):st.save_event(self.oid,d,manual=True)
        d['expected_revision']=1;d['start_at']=(self.clock+timedelta(days=2)).isoformat();d['end_at']=None
        b=st.save_event(self.oid,d,manual=True);self.assertEqual(b['revision'],2)
        self.assertEqual(st.save_event(self.oid,self.event())['status'],'manual_preserved')
        c=connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM olympiad_notices').fetchone()[0],2);c.close()

    def test_reminders_exact_once_per_revision_and_cancel_pending(self):
        self.clock-=timedelta(days=2);st.subscribe('student',1,self.oid,['WEB','VK','TELEGRAM']);self.clock+=timedelta(days=2)
        event=st.save_event(self.oid,self.event(),notify=False)
        self.assertEqual(st.enqueue_reminders(self.clock),1)
        self.assertEqual(st.enqueue_reminders(self.clock),0)
        c=connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM olympiad_delivery_outbox').fetchone()[0],2);c.close()
        st.save_event(self.oid,self.event(status='CANCELLED'),notify=False)
        queued=worker.claim();self.assertEqual(len(queued),2)
        self.assertTrue(all(worker.deliver(x)=='SKIPPED' for x in queued))

    def test_tentative_and_stale_source_do_not_remind(self):
        self.clock-=timedelta(days=2);st.subscribe('student',1,self.oid,['WEB']);self.clock+=timedelta(days=2)
        st.save_event(self.oid,self.event(status='TENTATIVE'),notify=False)
        self.assertEqual(st.enqueue_reminders(self.clock),0)
        st.save_event(self.oid,self.event(),notify=False)
        c=connect();c.execute('UPDATE olympiad_sources SET error=? WHERE url=?',('timeout',src.MSU));c.commit();c.close()
        self.assertEqual(st.enqueue_reminders(self.clock),0)

    def test_unsubscribe_skips_pending_and_channel_retries_independent(self):
        st.subscribe('student',1,self.oid,['WEB','VK','TELEGRAM']);st.save_event(self.oid,self.event())
        result=worker.process(lambda row:'SENT' if row['channel']=='VK' else 'PENDING')
        self.assertEqual({r['channel']:r['status'] for r in result},{'TELEGRAM':'PENDING','VK':'SENT'})
        self.clock+=timedelta(minutes=3)
        result=worker.process(lambda row:'SENT');self.assertEqual(len(result),1);self.assertEqual(result[0]['channel'],'TELEGRAM')
        st.save_event(self.oid,self.event(title='Новое название'));st.subscribe('student',1,self.oid,[])
        self.assertTrue(all(worker.deliver(x)=='SKIPPED' for x in worker.claim()))

    def test_parser_failures_keep_dates(self):
        before=st.overview('student',1)['items']
        result=src.refresh(lambda url:'<html>Сайт временно недоступен</html>')
        self.assertTrue(result['registry_error'])
        self.assertTrue(all(x['error'] for x in result['sources']))
        after=st.overview('student',1)['items']
        self.assertEqual([(x['id'],len(x['events'])) for x in before],[(x['id'],len(x['events'])) for x in after])

    def test_official_adapters_current_year_and_tentative(self):
        html='<table><tr><td>Физика</td><td>с 27 ноября 2026 пятница · 12:00 до 04 декабря 2026 пятница · 12:00</td></tr><tr><td>Химия</td><td>с 30 октября 2026 пятница · 12:00 до 06 ноября 2026 пятница · 12:00</td></tr></table>'
        rows=src.parse_msu(html,'2026/2027');self.assertEqual(len(rows),2);self.assertTrue(rows[0][1]['start_at'].endswith('+03:00'))
        with self.assertRaises(ValueError):src.parse_msu(html.replace('2026','2025'),'2026/2027')
        chem='<p>Отборочный этап (дистанционный) 26 ноября — 16 декабря 2026 года</p><p>теоретический тур — 14 февраля 2027 г (проект).</p><p>практический тур — 14 марта 2027 г (проект).</p><p>Награждение победителей</p>'
        rows=src.parse_moschem(chem,'2026/2027');self.assertEqual([e['status'] for _,e in rows],['CONFIRMED','TENTATIVE','TENTATIVE'])
        spbu='<p>2026/2027 Дистанционный тур 1: 22 ноября - 28 ноября 2026 г. Дистанционный тур 2: 17-23 января 2027 г. Заключительный (очный) тур: 13 марта 2027 г.</p>'
        self.assertEqual(len(src.parse_spbu(spbu,'2026/2027')),3)

    def test_registry_rowspan_and_guard(self):
        html='<h1>Перечень 2026/27</h1><table>'
        for n in range(1,16):
            html+=f'<tr><td rowspan="2">{n}</td><td rowspan="2"><a href="https://olymp.msu.ru/">Олимпиада {n}</a></td><td>физика</td><td>физика</td><td>1</td></tr><tr><td>химия</td><td>химия</td><td>2</td></tr>'
        html+='</table>'
        self.assertEqual(len(src.parse_registry(html,'2026/2027')),30)
        with self.assertRaises(ValueError):src.parse_registry(html.replace('2026/27','2025/26'),'2026/2027')
        with self.assertRaises(ValueError):src.parse_registry(html.replace('https://olymp.msu.ru/','https://unapproved.example/'),'2026/2027')

    def test_verified_dates_and_source_change_guard(self):
        url='https://chem-olymp.mipt.ru/'
        html='<h1>Физтех по химии</h1><p>Отборочный 15 декабря 2026 — 10 января 2027</p><p>Заключительный 21 февраля 2027</p>'
        self.assertEqual(len(src.parse_verified(html,'2026/2027',url)),2)
        with self.assertRaisesRegex(ValueError,'organizer_dates_changed'):
            src.parse_verified(html.replace('21 февраля','22 февраля'),'2026/2027',url)
        with self.assertRaises(ValueError):src.parse_verified(html,'2027/2028',url)
        result=st.overview('student',1)
        self.assertEqual(sum(bool(x['events']) for x in result['items']),15)

    def test_next_season_dates_and_subscription_rollover(self):
        html='<p>Отборочный 15 декабря 2027 — 10 января 2028</p><p>Заключительный Очно 21 февраля 2028</p>'
        out=src.parse_chem_year(html,'2027/2028')
        self.assertEqual(out[0][0],'2027-2028-38-chemistry')
        self.assertEqual(out[0][1]['start_at'],'2027-12-15')
        with self.assertRaises(ValueError):src.parse_chem_year(html,'2028/2029')
        ros=src.parse_rosatom_year('<h1>2027-2028</h1><p>Физика: 6 февраля 2028</p>','2027/2028')
        self.assertEqual(ros[0][1]['start_at'],'2028-02-06')
        st.subscribe('student',1,self.oid,['WEB','VK'])
        item=dict(next(x for x in st.overview('student',1)['items'] if x['id']==self.oid))
        item.update(id='2027-2028-35-physics',season='2027/2028')
        st.upsert_catalog([item])
        self.assertEqual(st.rollover_subscriptions('2027/2028'),1)
        st.subscribe('student',1,item['id'],[])
        self.assertEqual(st.rollover_subscriptions('2027/2028'),0)
        c=connect();self.assertFalse(c.execute('SELECT 1 FROM olympiad_subscriptions WHERE olympiad_id=?',(item['id'],)).fetchone());c.close()

    def test_journey_scope_resources_and_result_verification(self):
        journey.save_progress(1,self.oid,{'steps':['prepare','registered'],'note':'Механика'})
        self.assertEqual(journey.overview(2,self.oid)['progress']['steps'],[])
        self.assertEqual(journey.overview(1,self.oid)['progress']['steps'],['prepare','registered'])
        journey.save_resource(1,self.oid,{'kind':'LINK','title':'Архив задач','url':'https://olymp.msu.ru/'})
        self.assertEqual(len(journey.overview(1,self.oid)['resources']),1)
        self.assertEqual(journey.overview(2,self.oid)['resources'],[])
        c=connect();c.execute('CREATE TABLE homework(id INTEGER PRIMARY KEY,user_id INTEGER,title TEXT,status TEXT,deadline TEXT)');c.execute("INSERT INTO homework VALUES(7,2,'Задачи','ASSIGNED',NULL)");c.commit();c.close()
        with self.assertRaisesRegex(ValueError,'homework_not_assigned'):
            journey.save_resource(1,self.oid,{'kind':'HOMEWORK','reference_id':7})
        with self.assertRaises(ValueError):journey.save_resource(1,self.oid,{'kind':'LINK','title':'X','url':'javascript:alert(1)'})
        journey.save_result(1,self.oid,{'stage':'Финал','score':90,'total':100,'award':'PRIZE','verified':True},teacher=True)
        result=journey.overview(1)['results'][0];self.assertEqual(result['verified'],1)
        self.assertEqual(journey.overview(2)['results'],[])
        journey.save_result(1,self.oid,{'stage':'Финал','score':95,'total':100,'award':'PRIZE','verified':True},teacher=False)
        self.assertEqual(journey.overview(1)['results'][0]['verified'],0)
        with self.assertRaises(ValueError):journey.save_result(1,self.oid,{'stage':'X','score':101,'total':100})

    def test_ssrf_date_and_channel_validation(self):
        for url in ['http://olymp.msu.ru/','https://127.0.0.1/','https://olymp.msu.ru.evil.test/','https://olymp.msu.ru:444/','https://u:p@olymp.msu.ru/']:
            self.assertFalse(src.safe_url(url))
        with self.assertRaisesRegex(ValueError,'official_source'):st.save_event(self.oid,self.event(source_url=src.SPBU))
        with self.assertRaises(ValueError):st.subscribe('student',1,self.oid,['EMAIL'])
        with self.assertRaisesRegex(ValueError,'timezone_required'):st.save_event(self.oid,self.event(start_at='2026-11-21T09:00:00'))

    def test_hooks_preserve_customizations_idempotent(self):
        text=(ROOT/'web_backend/learning_hub_api.py').read_text()
        hooked=installer.hook_api(text+'\n# production customization\n')
        self.assertIn('# production customization',hooked);self.assertEqual(installer.hook_api(hooked),hooked)
        html='<html><head><title>Custom</title></head><body>Extra content</body></html>'
        out=installer.hook_html(html);self.assertEqual(installer.hook_html(out),out);self.assertIn('Extra content',out)

    def test_api_unauthenticated_does_not_read_body(self):
        class H(OlympiadMixin):
            def _student(self):return None
            def _teacher(self):return None
            def _json(self,code,data):return code,data
            def _body(self):raise AssertionError('body read before auth')
        self.assertEqual(H().olympiad_post('/api/student/olympiads/subscribe')[0],401)
        self.assertEqual(H().olympiad_get('/api/teacher/olympiads',{})[0],401)

if __name__=='__main__':
    unittest.main(verbosity=2)
