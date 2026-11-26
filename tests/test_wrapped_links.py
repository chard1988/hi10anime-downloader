"""Regression for query-wrapped download tables, using sanitized offline HTML."""
from html import escape
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup
import httpx

from hi10_downloader.parsing import download_target, parse_project
from hi10_downloader.web import Application, ident

URL = 'https://hi10anime.com/archives/85321'
HTML = (Path(__file__).parent / 'fixtures/accelerator_wrapped_links.html').read_text()
WRAPPERS = ('https://fc.lc/st?api=fixture&url=', 'https://ouo.io/s/fixture?s=',
            'https://spaste.com/r/fixture?link=')


class WrappedLinkTests(unittest.TestCase):
    def test_accelerator_table_deduplicates_three_wrappers_and_ignores_patch(self):
        project = parse_project(HTML, URL)
        self.assertEqual(project['candidate_count'], 17)
        self.assertEqual(len(project['files']), 17)
        self.assertTrue(all(f['resolution'] == 1080 for f in project['files']))
        self.assertTrue(all(urlsplit(f['url']).hostname == 'media.example.test' for f in project['files']))
        self.assertTrue(any('_05v2_' in f['filename'] for f in project['files']))
        self.assertEqual(sum('_OP' in f['filename'] for f in project['files']), 4)
        self.assertEqual(sum('_ED' in f['filename'] for f in project['files']), 1)
        self.assertFalse(any('mirrors' in f for f in project['files']))

    def test_each_wrapper_column_alone_detects_every_file(self):
        for host in ('fc.lc', 'ouo.io', 'spaste.com'):
            with self.subTest(host=host):
                soup = BeautifulSoup(HTML, 'html.parser')
                for anchor in soup.select('a[href]'):
                    if urlsplit(anchor['href']).hostname != host:
                        anchor.decompose()
                self.assertEqual(len(parse_project(str(soup), URL)['files']), 17)

    def test_encoded_destinations_preserve_signed_query_and_drop_fragment(self):
        target = 'https://files.example.test/Show%20(1080p).mkv?token=a%2Bb%3D&expires=123'
        for wrapper in WRAPPERS:
            with self.subTest(wrapper=wrapper):
                wrapped = wrapper + quote(target + '#fragment', safe='')
                self.assertEqual(download_target(wrapped), target)
                project = parse_project('<a href="' + escape(wrapped, quote=True) + '">DDL</a>', URL)
                self.assertEqual(project['files'][0]['url'], target)
                self.assertEqual(project['files'][0]['resolution'], 1080)

    def test_distinct_destination_hosts_are_retained_as_mirrors(self):
        targets = ['https://first.example.test/Show_01_1080p.mkv',
                   'https://second.example.test/Show_01_1080p.mkv']
        html = ''.join('<a href="' + escape(wrapper + quote(target, safe=''), quote=True) + '">DDL</a>'
                       for wrapper, target in zip(WRAPPERS, targets))
        project = parse_project(html, URL)
        self.assertEqual(len(project['files']), 1)
        self.assertEqual(project['files'][0]['mirrors'], targets)

    def test_only_known_routes_with_one_explicit_http_mkv_destination_are_unwrapped(self):
        invalid = [
            'https://fc.lc/st?url=https://files.example.test/a.mkv&url=https://files.example.test/b.mkv',
            'https://fc.lc/st?url=javascript:alert(1)',
            'https://fc.lc/st?url=file:///a.mkv',
            'https://fc.lc/st?url=https://files.example.test/patch.zip',
            'https://fc.lc/st?url=https://[broken/a.mkv',
            'https://fc.lc/st?url=/a.mkv',
            'https://fc.lc/other?url=https://files.example.test/a.mkv',
            'https://spaste.com/other?link=https://files.example.test/a.mkv',
            'https://unrecognized.example.test/st?url=https://files.example.test/a.mkv',
            'https://notfc.lc/st?url=https://files.example.test/a.mkv',
            'https://fc.lc/shortcode',
        ]
        for wrapped in invalid:
            with self.subTest(wrapped=wrapped):
                self.assertEqual(download_target(wrapped), wrapped)
                html = '<a href="' + escape(wrapped, quote=True) + '">DDL</a>'
                self.assertEqual(parse_project(html, URL)['files'], [])

    def test_web_rescan_replaces_zero_file_result_and_can_queue_detected_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Application(root/'config', root/'output', password='test')
            pid = ident(URL)
            project = parse_project('<h1>To Aru Kagaku no Accelerator</h1>', URL)
            project.update(id=pid, scanned=True, error='No direct MKV links detected.')
            app.catalog['projects'] = [project]
            self.assertEqual(app.snapshot()['projects'][0]['count'], 0)
            def client(_):
                return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=HTML)))
            with patch.object(app, 'verify'), patch('hi10_downloader.web.make_client', client), patch.object(app.cancel, 'wait', return_value=False):
                app.scan_projects({pid})
            self.assertEqual(app.snapshot()['projects'][0]['count'], 17)
            self.assertIsNone(app.snapshot()['projects'][0]['error'])
            self.assertEqual(app.queue([pid])['added'], 17)
            self.assertTrue(all(e['file']['url'].startswith('https://media.example.test/') for e in app.items))
            app.close(timeout=2)
