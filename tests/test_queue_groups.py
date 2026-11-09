import unittest
import test_runtime

class QueueGroupTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown

    def test_grouping_keeps_all_project_items_together_and_groups_collection_sections(self):
        self.app.items=[{'id':str(i),'project_id':self.p['id'],'project':'Section A' if i%2 else 'Section B','filename':f'{i}.mkv','status':'failed' if i%2 else 'complete','file':{'url':'https://private.test/?secret=hidden'}} for i in range(125)]
        state=self.app.snapshot(grouped=True,group_pages={self.p['id']:0})
        self.assertEqual(len(state['download_groups']),1)
        group=state['download_groups'][0]
        self.assertEqual(group['title'],self.p['title'])
        self.assertEqual(group['count'],125)
        self.assertEqual(group['failed'],62)
        self.assertEqual(len(state['downloads']),50)
        next_page=self.app.snapshot(grouped=True,group_pages={self.p['id']:2})
        self.assertEqual(len(next_page['downloads']),25)
        self.assertTrue(all(e['group_id']==self.p['id'] for e in state['downloads']))
        self.assertNotIn('private.test',str(state))
        filtered=self.app.snapshot(grouped=True,download_filter='failed',group_pages={self.p['id']:1})
        self.assertEqual(filtered['download_groups'][0]['count'],62)
        self.assertEqual(len(filtered['downloads']),12)

    def test_outer_pages_are_project_groups_and_legacy_records_group_by_url(self):
        self.app.items=[{'id':str(i),'project_url':f'https://hi10anime.com/project-{i//2}','project':f'Project {i//2} / section','filename':f'{i}.mkv','status':'queued'} for i in range(12)]
        first=self.app.snapshot(grouped=True)
        last=self.app.snapshot(grouped=True,download_page=1)
        self.assertEqual(first['download_page_total'],2)
        self.assertEqual(len(first['download_groups']),5)
        self.assertEqual(len(first['downloads']),0)
        self.assertEqual(len(last['download_groups']),1)
        self.assertEqual(last['download_groups'][0]['title'],'Project 5')
        self.assertEqual(len(last['downloads']),0)
