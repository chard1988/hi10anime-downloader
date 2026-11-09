import unittest
from unittest.mock import patch
import test_runtime
from test_web import wait
from hi10_downloader.web import Application

class ExclusionTests(unittest.TestCase):
    setUp = test_runtime.RuntimeTests.setUp
    tearDown = test_runtime.RuntimeTests.tearDown

    def test_exclusion_persists_skips_scan_and_queue_and_can_be_reversed(self):
        pid=self.p['id']
        self.app.action('/api/projects/exclude',{'ids':[pid],'excluded':True})
        restored=Application(self.app.config,self.app.output,password='test-password')
        self.assertTrue(restored.snapshot()['projects'][0]['excluded'])
        with patch.object(restored,'verify'), patch('hi10_downloader.web.make_client'):
            restored.scan_projects({pid})
        self.assertEqual(restored.job['total'],0)
        with self.assertRaises(ValueError): restored.queue([pid])
        restored.action('/api/projects/exclude',{'ids':[pid],'excluded':False})
        self.assertEqual(restored.queue([pid])['added'],2)

    def test_excluding_removes_pending_records_and_preserves_completed_files(self):
        self.app.queue([self.p['id']])
        self.app.items[0]['status']='complete'
        target=self.app.output/'keep.mkv';target.write_bytes(b'keep')
        self.app.action('/api/projects/exclude',{'ids':[self.p['id']],'excluded':True})
        self.assertEqual([e['status'] for e in self.app.items],['complete'])
        self.assertEqual(target.read_bytes(),b'keep')

    def test_retry_starts_only_selected_item_and_clear_completed_retains_failed(self):
        self.app.queue([self.p['id']])
        for entry in self.app.items: entry['status']='failed'
        chosen=self.app.items[0]['id']
        with patch.object(self.app,'verify'),patch.object(self.app,'run_downloads') as run:
            self.app.action('/api/downloads/retry',{'id':chosen});wait(self.app)
            self.assertEqual([e['id'] for e in run.call_args.args[0]],[chosen])
        self.assertEqual(self.app.items[1]['status'],'failed')
        self.app.items[0]['status']='complete'
        self.app.action('/api/downloads/clear-completed',{})
        self.assertEqual([e['status'] for e in self.app.items],['failed'])

    def test_filter_applies_before_pagination_and_redacts_urls(self):
        self.app.items=[{'id':str(i),'status':'failed' if i%2 else 'complete','filename':str(i),'file':{'url':'private'}} for i in range(140)]
        state=self.app.snapshot(download_page=1,download_filter='failed')
        self.assertEqual(state['download_total'],140)
        self.assertEqual(state['download_filtered_total'],70)
        self.assertEqual(len(state['downloads']),20)
        self.assertTrue(all(e['status']=='failed' and 'file' not in e for e in state['downloads']))

    def test_exclusion_keeps_cached_counts_and_sends_only_changed_project(self):
        self.app.warm_library()
        first=self.app.snapshot()
        with patch.object(self.app,'selected',side_effect=AssertionError('must not regroup files')),patch.object(self.app,'is_complete',side_effect=AssertionError('must not check files')),patch.object(self.app,'load_project',side_effect=AssertionError('must not load details')):
            self.app.action('/api/projects/exclude',{'ids':[self.p['id']],'excluded':True})
            state=self.app.snapshot(first['library_version'])
        self.assertIsNone(state['projects'])
        self.assertTrue(state['project_updates'][0]['excluded'])
        self.assertEqual(state['project_updates'][0]['count'],first['projects'][0]['count'])
        restored=Application(self.app.config,self.app.output,password='test-password')
        with patch.object(restored,'load_project',side_effect=AssertionError('cached startup must not load details')),patch.object(restored,'write_index',side_effect=AssertionError('cached startup must not rewrite library')):
            restored.warm_library()
        self.assertTrue(restored.snapshot()['projects'][0]['excluded'])
