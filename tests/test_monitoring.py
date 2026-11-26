"""Automatic monitoring uses disposable page/video fixtures and explicit clock ticks."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from threading import Event
import time
import unittest
from unittest.mock import patch

import httpx
from hi10_downloader import schema, storage
from hi10_downloader.monitoring import identity
from hi10_downloader.parsing import parse_project
from hi10_downloader.web import Application, Cancelled, ident
import test_runtime
from test_web import PAGE, URL, wait


class MonitoringTests(unittest.TestCase):
    setUp = test_runtime.RuntimeTests.setUp
    tearDown = test_runtime.RuntimeTests.tearDown

    def ready(self):
        self.app.connected=True;self.app.session_status='connected'
        self.app.last_verified=time.time()

    def enable(self, ids=None):
        self.ready()
        self.app.action('/api/monitoring/projects',{'ids':ids or [self.p['id']],'enabled':True})

    def check(self, page=PAGE, succeeds=True):
        def client(_):return httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=page)))
        with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',client),patch.object(self.app.cancel,'wait',return_value=False):
            self.assertTrue(self.app.monitoring.tick());wait(self.app)
        if succeeds:self.assertIsNone(self.app.job['error'])

    def test_monitoring_opt_in_manual_queue_does_not_autostart(self):
        self.ready();self.app.queue([self.p['id']])
        with patch.object(self.app,'start_job') as start:
            self.assertFalse(self.app.monitoring.tick())
            start.assert_not_called()
        self.assertEqual(self.app.monitoring.public()['count'],0)

    def test_existing_missing_files_queue_at_selected_quality_and_start_only_owned_ids(self):
        other=deepcopy(self.p);other.update(id='manual-project',folder='Manual folder')
        self.app.catalog['projects'].append(other)
        self.app.queue([other['id']]);manual=deepcopy(self.app.items)
        self.app.action('/api/project/settings',{'id':self.p['id'],'quality':720})
        self.enable();self.check()
        owned=self.app.items[2:]
        self.assertEqual(len(owned),2)
        self.assertEqual([e['file']['resolution'] for e in owned],[720,1080])
        self.assertTrue(all(e['monitor_auto'] and not e['monitor_attempted'] for e in owned))
        self.assertEqual(self.app.items[:2],manual)
        with patch.object(self.app,'start_downloads') as start:
            self.assertTrue(self.app.monitoring.tick())
            start.assert_called_once_with({e['id'] for e in owned},source='monitor')

    def test_later_new_episode_only_and_restart_keeps_ledger(self):
        self.enable();self.check()
        first_keys={identity(e['file']) for e in self.app.items}
        self.app.items=[];self.app.save_queue()
        restored=Application(self.app.config,self.app.output,password='test-password')
        restored.connected=True;restored.session_status='connected';self.app=restored
        self.app.action('/api/monitoring/check',{})
        self.check(PAGE.replace('</div>', '<a href="https://other.test/03_1080p.mkv">New</a></div>'))
        self.assertEqual([e['filename'] for e in self.app.items],['03_1080p.mkv'])
        record=self.app.monitoring.state['projects'][self.p['id']]
        self.assertEqual(len(record['seen']),3)
        self.assertTrue(first_keys.issubset(record['seen']))
        # An already handled episode is not a quality-upgrade/redownload request.
        self.app.items=[];self.app.save_queue()
        self.app.action('/api/project/settings',{'id':self.p['id'],'quality':720})
        self.app.action('/api/monitoring/check',{})
        self.check()
        self.assertEqual(self.app.items,[])

    def test_manifest_complete_files_are_not_added(self):
        self.enable()
        with patch.object(self.app,'is_complete',return_value=True):self.check()
        self.assertEqual(self.app.items,[])
        self.assertEqual(len(self.app.monitoring.state['projects'][self.p['id']]['seen']),2)

    def test_existing_failed_manual_entry_is_preserved_even_with_other_quality(self):
        self.app.action('/api/project/settings',{'id':self.p['id'],'quality':720})
        self.app.queue([self.p['id']])
        self.app.items[0].update(status='failed',bytes=99,message='HTTP 404')
        before=deepcopy(self.app.items)
        self.app.action('/api/project/settings',{'id':self.p['id'],'quality':1080})
        self.enable();self.check()
        self.assertEqual(self.app.items,before)
        with patch.object(self.app,'start_downloads') as start:
            self.assertFalse(self.app.monitoring.tick());start.assert_not_called()

    def test_check_can_append_while_manual_download_runs_without_mutating_targets(self):
        self.app.queue([self.p['id']]);before=deepcopy(self.app.items)
        entered,release=Event(),Event()
        def running(targets):
            entered.set();release.wait(3)
            self.assertEqual(targets,before)
        try:
            with patch.object(self.app,'verify'),patch.object(self.app,'run_downloads',side_effect=running):
                self.app.start_downloads();self.assertTrue(entered.wait(1))
                self.enable()
                def client(_):return httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,text=PAGE.replace('</div>', '<a href="https://mirror.test/03_1080p.mkv">New</a></div>'))))
                with patch('hi10_downloader.web.make_client',client),patch.object(self.app.cancel,'wait',return_value=False):
                    self.assertTrue(self.app.monitoring.tick())
                    deadline=time.monotonic()+3
                    while self.app.job['running'] and time.monotonic()<deadline:time.sleep(.01)
                self.assertFalse(self.app.job['running']);self.assertTrue(self.app.download_job['running'])
                self.assertEqual(self.app.items[:2],before)
                self.assertEqual(len(self.app.items),3)
                release.set();wait(self.app)
        finally:release.set()

    def test_interval_and_explicit_schedule_are_respected(self):
        self.enable();self.check()
        target=time.time()+3600
        self.app.set_schedule(datetime.fromtimestamp(target,timezone.utc).isoformat())
        with patch.object(self.app,'start_downloads') as start:
            self.assertFalse(self.app.monitoring.tick())
            start.assert_not_called()
        self.assertAlmostEqual(self.app.schedule['starts_at'],target,places=5)
        self.app.items=[];self.app.save_queue()
        with patch.object(self.app,'start_job') as start:
            due=self.app.monitoring.state['projects'][self.p['id']]['next_check']
            self.assertFalse(self.app.monitoring.tick(now=due-1))
            self.assertTrue(self.app.monitoring.tick(now=due+1))
            self.assertEqual(start.call_args.args[0],'monitor')

    def test_pause_and_unmonitor_prevent_automatic_starts_and_persist(self):
        self.enable();self.check()
        self.app.action('/api/monitoring/settings',{'paused':True,'interval_minutes':30})
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertTrue(restored.monitoring.state['paused'])
        with patch.object(self.app,'start_downloads') as start:
            self.assertFalse(self.app.monitoring.tick());start.assert_not_called()
        self.app.action('/api/monitoring/settings',{'paused':False,'interval_minutes':30})
        self.app.action('/api/monitoring/projects',{'ids':[self.p['id']],'enabled':False})
        with patch.object(self.app,'start_downloads') as start:
            self.assertFalse(self.app.monitoring.tick());start.assert_not_called()
        self.assertEqual(len(self.app.items),2)

    def test_failed_attempts_are_not_automatically_retried(self):
        self.enable();self.check()
        with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',return_value=httpx.Client()),patch('hi10_downloader.web.download_one',side_effect=ValueError('fixture failure')):
            self.assertTrue(self.app.monitoring.tick());wait(self.app)
        self.assertEqual([e['status'] for e in self.app.items],['failed','failed'])
        self.assertTrue(all(e['monitor_attempted'] for e in self.app.items))
        with patch.object(self.app,'start_downloads') as start:
            self.assertFalse(self.app.monitoring.tick());start.assert_not_called()
        with patch.object(self.app,'start_downloads') as start:
            self.app.action('/api/downloads/retry',{'id':self.app.items[0]['id']})
            start.assert_called_once_with({self.app.items[0]['id']})

    def test_stop_batch_pauses_monitor_but_not_manual_work(self):
        self.enable();self.check()
        entered=Event()
        def running(targets):
            entered.set();self.app.download_cancel.wait(3);raise Cancelled()
        with patch.object(self.app,'verify'),patch.object(self.app,'run_downloads',side_effect=running):
            self.app.monitoring.tick();self.assertTrue(entered.wait(1))
            self.app.action('/api/stop',{'target':'download'});wait(self.app)
        self.assertTrue(self.app.monitoring.state['paused'])
        self.app.action('/api/monitoring/settings',{'paused':False,'interval_minutes':60})
        self.app.start_job('download',lambda:self.app.download_cancel.wait(3))
        self.app.action('/api/monitoring/settings',{'paused':True,'interval_minutes':60})
        self.assertFalse(self.app.download_cancel.is_set())
        self.app.download_cancel.set();wait(self.app)

    def test_missing_or_expired_session_blocks_and_network_failure_backs_off(self):
        self.enable();self.app.connected=False;self.app.session_status='expired'
        with patch.object(self.app,'start_job') as start:
            self.assertFalse(self.app.monitoring.tick());start.assert_not_called()
        self.ready()
        with patch.object(self.app,'scan_projects',side_effect=ValueError('fixture offline')):
            self.assertTrue(self.app.monitoring.tick());wait(self.app)
        record=self.app.monitoring.state['projects'][self.p['id']]
        self.assertGreater(record['next_check'],time.time())
        self.assertIsNotNone(record['last_error'])
        with patch.object(self.app,'start_job') as start:
            self.assertFalse(self.app.monitoring.tick());start.assert_not_called()

    def test_excluded_projects_not_monitored_scanned_or_started(self):
        self.enable();self.app.catalog['excluded_ids']=[self.p['id']]
        with patch.object(self.app,'start_job') as start:
            self.assertFalse(self.app.monitoring.tick());start.assert_not_called()
        self.assertEqual(self.app.monitoring.public()['active_count'],0)
        with self.assertRaisesRegex(ValueError,'excluded'):
            self.app.action('/api/monitoring/projects',{'ids':[self.p['id']],'enabled':True})

    def test_queue_limit_does_not_mark_files_handled(self):
        self.enable()
        with patch.dict(os.environ,{'HI10_MAX_QUEUE_ITEMS':'1'}):self.check()
        self.assertEqual(self.app.items,[])
        record=self.app.monitoring.state['projects'][self.p['id']]
        self.assertEqual(record['seen'],[])
        self.assertIn('queue',record['last_error'])

    def test_storage_failure_shuts_down_and_recovers_queue_and_ledger_together(self):
        self.enable()
        original=storage.recover_transaction
        with patch('hi10_downloader.storage.recover_transaction',side_effect=OSError('fixture disk full')):
            self.check(succeeds=False)
        self.assertTrue(self.app.shutdown.is_set())
        self.assertTrue((self.app.config/'pending-transaction.json').exists())
        original(self.app.config,self.app.output)
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertEqual(len(restored.items),2)
        self.assertEqual(len(restored.monitoring.state['projects'][self.p['id']]['seen']),2)

    def test_snapshot_hides_ledger_and_emits_project_delta(self):
        first=self.app.snapshot();self.enable()
        delta=self.app.snapshot(first['library_version'])
        self.assertIsNone(delta['projects'])
        self.assertTrue(delta['project_updates'][0]['monitored'])
        self.assertEqual(delta['monitoring']['count'],1)
        self.check()
        for value in self.app.monitoring.state['projects'][self.p['id']]['seen']:
            self.assertNotIn(value,json.dumps(self.app.snapshot()))

    def test_settings_validation_and_corrupt_state_recovery(self):
        for body in ({'paused':False,'interval_minutes':0},{'paused':0,'interval_minutes':60},{'paused':False,'interval_minutes':True}):
            with self.assertRaises(ValueError):self.app.action('/api/monitoring/settings',body)
        self.enable();self.app.action('/api/monitoring/settings',{'paused':True,'interval_minutes':30})
        path=self.app.monitoring.path;path.write_text('{broken')
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertEqual(len(restored.monitoring.state['projects']),1)
        self.assertTrue(path.with_name(path.name+'.corrupt').exists())
        bad=deepcopy(restored.monitoring.state);bad['projects'][self.p['id']]['next_check']=float('nan')
        self.assertFalse(schema.monitoring(bad))

    def test_scheduler_scans_and_downloads_without_browser_or_manual_start(self):
        self.enable();self.app.save_catalog()
        requested=[]
        def respond(request):
            url=str(request.url);requested.append(url)
            if 'all-projects' in url:return httpx.Response(200,text='<div id="urlContainer"></div>')
            if url==URL:return httpx.Response(200,text=PAGE)
            return httpx.Response(200,content=b'\x1a\x45\xdf\xa3monitor-fixture')
        def client(_):return httpx.Client(transport=httpx.MockTransport(respond))
        with patch('hi10_downloader.web.make_client',client),patch.object(self.app.cancel,'wait',return_value=False):
            self.app.start_services()
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    with self.app.lock:
                        if len(self.app.items)==2 and all(e['status']=='complete' for e in self.app.items):break
                    time.sleep(.01)
                self.assertEqual([e['status'] for e in self.app.items],['complete','complete'])
                self.assertEqual(self.app.download_job['source'],'monitor')
                self.assertEqual(self.app.snapshot()['projects'][0]['remaining'],0)
                self.assertEqual(len(list(self.app.output.glob('*/*.mkv'))),2)
                self.assertIn('https://mirror.test/01_1080p.mkv',requested)
                self.assertNotIn('https://mirror.test/01_720p.mkv',requested)
            finally:self.app.close(timeout=2)

    def test_section_choices_limit_automatic_downloads(self):
        from test_collections import HTML
        p=parse_project(HTML,URL);p.update(id=self.p['id'],scanned=True,choices={})
        self.app.catalog['projects']=[p];self.p=p
        section=p['sections'][1]['id']
        self.app.action('/api/project/settings',{'id':p['id'],'sections':[section],'section_qualities':{section:480}})
        self.enable();self.check(HTML)
        self.assertEqual(len(self.app.items),2)
        self.assertTrue(all(e['file']['section_id']==section and e['file']['resolution']==480 for e in self.app.items))

    def test_monitor_batch_is_bounded_and_blocked_by_session_operations(self):
        ids=[]
        for i in range(7):
            p=deepcopy(self.p);p['id']=f'monitored-{i}';ids.append(p['id'])
            self.app.catalog['projects'].append(p)
        self.enable(ids)
        self.app.job.update(kind='session',running=True)
        self.assertFalse(self.app.monitoring.tick())
        self.app.job['running']=False
        with patch.object(self.app,'start_job') as start:
            self.assertTrue(self.app.monitoring.tick())
            self.assertEqual(start.call_args.args[0],'monitor')
        due=[r for r in self.app.monitoring.state['projects'].values() if r['next_check']>0]
        self.assertEqual(len(due),5)

    def test_start_failure_after_successful_verification_does_not_spin(self):
        self.enable();self.check()
        def verified():self.app.monitoring.retry_after=0
        with patch.object(self.app,'verify',side_effect=verified),patch('hi10_downloader.web.make_client',side_effect=ValueError('fixture client failed')):
            self.assertTrue(self.app.monitoring.tick());wait(self.app)
        self.assertGreater(self.app.monitoring.retry_after,time.time())
        self.assertFalse(self.app.monitoring.tick())
        self.assertFalse(any(e['monitor_attempted'] for e in self.app.items))

    def test_unmonitor_during_batch_skips_remaining_files(self):
        self.enable();self.check()
        seen=[]
        def downloaded(client,item,referer,target,progress=None):
            seen.append(item['filename']);target.write_bytes(b'\x1a\x45\xdf\xa3fixture')
            self.app.action('/api/monitoring/projects',{'ids':[self.p['id']],'enabled':False})
            from hi10_downloader.cli import digest
            return {'url':item['url'],'size':target.stat().st_size,'sha256':digest(target)}
        with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',return_value=httpx.Client()),patch('hi10_downloader.web.download_one',side_effect=downloaded):
            self.assertTrue(self.app.monitoring.tick());wait(self.app)
        self.assertEqual(len(seen),1)
        self.assertEqual([e['status'] for e in self.app.items],['complete','queued'])
        self.assertFalse(self.app.monitoring.tick())
