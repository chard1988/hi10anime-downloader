import json
import unittest
import test_runtime
from hi10_downloader.web import Application

class EditUrlTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown

    def test_edited_url_persists_survives_requeue_and_does_not_start(self):
        self.app.queue([self.p['id']]);entry=self.app.items[0]
        entry['status']='failed';old_name=entry['filename']
        replacement='https://mirror.test/new.mkv?token=PRIVATE'
        self.app.action('/api/downloads/edit-url',{'id':entry['id'],'url':replacement})
        self.assertEqual(entry['status'],'queued')
        self.assertEqual(entry['filename'],old_name)
        self.assertFalse(self.app.download_job['running'])
        self.app.queue([self.p['id']])
        self.assertEqual(entry['file']['url'],replacement)
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertEqual(restored.items[0]['file']['url'],replacement)
        self.assertNotIn('PRIVATE',json.dumps(restored.snapshot()))

    def test_invalid_urls_and_active_batch_are_rejected_without_changes(self):
        self.app.queue([self.p['id']]);entry=self.app.items[0];old=entry['file']['url']
        for url in ['javascript:alert(1)','file:///etc/passwd','https://user:pass@mirror.test/a','https://mirror.test/a\nb','https://mirror.test:bad/a','https://','']:
            with self.subTest(url=url),self.assertRaises(ValueError):
                self.app.action('/api/downloads/edit-url',{'id':entry['id'],'url':url})
            self.assertEqual(entry['file']['url'],old)
        self.app.download_job['running']=True
        try:
            with self.assertRaises(ValueError):
                self.app.action('/api/downloads/edit-url',{'id':entry['id'],'url':'https://mirror.test/new.mkv'})
        finally:self.app.download_job['running']=False
        self.assertEqual(entry['file']['url'],old)
