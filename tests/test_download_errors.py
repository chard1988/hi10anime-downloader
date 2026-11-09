import errno
import unittest
from unittest.mock import patch
import httpx
import test_runtime
from hi10_downloader.web import download_error

class DownloadErrorTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown

    def test_final_http_error_is_saved_per_item_without_private_url(self):
        self.app.queue([self.p['id']])
        request=httpx.Request('GET','https://mirror.test/file?token=SECRET')
        response=httpx.Response(403,request=request)
        error=httpx.HTTPStatusError('private url',request=request,response=response)
        with patch('hi10_downloader.web.make_client',return_value=httpx.Client()),patch('hi10_downloader.web.download_one',side_effect=error),patch.object(self.app.download_cancel,'wait',return_value=False):
            self.app.run_downloads()
        for entry in self.app.items:
            self.assertEqual(entry['status'],'failed')
            self.assertEqual(entry['message'],'HTTP 403 Forbidden')
        self.assertNotIn('SECRET',str(self.app.snapshot()))
        self.assertIn('HTTP 403 Forbidden',self.app.jobs_path.read_text())

    def test_error_categories_preserve_useful_cause(self):
        self.assertIn('ReadTimeout',download_error(httpx.ReadTimeout('https://private/?secret=yes')))
        self.assertIn('Permission denied',download_error(PermissionError(errno.EACCES,'private')))
        self.assertIn('No space left',download_error(OSError(errno.ENOSPC,'private')))
        self.assertIn('CERTIFICATE_VERIFY_FAILED',download_error(httpx.ConnectError('CERTIFICATE_VERIFY_FAILED')))
        self.assertIn('not a video',download_error(ValueError('not a video')))
        self.assertNotIn('SECRET',download_error(ValueError('Bad URL https://mirror.test/?token=SECRET')))

    def test_destination_error_is_attached_to_item(self):
        self.app.queue([self.p['id']])
        self.app.items=self.app.items[:1]
        with patch('hi10_downloader.web.make_client',return_value=httpx.Client()),patch('hi10_downloader.web.file_folder',side_effect=PermissionError(errno.EACCES,'denied')),patch.object(self.app.download_cancel,'wait',return_value=False):
            self.app.run_downloads()
        self.assertEqual(self.app.items[0]['status'],'failed')
        self.assertIn('Permission denied',self.app.items[0]['message'])
