"""Transfer settings, shared bandwidth, bounded parallel work, and cancellation."""
from copy import deepcopy
import json
from pathlib import Path
from threading import Event, Lock
import time
import unittest
from unittest.mock import patch

import httpx
from hi10_downloader.transfers import BandwidthBudget
from hi10_downloader.cli import digest, download_one
from hi10_downloader.web import Application, Cancelled
from hi10_downloader.parsing import parse_project
import test_runtime
from test_web import PAGE, URL, wait

class BudgetTests(unittest.TestCase):
    def test_budget_uses_decimal_kilobits_and_shared_reservations_without_idle_credit(self):
        class Clock:
            now=0
            def is_set(self):return False
            def wait(self,delay):self.now+=delay;return False
        clock=Clock();budget=BandwidthBudget(8,clock,Cancelled,clock=lambda:clock.now)
        budget.consume(1000);self.assertAlmostEqual(clock.now,1)
        budget.consume(500);self.assertAlmostEqual(clock.now,1.5)
        clock.now+=50
        budget.consume(1000);self.assertAlmostEqual(clock.now,52.5)
    def test_low_limit_chunk_sizes_keep_all_workers_reporting_within_a_quarter_second(self):
        for speed in (1,8,64,100,8000):
            for workers in (1,2,8):
                budget=BandwidthBudget(speed,Event(),Cancelled,parallel_downloads=workers)
                self.assertGreater(budget.chunk_size,0)
                self.assertLessEqual(budget.chunk_size,65536)
                self.assertLessEqual(budget.chunk_size*workers/budget.bytes_per_second,.25)

    def test_unlimited_does_not_wait_and_stop_interrupts_wait(self):
        event=Event()
        budget=BandwidthBudget(0,event,Cancelled)
        with patch.object(event,'wait') as wait_event:budget.consume(100000);wait_event.assert_not_called()
        event.set()
        with self.assertRaises(Cancelled):budget.consume(1)
        event.clear();budget=BandwidthBudget(1,event,Cancelled)
        with patch.object(event,'wait',return_value=True),self.assertRaises(Cancelled):budget.consume(65536)

class TransferTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown
    def settings(self,speed=0,parallel=2):
        self.app.action('/api/downloads/settings',{'speed_limit_kbps':speed,'parallel_downloads':parallel})
    def expand_queue(self):
        html='<h1>Test project</h1><div class="entry-content">'+''.join(f'<a href="https://mirror.test/{i:02}_1080p.mkv">Video</a>' for i in range(6))+'</div>'
        p=parse_project(html,URL);p.update(id=self.p['id'],scanned=True,choices={})
        self.app.catalog['projects']=[p];self.p=p
        self.app.queue([p['id']])
    def clients(self,_):return httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200)))
    def test_settings_default_validate_and_survive_restart(self):
        self.assertEqual(self.app.transfer_settings,{'version':1,'speed_limit_kbps':0,'parallel_downloads':1})
        for data in ({'speed_limit_kbps':-1,'parallel_downloads':2},{'speed_limit_kbps':10,'parallel_downloads':9},{'speed_limit_kbps':True,'parallel_downloads':1},{'speed_limit_kbps':1.5,'parallel_downloads':1},{'speed_limit_kbps':0,'parallel_downloads':0}):
            with self.assertRaises(ValueError):self.app.action('/api/downloads/settings',data)
        self.settings(8000,3)
        restored=Application(self.app.config,self.app.output,password='test')
        self.assertEqual(restored.snapshot()['transfer_settings']['speed_limit_kbps'],8000)
        self.assertEqual(restored.transfer_settings['parallel_downloads'],3)
        self.assertFalse(restored.download_job['running'])
    def test_parallelism_is_bounded_and_all_manifest_records_survive(self):
        self.settings(parallel=2);self.expand_queue()
        mutex=Lock();entered=Event();release=Event();active=peak=0
        def download(client,item,referer,target,progress=None):
            nonlocal active,peak
            with mutex:
                active+=1;peak=max(peak,active)
                if active==2:entered.set()
            release.wait(3)
            progress(4,4);target.write_bytes(b'\x1a\x45\xdf\xa3')
            with mutex:active-=1
            return {'url':item['url'],'size':4,'sha256':digest(target)}
        try:
            with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',self.clients),patch('hi10_downloader.web.download_one',side_effect=download):
                self.app.start_downloads()
                self.assertTrue(entered.wait(2),'two files must start before either completes')
                self.settings(parallel=1)  # Active batch retains its original limit.
                release.set();wait(self.app)
            self.assertEqual(peak,2)
            self.assertEqual(self.app.download_job['done'],6)
            self.assertEqual(self.app.download_job['total'],6)
            self.assertTrue(all(e['status']=='complete' for e in self.app.items))
            self.assertEqual(len(json.loads((self.app.output/'hi10-manifest.json').read_text())),6)
            self.assertEqual(self.app.transfer_settings['parallel_downloads'],1)
        finally:release.set()
    def test_stop_interrupts_active_parallel_files_and_leaves_pending_files(self):
        self.settings(parallel=2);self.expand_queue()
        entered=Event();mutex=Lock();count=0
        def download(client,item,referer,target,progress=None):
            nonlocal count
            with mutex:
                count+=1
                if count==2:entered.set()
            self.app.download_cancel.wait(3);progress(1,100)
        with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',self.clients),patch('hi10_downloader.web.download_one',side_effect=download):
            self.app.start_downloads();self.assertTrue(entered.wait(2))
            self.app.action('/api/stop',{'target':'download'});wait(self.app)
        self.assertEqual(count,2)
        self.assertEqual(sum(e['status']=='interrupted' for e in self.app.items),2)
        self.assertEqual(sum(e['status']=='queued' for e in self.app.items),4)
        self.assertFalse(any(t.is_alive() and t.name.startswith('hi10-transfer') for t in __import__('threading').enumerate()))
    def test_parallel_failures_do_not_stop_other_files(self):
        self.settings(parallel=2);self.app.queue([self.p['id']])
        def respond(request):return httpx.Response(404) if '01_' in str(request.url) else httpx.Response(200,content=b'\x1a\x45\xdf\xa3fixture')
        def client(_):return httpx.Client(transport=httpx.MockTransport(respond))
        with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',client):
            self.app.start_downloads();wait(self.app)
        self.assertEqual([e['status'] for e in self.app.items],['failed','complete'])
        self.assertEqual(self.app.download_job['done'],2)
    def test_shared_budget_is_used_for_every_limited_transfer(self):
        self.settings(8000,2);self.app.queue([self.p['id']]);calls=[]
        def download(client,item,referer,target,progress=None,throttle=None,chunk_size=None):
            calls.append(throttle);throttle(4);target.write_bytes(b'\x1a\x45\xdf\xa3');return {'url':item['url'],'size':4,'sha256':digest(target)}
        with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',self.clients),patch('hi10_downloader.web.download_one',side_effect=download):
            self.app.start_downloads();wait(self.app)
        self.assertEqual(len(calls),2)
        self.assertIs(calls[0].__self__,calls[1].__self__)
    def test_worker_failure_is_not_hidden_by_another_workers_cancellation(self):
        self.settings(parallel=2);self.app.queue([self.p['id']])
        release=Event();mutex=Lock();count=0
        def transfer(*args,**kwargs):
            nonlocal count
            with mutex:count+=1;first=count==1
            if first:
                release.wait(3)
                raise Cancelled()
            release.set()
            raise ValueError('Worker setup failed')
        try:
            with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',self.clients),patch.object(self.app,'_run_download_targets',side_effect=transfer):
                self.app.start_downloads();wait(self.app)
            self.assertEqual(self.app.download_job['error'],'Worker setup failed')
            self.assertFalse(self.app.download_job['running'])
        finally:release.set()

    def test_throttle_counts_bytes_and_cancel_cleans_part(self):
        target=self.app.output/'fixture.mkv';payload=b'\x1a\x45\xdf\xa3'+b'x'*130000;chunks=[]
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=payload))) as client:
            record=download_one(client,{'url':'https://mirror.test/file.mkv'},URL,target,throttle=chunks.append)
        self.assertEqual(sum(chunks),len(payload));self.assertLessEqual(max(chunks),65536)
        target.unlink()
        def cancelled(_):raise Cancelled()
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=payload))) as client,self.assertRaises(Cancelled):
            download_one(client,{'url':'https://mirror.test/file.mkv'},URL,target,throttle=cancelled)
        self.assertFalse(target.exists());self.assertFalse(target.with_name(target.name+'.part').exists())

    def test_speed_counts_progress_across_workers_and_retries_not_queue_totals(self):
        from hi10_downloader.transfers import TransferRate
        self.settings(parallel=2);self.app.queue([self.p['id']])
        now=[0.0];self.app.transfer_rate=TransferRate(clock=lambda:now[0])
        self.app.items[0]['bytes']=99999999  # Historical totals must not affect rate.
        def downloaded(client,item,referer,target,progress=None):
            with self.app.lock:
                now[0]=2
            progress(0,100);progress(100,100)
            progress(0,50);progress(50,50)  # A retry resets cumulative progress.
            target.write_bytes(b'\x1a\x45\xdf\xa3')
            return {'url':item['url'],'size':4,'sha256':digest(target)}
        self.app.download_job['running']=True
        try:
            with patch('hi10_downloader.web.make_client',self.clients),patch('hi10_downloader.web.download_one',side_effect=downloaded):
                self.app.run_downloads()
            self.assertEqual(self.app.snapshot(download_filter='complete')['download_job']['speed_bytes_per_second'],150)
            self.assertEqual(self.app.snapshot(download_filter='failed')['download_job']['speed_bytes_per_second'],150)
            self.app.download_job['running']=False
            self.assertEqual(self.app.snapshot()['download_job']['speed_bytes_per_second'],0)
        finally:self.app.download_job['running']=False



