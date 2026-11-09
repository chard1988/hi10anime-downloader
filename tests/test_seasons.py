import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from hi10_downloader.parsing import parse_project, select_files, file_key
from hi10_downloader.web import Application, ident
from test_web import wait

URL='https://hi10anime.com/archives/ace-fixture'


def season_page():
    parts=['<h1>Ace Attorney Series [BD 720p | BD 1080p]</h1><div class="entry-content">']
    for season in (2,1):
        for quality,checksum in ((720,'AABBCCDD'),(1080,'11223344')):
            filename=f'(Hi10)_Ace_Attorney_S{season}_-_01_(BD_{quality}p)_(TW)_({checksum}).mkv'
            parts.append(f'<table class="showLinksTable"><thead><tr><th colspan="5">Ace Attorney S{season} [BD {quality}p]</th></tr></thead><tbody><tr><td><a href="https://files.test/{filename}">Download</a></td></tr></tbody></table>')
    return ''.join(parts)+'</div>'


class SeasonTests(unittest.TestCase):
    def test_table_headers_group_qualities_by_season_and_ignore_crc(self):
        p=parse_project(season_page(),URL)
        self.assertEqual([s['season'] for s in p['sections']],[2,1])
        self.assertEqual([s['folder'] for s in p['sections']],['Season 02','Season 01'])
        self.assertEqual(len(p['variants']),4)
        self.assertEqual(len(p['files']),2)
        self.assertEqual([f['resolution'] for f in p['files']],[1080,1080])
        self.assertEqual([f['resolution'] for f in select_files(p['variants'],720)],[720,720])
        self.assertNotEqual(p['files'][0]['key'],p['files'][1]['key'])

    def test_crc_does_not_merge_distinct_editions(self):
        self.assertEqual(file_key('Show_S1_01_(720p)_[A1B2C3D4].mkv'),file_key('Show_S1_01_(1080p)_(11223344).mkv'))
        self.assertNotEqual(file_key('Show_S1_01_DirectorsCut_(720p)_(11223344).mkv'),file_key('Show_S1_01_(1080p)_(AABBCCDD).mkv'))
        self.assertNotEqual(file_key('Show_S1_01_(720p).mkv'),file_key('Show_S2_01_(720p).mkv'))

    def test_filename_seasons_work_without_page_headings(self):
        p=parse_project('<h1>Show</h1><a href="https://a.test/Show_S01E02_1080p.mkv">A</a><a href="https://a.test/Show_Season_2_E02_1080p.mkv">B</a>',URL)
        self.assertEqual([s['folder'] for s in p['sections']],['Season 01','Season 02'])
        self.assertEqual(len(p['files']),2)

    def test_single_explicit_season_and_unlabelled_specials(self):
        p=parse_project('<h1>Show</h1><table class="showLinksTable"><thead><tr><th colspan="4">Show Season 3 [720p]</th></tr></thead><tr><td><a href="https://a.test/01.mkv">01</a></td></tr></table>',URL)
        self.assertEqual(p['sections'][0]['folder'],'Season 03')
        self.assertEqual(p['files'][0]['resolution'],720)
        mixed=parse_project('<h1>Show</h1><a href="https://a.test/Show_S1_01.mkv">01</a><a href="https://a.test/bonus.mkv">Special</a>',URL)
        self.assertEqual(len(mixed['sections']),2)
        self.assertEqual(mixed['files'][0]['subfolder'],'Season 01')
        self.assertNotEqual(mixed['files'][1]['subfolder'],'Season 01')

    def test_collection_series_with_same_season_keep_separate_folders(self):
        html='<h1>Collection</h1>' + ''.join(f'<h2>{name}</h2><a href="https://a.test/{name}_S1_01.mkv">01</a>' for name in ('Series A','Series B'))
        p=parse_project(html,URL)
        self.assertEqual(len(p['sections']),2)
        self.assertNotEqual(p['sections'][0]['folder'],p['sections'][1]['folder'])
        self.assertTrue(all('Season 01' in s['folder'] for s in p['sections']))

    def test_web_selection_and_download_routes_seasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); app=Application(root/'config',root/'downloads',password='test')
            p=parse_project(season_page(),URL);p.update(id=ident(URL),scanned=True,choices={})
            app.catalog['projects']=[p];app.state_path.write_text(json.dumps({'cookies':[]}))
            self.assertEqual(app.snapshot()['projects'][0]['count'],2)
            detail=app.details(p['id'])
            self.assertTrue(all(s['qualities']==[1080,720] for s in detail['sections']))
            with patch('hi10_downloader.web.make_client',return_value=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'\x1a\x45\xdf\xa3video')))),patch.object(app.cancel,'wait',return_value=False):
                app.queue([p['id']])
                with patch.object(app, 'verify', return_value=None):
                    app.start_downloads();wait(app)
            self.assertIsNone(app.job['error'])
            files=list(app.output.glob('*/*/*.mkv'))
            self.assertEqual({f.parent.name for f in files},{'Season 01','Season 02'})
            self.assertEqual(len(files),2)
            self.assertTrue(all('1080p' in f.name for f in files))
            self.assertEqual(app.snapshot()['projects'][0]['remaining'],0)
