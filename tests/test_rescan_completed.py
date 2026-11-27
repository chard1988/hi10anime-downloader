import unittest
from unittest.mock import patch

import httpx

import test_runtime
from test_web import PAGE


class RescanCompletedTests(unittest.TestCase):
    setUp = test_runtime.RuntimeTests.setUp
    tearDown = test_runtime.RuntimeTests.tearDown

    def finish_first_file(self):
        self.app.queue([self.p['id']])
        first = self.app.items[0]
        def respond(request):
            if str(request.url) == first['file']['url']:
                return httpx.Response(200, content=b'\x1a\x45\xdf\xa3fixture-video')
            return httpx.Response(404)
        with patch('hi10_downloader.web.make_client', return_value=httpx.Client(transport=httpx.MockTransport(respond))):
            self.app.run_downloads()
        self.assertEqual(first['status'], 'complete')
        self.assertEqual(self.app.items[1]['status'], 'failed')
        return first

    def test_rescan_after_clearing_history_only_queues_remaining_file(self):
        first = self.finish_first_file()
        self.app.items.remove(first)
        with patch.object(self.app, 'verify'), patch('hi10_downloader.web.make_client', return_value=httpx.Client()), \
                patch('hi10_downloader.web.fetch_page', return_value=PAGE), patch.object(self.app.cancel, 'wait', return_value=False):
            self.app.scan_projects([self.p['id']])
        result = self.app.queue([self.p['id']])
        self.assertEqual(result['added'], 0)
        self.assertEqual(len(self.app.items), 1)
        self.assertEqual(self.app.items[0]['status'], 'queued')

    def test_rescan_title_change_preserves_download_folder(self):
        self.finish_first_file()
        folder = self.p['folder']
        with patch.object(self.app, 'verify'), patch('hi10_downloader.web.make_client', return_value=httpx.Client()), \
                patch('hi10_downloader.web.fetch_page', return_value=PAGE.replace('Test project', 'Renamed project')), \
                patch.object(self.app.cancel, 'wait', return_value=False):
            self.app.scan_projects([self.p['id']])
        self.assertEqual(self.p['folder'], folder)
        self.app.items = [entry for entry in self.app.items if entry['status'] != 'complete']
        self.assertEqual(self.app.queue([self.p['id']])['added'], 0)

    def test_all_completed_is_a_noop_after_history_is_cleared(self):
        self.app.queue([self.p['id']])
        with patch('hi10_downloader.web.make_client', return_value=httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b'\x1a\x45\xdf\xa3fixture-video')))):
            self.app.run_downloads()
        self.assertTrue(all(entry['status'] == 'complete' for entry in self.app.items))
        self.app.items.clear()
        self.assertEqual(self.app.queue([self.p['id']]), {'added': 0, 'pending': 0})

    def test_missing_completed_file_can_be_queued_again(self):
        first = self.finish_first_file()
        (self.app.output / first['folder'] / first['filename']).unlink()
        self.app.items.remove(first)
        self.assertEqual(self.app.queue([self.p['id']])['added'], 1)
