from threading import Event
import time
from unittest.mock import patch

import httpx

import unittest
import test_runtime
from test_web import PAGE, wait
from hi10_downloader.web import Cancelled


class ConcurrentJobTests(unittest.TestCase):
    """Exercise the public scan/start/stop actions with overlapping workers."""

    setUp = test_runtime.RuntimeTests.setUp
    tearDown = test_runtime.RuntimeTests.tearDown

    def test_scan_during_download_preserves_batch_and_separate_progress(self):
        self.app.queue([self.p['id']])
        entered, release = Event(), Event()
        filenames = [entry['filename'] for entry in self.app.items]

        def downloading(targets):
            self.app.download_job.update(message='Downloading episode', total=2, done=1)
            entered.set()
            release.wait(3)
            self.assertEqual([entry['filename'] for entry in targets], filenames)

        def client(_):
            return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=PAGE)))

        try:
            with patch.object(self.app, 'verify'), patch.object(self.app, 'run_downloads', side_effect=downloading), patch('hi10_downloader.web.make_client', client), patch.object(self.app.cancel, 'wait', return_value=False):
                self.app.action('/api/downloads/start', {})
                self.assertTrue(entered.wait(1))
                self.app.action('/api/scan', {'ids': [self.p['id']]})
                deadline = time.monotonic() + 2
                while self.app.job['running'] and time.monotonic() < deadline:
                    time.sleep(.01)
                state = self.app.snapshot()
                self.assertFalse(state['job']['running'])
                self.assertIsNone(state['job']['error'])
                self.assertEqual(state['job']['done'], 1)
                self.assertTrue(state['download_job']['running'])
                self.assertEqual(state['download_job']['done'], 1)
                self.assertEqual(state['download_job']['message'], 'Downloading episode')
                self.assertEqual(len(self.app.items), 2)
                release.set()
                wait(self.app)
        finally:
            release.set()

    def test_stopping_scan_leaves_download_running_and_duplicate_jobs_rejected(self):
        scan_entered, download_entered, release_download = Event(), Event(), Event()

        def scan():
            scan_entered.set()
            self.app.cancel.wait(3)
            raise Cancelled()

        def download():
            download_entered.set()
            release_download.wait(3)

        try:
            self.app.start_job('download', download)
            self.assertTrue(download_entered.wait(1))
            self.app.start_job('scan', scan)
            self.assertTrue(scan_entered.wait(1))
            with self.assertRaises(ValueError):
                self.app.start_job('scan', lambda: None)
            with self.assertRaises(ValueError):
                self.app.start_job('download', lambda: None)
            with self.assertRaises(ValueError):
                self.app.action('/api/session/delete', {})
            self.app.action('/api/stop', {'target': 'scan'})
            self.assertTrue(self.app.cancel.is_set())
            self.assertFalse(self.app.download_cancel.is_set())
            self.assertTrue(self.app.download_job['running'])
        finally:
            self.app.cancel.set()
            release_download.set()
            wait(self.app)
        self.assertEqual(self.app.job['message'], 'Stopped')

    def test_start_and_stop_download_during_scan_leaves_scan_running(self):
        self.app.queue([self.p['id']])
        entered, release_scan = Event(), Event()

        def download(targets):
            entered.set()
            self.app.download_cancel.wait(3)
            raise Cancelled()

        try:
            self.app.start_job('scan', lambda: release_scan.wait(3))
            with patch.object(self.app, 'verify'), patch.object(self.app, 'run_downloads', side_effect=download):
                self.app.action('/api/downloads/start', {})
                self.assertTrue(entered.wait(1))
                self.app.action('/api/stop', {'target': 'download'})
                self.assertTrue(self.app.download_cancel.is_set())
                self.assertFalse(self.app.cancel.is_set())
                self.assertTrue(self.app.job['running'])
                release_scan.set()
                wait(self.app)
        finally:
            release_scan.set()
            self.app.download_cancel.set()
            wait(self.app)
        self.assertEqual(self.app.download_job['message'], 'Stopped')
