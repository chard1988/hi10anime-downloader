"""Bounded React table endpoints and safe built-asset serving."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from hi10_downloader.web import Application
from hi10_downloader.server import application

class FrontendApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.app=Application(root/'config',root/'output',password='test')
        self.app.items=[{'id':str(i),'project_id':f'p{i//120}','project':f'Show {i//120}','filename':f'episode-{i:03}.mkv','status':'failed' if i%2 else 'queued','bytes':0,'message':''} for i in range(360)]
        self.client=httpx.Client(transport=httpx.WSGITransport(app=application(self.app)),base_url='http://local.test')
        self.client.post('/api/unlock',json={'password':'test'})
    def tearDown(self):
        self.client.close();self.app.close(timeout=1);self.temp.cleanup()
    def test_server_search_and_pagination_share_consistent_counts(self):
        result=self.app.snapshot(grouped=True,group_pages={'p0':1},download_page_size=10,download_search='SHOW 0')
        self.assertEqual(result['download_group_total'],1)
        self.assertEqual(result['download_filtered_total'],120)
        self.assertEqual(len(result['downloads']),10)
        self.assertEqual(result['downloads'][0]['filename'],'episode-010.mkv')
        result=self.client.get('/api/state',params={'grouped':'1','download_search':'episode-121','download_filter':'failed','group_pages':'{"p1":0}','download_page_size':25}).json()
        self.assertEqual(result['download_filtered_total'],1)
        self.assertEqual(result['downloads'][0]['filename'],'episode-121.mkv')
        self.assertNotIn('file',result['downloads'][0])
    def test_bounds_and_search_cache_are_limited(self):
        for kwargs in ({'download_page_size':5000},{'group_page_size':0},{'download_search':'x'*201}):
            with self.assertRaises(ValueError):self.app.snapshot(**kwargs)
        for i in range(30):self.app.snapshot(download_search=str(i))
        self.assertLessEqual(len(self.app._queue_groups_cache),8)
        self.assertEqual(self.client.get('/api/state?download_page_size=999999').status_code,400)
    def test_static_root_blocks_traversal_and_private_source(self):
        for path in ('/../routes.py','/%2e%2e/routes.py','/assets/%2e%2e/%2e%2e/routes.py','/api/not-a-route','/package.json','/assets/private.json'):
            self.assertEqual(self.client.get(path).status_code,404,path)
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/theme.js').status_code,200)
        index=self.client.get('/').text
        import re
        assets=re.findall(r'(?:src|href)="(/assets/[^\"]+)"',index)
        self.assertTrue(assets)
        for asset in assets:self.assertEqual(self.client.get(asset).status_code,200)
