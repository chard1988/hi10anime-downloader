import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from hi10_downloader.cli import download
from hi10_downloader.parsing import parse_project, select_files
from hi10_downloader.web import Application, ident
from test_web import wait

URL = 'https://hi10anime.com/archives/collection'
HTML = '''<h1 class="entry-title">.hack Collection</h1><div class="entry-content">
<table class="showLinksTable"><caption>Links for: .hack SIGN [720p]</caption><tr><td>
<a href="https://files.test/sign-720/01.mkv">01</a></td></tr></table>
<table class="showLinksTable"><caption>Links for: .hack SIGN [1080p]</caption><tr><td>
<a href="https://files.test/sign-1080/01.mkv">01</a>
<a href="https://files.test/sign-1080/01.mkv">mirror</a></td></tr></table>
<table class="showLinksTable"><caption>Links for: .hack Liminality [480p]</caption><tr><td>
<a href="https://files.test/liminality/01.mkv">01</a>
<a href="https://files.test/liminality/02.mkv">02</a></td></tr></table>
</div>'''


class CollectionTests(unittest.TestCase):
    def project(self):
        project = parse_project(HTML, URL)
        project.update(id=ident(URL), scanned=True, choices={})
        return project

    def test_caption_sections_group_qualities_and_preserve_identical_filenames(self):
        p = self.project()
        self.assertEqual([s['title'] for s in p['sections']], ['.hack SIGN', '.hack Liminality'])
        self.assertEqual(len(p['variants']), 4)
        self.assertEqual(len(p['files']), 3)
        self.assertEqual([f['resolution'] for f in p['files']], [1080,480,480])
        self.assertEqual([f['filename'] for f in p['files']], ['01.mkv','01.mkv','02.mkv'])
        self.assertNotEqual(p['files'][0]['key'], p['files'][1]['key'])
        sign = p['sections'][0]['id']
        chosen = select_files(p['variants'], section_qualities={sign:720})
        self.assertEqual(chosen[0]['resolution'],720)
        explicit = select_files(p['variants'], choices={chosen[0]['key']:1080}, section_qualities={sign:720})
        self.assertEqual(explicit[0]['resolution'],1080)

    def test_plain_heading_sections_and_simple_quality_headings(self):
        p = parse_project('<h1>Collection</h1><h2>Series A</h2><h3>720p</h3><a href="https://a.test/01.mkv">01</a><h2>Series B</h2><h3>1080p</h3><a href="https://b.test/01.mkv">01</a>', URL)
        self.assertEqual([s['title'] for s in p['sections']], ['Series A','Series B'])
        self.assertEqual([f['resolution'] for f in p['files']], [720,1080])
        single = parse_project('<h1>Show</h1><h2>720p</h2><a href="https://a.test/01.mkv">01</a><h2>1080p</h2><a href="https://b.test/01.mkv">01</a>',URL)
        self.assertEqual(single['sections'], [])
        self.assertEqual(len(single['files']),1)
        self.assertNotIn('subfolder',single['files'][0])

    def test_section_selection_counts_and_queue_use_own_subfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            app=Application(root/'config',root/'downloads',password='test')
            p=self.project(); app.catalog['projects']=[p]
            app.state_path.write_text(json.dumps({'cookies':[]}))
            liminality=p['sections'][1]['id']
            app.action('/api/project/settings', {'id':p['id'],'sections':[liminality],'section_qualities':{liminality:480}})
            summary=app.snapshot()['projects'][0]
            self.assertEqual((summary['count'],summary['section_count'],summary['selected_section_count']),(2,2,1))
            details=app.details(p['id'])
            self.assertEqual([s['enabled'] for s in details['sections']], [False,True])
            self.assertEqual(len(details['files']),3)
            requested=[]
            def respond(request):
                requested.append(str(request.url))
                return httpx.Response(200,content=b'\x1a\x45\xdf\xa3collection-test')
            with patch('hi10_downloader.web.make_client', return_value=httpx.Client(transport=httpx.MockTransport(respond))), patch.object(app.cancel,'wait',return_value=False):
                app.queue([p['id']])
                with patch.object(app, 'verify', return_value=None):
                    app.start_downloads(); wait(app)
            self.assertIsNone(app.job['error'])
            self.assertEqual(len(requested),2)
            self.assertTrue(all('/liminality/' in url for url in requested))
            files=list(app.output.glob('*/*/*.mkv'))
            self.assertEqual(len(files),2)
            self.assertEqual({f.parent.name for f in files},{p['sections'][1]['folder']})
            self.assertEqual(app.snapshot()['projects'][0]['remaining'],0)
            restored=Application(app.config,app.output,password='test')
            self.assertEqual(restored.snapshot()['projects'][0]['remaining'],0)
            app.action('/api/project/settings',{'id':p['id'],'sections':[]})
            self.assertEqual(app.snapshot()['projects'][0]['count'],0)
            self.assertEqual(len(app.details(p['id'])['files']),3)
            with self.assertRaises(ValueError):
                app.queue([p['id']])

    def test_invalid_section_setting_does_not_partially_mutate_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Application(Path(tmp)/'config',Path(tmp)/'downloads',password='test')
            p=self.project(); app.catalog['projects']=[p]
            with self.assertRaises(ValueError):
                app.action('/api/project/settings',{'id':p['id'],'quality':480,'sections':['unknown']})
            self.assertNotIn('preferred',p)
            self.assertNotIn('selected_sections',p)

    def test_cli_download_also_preserves_collection_subfolders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=self.project()
            plan=root/'plan.json'; plan.write_text(json.dumps({'version':1,'projects':[p]}))
            args=argparse.Namespace(plan=plan,output=root/'downloads',state=root/'state.json',retries=0,delay=0)
            with patch('hi10_downloader.cli.make_client',return_value=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'\x1a\x45\xdf\xa3video')))),redirect_stdout(io.StringIO()):
                download(args)
            self.assertEqual(len(list(args.output.glob('*/*/*.mkv'))),3)
