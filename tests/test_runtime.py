from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import httpx

from hi10_downloader.cli import save_json
from hi10_downloader.parsing import parse_project
from hi10_downloader.web import Application, Cancelled, ident
from test_web import PAGE, URL, wait


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.app=Application(self.root/'config',self.root/'downloads',password='test-password')
        p=parse_project(PAGE,URL);p.update(id=ident(URL),scanned=True,choices={})
        self.app.catalog['projects']=[p]
        save_json(self.app.state_path,{'cookies':[]})
        self.p=p

    def tearDown(self):
        self.app.shutdown.set();self.app.scheduler_wake.set()
        wait(self.app)
        self.temp.cleanup()

    def test_add_queue_is_deferred_deduplicated_and_persistent(self):
        with patch.object(self.app,'start_job') as start:
            first=self.app.queue([self.p['id']])
            second=self.app.queue([self.p['id']])
        start.assert_not_called()
        self.assertEqual((first['added'],second['added']),(2,0))
        self.assertFalse(self.app.job['running'])
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertEqual(restored.pending_count(),2)
        self.assertEqual([e['status'] for e in restored.items],['queued','queued'])
        self.assertFalse(restored.start_due())

    def test_schedule_persists_and_only_runs_when_due(self):
        self.app.queue([self.p['id']])
        target=time.time()+3600
        self.app.set_schedule(datetime.fromtimestamp(target,timezone.utc).isoformat())
        restored=Application(self.app.config,self.app.output,password='test-password')
        with patch.object(restored,'start_job') as start:
            self.assertFalse(restored.start_due(now=target-1))
            start.assert_not_called()
            self.assertTrue(restored.start_due(now=target+1))
            self.assertEqual(start.call_args.args[0],'download')
        self.assertIsNone(restored.schedule['starts_at'])
        self.assertIsNone(json.loads(restored.schedule_path.read_text())['starts_at'])

    def test_schedule_waits_for_active_job_and_can_be_cancelled(self):
        self.app.queue([self.p['id']]);target=time.time()+3600
        self.app.set_schedule(datetime.fromtimestamp(target,timezone.utc).isoformat())
        self.app.job['running']=True
        self.assertFalse(self.app.start_due(now=target+1))
        self.app.job['running']=False
        self.app.action('/api/downloads/unschedule',{})
        self.assertIsNone(self.app.schedule['starts_at'])
        self.assertEqual(self.app.pending_count(),2)
        for value in ('bad','2020-01-01T00:00:00','2020-01-01T00:00:00+00:00'):
            with self.assertRaises(ValueError):self.app.set_schedule(value)

    def test_stop_keeps_remaining_files_in_pending_queue(self):
        self.app.queue([self.p['id']])
        with patch.object(self.app,'verify',return_value=None),patch('hi10_downloader.web.download_one',side_effect=Cancelled),patch('hi10_downloader.web.make_client',return_value=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200)))):
            self.app.start_downloads();wait(self.app)
        self.assertEqual([e['status'] for e in self.app.items],['interrupted','queued'])
        self.assertEqual(self.app.pending_count(),2)

    def test_access_cookie_survives_restart_expires_and_rejects_password_change(self):
        value=self.app.access_cookie()
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertTrue(restored.valid_access_cookie(value))
        self.assertFalse(restored.valid_access_cookie(value+'tampered'))
        changed=Application(self.app.config,self.app.output,password='different-password')
        self.assertFalse(changed.valid_access_cookie(value))
        with patch('hi10_downloader.runtime.time.time',return_value=time.time()+31*86400):
            self.assertFalse(restored.valid_access_cookie(value))

    def test_verified_hi10_session_restores_without_reimport(self):
        client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text='<div id="urlContainer"></div>')))
        with patch('hi10_downloader.web.make_client',return_value=client):self.app.verify(force=True)
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertTrue(restored.connected)
        self.assertEqual(restored.session_status,'connected')
        with patch('hi10_downloader.web.make_client') as make:
            restored.verify()
            make.assert_not_called()

    def test_temporary_network_error_retains_saved_session(self):
        self.app.connected=True
        def unavailable(request):raise httpx.ConnectError('offline')
        with patch('hi10_downloader.web.make_client',return_value=httpx.Client(transport=httpx.MockTransport(unavailable))):
            with self.assertRaisesRegex(ValueError,'retained'):self.app.verify(force=True)
        self.assertTrue(self.app.state_path.exists())
        self.assertTrue(self.app.connected)
        self.assertEqual(self.app.session_status,'error')

    def test_startup_automatically_verifies_saved_session(self):
        with patch.object(self.app,'verify') as verify:
            self.app.start_services();wait(self.app)
            verify.assert_called_once_with(force=True)
        self.assertFalse(self.app._restoring)

    def test_repeated_polls_use_cached_summaries_and_no_file_work(self):
        with patch.object(self.app,'selected',wraps=self.app.selected) as selected,patch.object(self.app,'is_complete',wraps=self.app.is_complete) as complete:
            initial=self.app.snapshot()
            selected_calls=selected.call_count;file_checks=complete.call_count
            for _ in range(20):
                result=self.app.snapshot(initial['library_version'])
                self.assertIsNone(result['projects'])
            self.assertEqual(selected.call_count,selected_calls)
            self.assertEqual(complete.call_count,file_checks)
            self.assertEqual(selected_calls,1)

    def test_project_update_sends_only_changed_summary(self):
        first=self.app.snapshot()
        self.app.action('/api/project/settings',{'id':self.p['id'],'quality':720})
        result=self.app.snapshot(first['library_version'])
        self.assertIsNone(result['projects'])
        self.assertEqual([p['id'] for p in result['project_updates']],[self.p['id']])
        self.assertEqual(result['project_updates'][0]['preferred'],720)

    def test_old_catalog_migrates_to_bounded_detail_cache(self):
        projects=[]
        for i in range(12):
            url=f'https://hi10anime.com/{i}'
            p=parse_project(PAGE,url);p.update(id=ident(url),scanned=True,choices={})
            projects.append(p)
        self.app.catalog['projects']=projects
        save_json(self.app.catalog_path,self.app.catalog)
        restored=Application(self.app.config,self.app.output,password='test-password')
        restored.warm_library()
        index=json.loads(restored.catalog_path.read_text())
        self.assertTrue(all('variants' not in p for p in index['projects']))
        self.assertEqual(len(list(restored.project_dir.glob('*.json'))),12)
        self.assertLessEqual(len(restored._details),8)
        self.assertTrue((restored.config/'library-legacy-backup.json').exists())
        again=Application(restored.config,restored.output,password='test-password')
        self.assertEqual(len(again._details),0)
        self.assertEqual(again.snapshot()['projects'][0]['count'],2)
        self.assertEqual(len(again._details),0,'cached summaries should not load project details')

    def test_scan_writes_project_details_and_one_small_index(self):
        def client(_):return httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=PAGE)))
        import hi10_downloader.runtime as runtime
        with patch.object(self.app,'verify',return_value=None),patch('hi10_downloader.web.make_client',client),patch.object(self.app.cancel,'wait',return_value=False),patch('hi10_downloader.runtime.save_json',wraps=runtime.save_json) as save:
            self.app.scan_projects({self.p['id']})
        paths=[call.args[0] for call in save.call_args_list]
        self.assertEqual(paths.count(self.app.catalog_path),1)
        self.assertIn(self.app.project_dir/(self.p['id']+'.json'),paths)
        self.assertNotIn('variants',json.loads(self.app.catalog_path.read_text())['projects'][0])

    def test_queue_status_response_is_paged_and_redacted(self):
        self.app.items=[{'id':str(i),'status':'queued','filename':f'{i}.mkv','file':{'url':'https://private.test/token'}} for i in range(125)]
        state=self.app.snapshot(download_page=1)
        self.assertEqual(len(state['downloads']),50)
        self.assertEqual(state['downloads'][0]['filename'],'50.mkv')
        self.assertEqual(state['download_total'],125)
        self.assertNotIn('private.test',json.dumps(state))