class TransferRateTests(unittest.TestCase):
    def test_rolling_rate_expires_when_stalled_and_resets_between_batches(self):
        from hi10_downloader.transfers import TransferRate
        now=[0.0];rate=TransferRate(clock=lambda:now[0])
        self.assertEqual(rate.speed(),0)
        now[0]=1;rate.add(1000)
        self.assertEqual(rate.speed(),1000)
        now[0]=2;rate.add(2000)
        self.assertEqual(rate.speed(),1500)
        now[0]=7;self.assertEqual(rate.speed(),0)
        rate.add(1000);self.assertEqual(rate.speed(),200)
        rate.reset();self.assertEqual(rate.speed(),0)
    def test_high_frequency_parallel_samples_stay_bounded(self):
        from hi10_downloader.transfers import TransferRate
        now=[0.0];rate=TransferRate(clock=lambda:now[0])
        for i in range(10000):
            now[0]=i/1000;rate.add(1);rate.add(2)
        self.assertLessEqual(len(rate.samples),21)
        self.assertGreater(rate.speed(),0)
        now[0]+=6;self.assertEqual(rate.speed(),0)


class StreamingSpeedTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown

    def test_rate_updates_before_one_megabyte_has_arrived(self):
        ready,release=Event(),Event()
        class SlowStream(httpx.SyncByteStream):
            def __iter__(self):
                yield b'\x1a\x45\xdf\xa3'+b'x'*(16384-4)
                yield b'x'*16384
                ready.set()
                release.wait(3)
                yield b'x'*16384
        self.app.queue([self.p['id']]);self.app.items=self.app.items[:1];self.app.save_queue()
        def client(_):return httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=SlowStream())))
        try:
            with patch.object(self.app,'verify'),patch('hi10_downloader.web.make_client',client):
                self.app.start_downloads()
                self.assertTrue(ready.wait(2))
                from hi10_downloader.server import application
                with httpx.Client(transport=httpx.WSGITransport(app=application(self.app)),base_url='http://local.test') as api_client:
                    self.assertEqual(api_client.post('/api/unlock',json={'password':'test-password'}).status_code,200)
                    snapshot=api_client.get('/api/state').json()
                self.assertTrue(snapshot['download_job']['running'])
                self.assertGreater(snapshot['download_job']['speed_bytes_per_second'],0)
                self.assertEqual(snapshot['downloads'][0]['bytes'],32768)
                release.set();wait(self.app)
        finally:release.set();wait(self.app)
