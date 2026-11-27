import unittest
from unittest.mock import patch
import test_runtime
from test_web import wait

class BulkQueueTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown

    def test_start_selected_leaves_other_failed_items_waiting(self):
        self.app.queue([self.p['id']])
        for entry in self.app.items: entry['status']='failed'
        chosen=self.app.items[0]['id']
        with patch.object(self.app,'verify'),patch.object(self.app,'run_downloads') as run:
            self.app.action('/api/downloads/start-selected',{'ids':[chosen]});wait(self.app)
            self.assertEqual([e['id'] for e in run.call_args.args[0]],[chosen])
        self.assertEqual(self.app.items[1]['status'],'failed')

    def test_remove_selected_retains_other_entries_and_files(self):
        self.app.queue([self.p['id']])
        target=self.app.output/'keep.mkv';target.write_bytes(b'keep')
        chosen=self.app.items[0]['id'];remaining=self.app.items[1]['id']
        self.app.action('/api/downloads/remove-selected',{'ids':[chosen]})
        self.assertEqual([e['id'] for e in self.app.items],[remaining])
        self.assertEqual(target.read_bytes(),b'keep')
        with self.assertRaises(ValueError):
            self.app.action('/api/downloads/remove-selected',{'ids':[remaining,'missing']})
        self.assertEqual([e['id'] for e in self.app.items],[remaining])

    def test_bulk_removal_blocked_while_downloading(self):
        self.app.queue([self.p['id']]);self.app.download_job['running']=True
        try:
            with self.assertRaises(ValueError):
                self.app.action('/api/downloads/remove-selected',{'ids':[self.app.items[0]['id']]})
        finally:self.app.download_job['running']=False
        self.assertEqual(len(self.app.items),2)

    def test_queue_details_include_full_destination_but_not_private_link(self):
        self.app.queue([self.p['id']])
        self.app.items[0]['file']['subfolder']='Season 01'
        self.app.items[0].update(status='failed',message='HTTP 403 Forbidden')
        state=self.app.snapshot()
        first=state['downloads'][0]
        expected=self.app.output.absolute()/self.app.items[0]['folder']/'Season 01'/first['filename']
        self.assertEqual(first['destination'],str(expected))
        self.assertEqual(first['message'],'HTTP 403 Forbidden')
        self.assertNotIn('file',first)
        self.assertNotIn('url',first)

    def test_remove_projects_removes_all_group_history_and_preserves_files_and_library(self):
        from copy import deepcopy
        import json
        self.app.queue([self.p['id']])
        first=self.app.items[0];first['status']='complete'
        for i in range(65):
            item=deepcopy(self.app.items[1]);item.update(id=f'extra-{i}',status='failed')
            self.app.items.append(item)
        keep=deepcopy(first);keep.update(id='other',project_id='other-project',status='queued')
        self.app.items.append(keep);self.app.save_queue()
        target=self.app.output/'keep.mkv';target.write_bytes(b'keep')
        catalog=deepcopy(self.app.catalog)
        self.app.action('/api/downloads/remove-projects',{'ids':[self.p['id']]})
        self.assertEqual(self.app.items,[keep])
        self.assertEqual(json.loads(self.app.jobs_path.read_text()),[keep])
        self.assertEqual(self.app.catalog,catalog)
        self.assertEqual(target.read_bytes(),b'keep')

    def test_remove_projects_validates_entire_selection_and_requires_idle(self):
        from copy import deepcopy
        self.app.queue([self.p['id']]);before=deepcopy(self.app.items)
        for data in ({'ids':[]},{'ids':'wrong'},{'ids':[None]},{'ids':[self.p['id'],'missing']}):
            with self.assertRaises(ValueError):self.app.action('/api/downloads/remove-projects',data)
            self.assertEqual(self.app.items,before)
        for job in (self.app.job,self.app.download_job):
            job['running']=True
            try:
                with self.assertRaises(ValueError):self.app.action('/api/downloads/remove-projects',{'ids':[self.p['id']]})
            finally:job['running']=False
            self.assertEqual(self.app.items,before)

    def test_remove_orphan_group_uses_same_id_as_snapshot_and_cancels_empty_schedule(self):
        self.app.items=[{'id':'old','project':'Old project','filename':'old.mkv','status':'failed'}]
        group=self.app.snapshot(grouped=True)['download_groups'][0]['id']
        self.app.schedule['starts_at']=9999999999
        self.app.action('/api/downloads/remove-projects',{'ids':[group]})
        self.assertEqual(self.app.items,[])
        self.assertIsNone(self.app.schedule['starts_at'])
