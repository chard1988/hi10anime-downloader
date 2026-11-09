from pathlib import Path
import tempfile
import argparse
import io
from contextlib import redirect_stdout
from unittest.mock import patch
import unittest

import httpx

from hi10_downloader.parsing import parse_project, project_links, safe_name
from hi10_downloader.cli import child_path, download_one, make_client, save_json, scan, download


class ParsingTests(unittest.TestCase):
    def test_project_links_resolve_and_deduplicate(self):
        html = '<div id="urlContainer"><a href="/show#top">A</a><a href="/show">B</a><a href="javascript:void(0)">X</a></div>'
        self.assertEqual(project_links(html, 'https://hi10anime.com'), ['https://hi10anime.com/show'])
        with self.assertRaises(ValueError):
            project_links('<h1>Login required</h1>', 'https://hi10anime.com')

    def test_highest_resolution_per_episode_and_edition(self):
        html = '''<h1 class="entry-title">Show: One</h1><div class="entry-content">
        <a href="/Show_01_720p_HEVC.mkv">720p</a><a href="/Show_01_1080p_HEVC.mkv">1080p</a>
        <a href="/Show_02_720p.mkv">720p</a><a href="/Show_02_380p.mkv">380p</a>
        <a href="/Show_01_DirectorsCut_720p.mkv">720p</a></div>'''
        project = parse_project(html, 'https://hi10anime.com/show')
        self.assertEqual([f['resolution'] for f in project['files']], [1080, 720, 720])
        self.assertEqual(project['candidate_count'], 5)
        self.assertTrue(project['folder'].startswith('Show_ One--'))

    def test_heading_quality_and_mirror_duplicates(self):
        html = '''<h1>Show</h1><h2>720p</h2><a href="https://a.test/01.mkv">Episode 1</a>
        <h2>1080p</h2><a href="https://b.test/01.mkv">Episode 1</a>
        <a href="https://c.test/01.mkv">Mirror</a>'''
        files = parse_project(html, 'https://hi10anime.com/show')['files']
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['url'], 'https://b.test/01.mkv')

    def test_url_extension_and_unknown_quality(self):
        files = parse_project('<h1>X</h1><a href="/01.MKV?token=a">A</a><a href="/host">host</a>', 'https://hi10anime.com/x')['files']
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['resolution'], 0)

    def test_wrapped_mkv_targets_are_grouped_by_quality(self):
        from urllib.parse import quote
        high = 'https://files.test/Show_(1080p).mkv?token=private'
        low = 'https://files.test/Show_(720p).mkv'
        html = '<h1>Show</h1>' + ''.join(
            f'<a href="https://ouo.io/s/wrapper?s={quote(url, safe="")}">Video</a>'
            for url in (low, high, high))
        project = parse_project(html, 'https://hi10anime.com/show')
        self.assertEqual(project['candidate_count'], 2)
        self.assertEqual(len(project['files']), 1)
        self.assertEqual(project['files'][0]['url'], high)
        self.assertEqual(project['files'][0]['resolution'], 1080)
        self.assertEqual({v['resolution'] for v in project['variants']}, {720,1080})

    def test_path_restrictions(self):
        self.assertEqual(safe_name('CON'), '_CON')
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('..', '../escape', '/absolute'):
                with self.assertRaises(ValueError):
                    child_path(Path(tmp), name)
            (Path(tmp) / 'link').symlink_to('/tmp')
            with self.assertRaises(ValueError):
                child_path(Path(tmp), 'link')


class DownloadTests(unittest.TestCase):
    def test_stream_and_checksum(self):
        data = b'\x1a\x45\xdf\xa3' + b'video' * 100
        with tempfile.TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=data))) as client:
            path = Path(tmp) / 'episode.mkv'
            record = download_one(client, {'url': 'https://mirror.test/file.mkv'}, 'https://hi10anime.com/show', path)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(record['size'], len(data))
            self.assertFalse(path.with_name('episode.mkv.part').exists())

    def test_error_pages_and_truncation_never_become_videos(self):
        responses = [
            httpx.Response(200, headers={'content-type': 'text/html'}, content=b'<html>Login</html>'),
            httpx.Response(200, content=b'<html>Challenge</html>'),
            httpx.Response(200, content=b''),
            httpx.Response(200, headers={'content-length': '1000'}, content=b'\x1a\x45\xdf\xa3short'),
            httpx.Response(403),
        ]
        for response in responses:
            with self.subTest(response=response), tempfile.TemporaryDirectory() as tmp:
                with httpx.Client(transport=httpx.MockTransport(lambda r: response)) as client:
                    target = Path(tmp) / 'file.mkv'
                    with self.assertRaises((ValueError, httpx.HTTPError)):
                        download_one(client, {'url': 'https://mirror.test/file.mkv'}, 'https://hi10anime.com/show', target)
                    self.assertFalse(target.exists())
                    self.assertFalse(list(Path(tmp).glob('*.part')))

    def test_scan_download_and_verified_rerun(self):
        requests = []
        def respond(request):
            requests.append(str(request.url))
            if request.url.path == '/projects/all-projects':
                return httpx.Response(200, text='<div id="urlContainer"><a href="/show">Show</a></div>')
            if request.url.path == '/show':
                return httpx.Response(200, text='<h1>Show</h1><a href="https://mirror.test/01_720p.mkv">720p</a><a href="https://mirror.test/01_1080p.mkv">1080p</a>')
            return httpx.Response(200, content=b"\x1a\x45\xdf\xa3test-video")
        def client(_):
            return httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True)
        with tempfile.TemporaryDirectory() as tmp, patch('hi10_downloader.cli.make_client', client), redirect_stdout(io.StringIO()):
            root = Path(tmp)
            args = argparse.Namespace(state=root/'session.json', plan=root/'plan.json', project=None,
                                      limit=1, delay=0, output=root/'downloads', retries=0)
            scan(args)
            download(args)
            first_count = len(requests)
            download(args)
            self.assertEqual(len(requests), first_count)
            videos = list(args.output.glob('*/*.mkv'))
            self.assertEqual(len(videos), 1)
            self.assertEqual(videos[0].name, '01_1080p.mkv')
            self.assertTrue((args.output / 'hi10-manifest.json').exists())

    def test_cookies_do_not_leak_to_mirrors(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'state.json'
            save_json(state, {'cookies': [{'name': 'auth', 'value': 'secret', 'domain': '.hi10anime.com', 'path': '/', 'secure': True, 'expires': -1}]})
            with make_client(state) as client:
                self.assertIn('auth=secret', client.build_request('GET', 'https://hi10anime.com/show').headers.get('cookie', ''))
                self.assertNotIn('cookie', client.build_request('GET', 'https://mirror.test/video.mkv').headers)
                self.assertNotIn('cookie', client.build_request('GET', 'http://hi10anime.com/show').headers)
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
