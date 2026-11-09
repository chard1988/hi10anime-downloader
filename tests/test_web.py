import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from hi10_downloader.cli import download_one
from hi10_downloader.parsing import parse_project, select_files
from hi10_downloader.web import Application, Cancelled, Handler, ThreadingHTTPServer, ident, validate_state

PAGE = '''<h1>Test project</h1><div class="entry-content">
<a href="https://mirror.test/01_720p.mkv">720p</a>
<a href="https://mirror.test/01_1080p.mkv">1080p</a>
<a href="https://mirror.test/02_1080p.mkv">1080p</a></div>'''
URL = 'https://hi10anime.com/test-project'


def wait(app):
    # Container fsync and instrumented CI can be slower than the in-memory fixtures.
    deadline = time.monotonic() + 30
    while (app.job['running'] or app.download_job['running']) and time.monotonic() < deadline:
        time.sleep(.01)
    if app.job['running'] or app.download_job['running']:
        raise AssertionError('Background job did not finish')


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = Application(self.root / 'config', self.root / 'downloads', password='test-web-password')
        project = parse_project(PAGE, URL)
        project.update(id=ident(URL), scanned=True, choices={})
        self.app.catalog['projects'] = [project]
        self.app.state_path.write_text(json.dumps({'cookies': []}))

    def tearDown(self):
        self.temp.cleanup()

    def test_quality_options_preserved_with_per_file_fallback(self):
        p = self.app.catalog['projects'][0]
        self.assertEqual(len(p['variants']), 3)
        self.assertEqual([v['resolution'] for v in select_files(p['variants'], 720)], [720, 1080])
        inherited = {p['variants'][0]['key']: 0}
        self.assertEqual([v['resolution'] for v in select_files(p['variants'], 720, inherited)], [720, 1080])
        choices = {p['variants'][0]['key']: 1080}
        self.assertEqual([v['resolution'] for v in select_files(p['variants'], 720, choices)], [1080, 1080])
        self.app.action('/api/project/settings', {'id': p['id'], 'quality': 720})
        self.assertEqual(self.app.snapshot()['projects'][0]['count'], 2)
        detail = self.app.details(p['id'])
        self.assertEqual(detail['files'][0]['qualities'], [1080,720])
        self.assertEqual(detail['files'][0]['selected'], 720)

    def test_rejects_unknown_quality_and_cookie_scope(self):
        with self.assertRaises(ValueError):
            self.app.action('/api/project/settings', {'id': ident(URL), 'choices': {'missing-key': 1080}})
        with self.assertRaises(ValueError):
            validate_state({'cookies': [{'name':'auth','value':'x','domain':'evil.test','path':'/'}]})
        result = validate_state({'cookies': [{'name':'auth','value':'secret','domain':'.hi10anime.com','path':'/'}], 'origins': [{'origin': 'https://evil.test'}]})
        self.assertEqual(result['origins'], [])
        self.assertEqual(len(result['cookies']), 1)

    def test_single_job_guard_and_cancel(self):
        blocked = threading.Event()
        self.app.start_job('scan', lambda: blocked.wait(2))
        with self.assertRaises(ValueError):
            self.app.action('/api/preferences', {'quality':720})
        self.app.action('/api/stop', {})
        self.assertTrue(self.app.cancel.is_set())
        blocked.set()
        wait(self.app)

    def test_queue_download_manifest_and_remaining_counts(self):
        p = self.app.catalog['projects'][0]
        self.app.action('/api/project/settings', {'id':p['id'], 'quality':720})
        requested = []
        def respond(request):
            requested.append(str(request.url))
            return httpx.Response(200, content=b'\x1a\x45\xdf\xa3test-video')
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with patch('hi10_downloader.web.make_client', return_value=client), patch.object(self.app.cancel, 'wait', return_value=False), patch.object(self.app.download_cancel, 'wait', return_value=False):
            self.app.queue([p['id']])
            with patch.object(self.app, 'verify', return_value=None):
                self.app.start_downloads()
                wait(self.app)
        self.assertIsNone(self.app.download_job['error'])
        self.assertEqual([e['status'] for e in self.app.items], ['complete','complete'])
        self.assertIn('https://mirror.test/01_720p.mkv', requested)
        self.assertEqual(self.app.snapshot()['projects'][0]['remaining'], 0)
        self.assertEqual(len(list(self.app.output.glob('*/*.mkv'))), 2)
        self.app.save_catalog()
        restored = Application(self.app.config, self.app.output, password='test')
        self.assertEqual(restored.snapshot()['projects'][0]['remaining'], 0)

    def test_cancel_cleans_partial_file(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'\x1a\x45\xdf\xa3video'))) as client:
            def cancel(size,total):
                if size:
                    raise Cancelled()
            target = self.root / 'stopped.mkv'
            with self.assertRaises(Cancelled):
                download_one(client, {'url':'https://mirror.test/test.mkv'}, URL, target, progress=cancel)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.mkv.part').exists())

    def test_interrupted_queue_after_restart(self):
        self.app.jobs_path.write_text(json.dumps([{'status':'downloading','filename':'episode.mkv'}]))
        restored = Application(self.app.config, self.app.output, password='test')
        self.assertEqual(restored.items[0]['status'], 'interrupted')

    def test_authenticated_api_and_private_state_redaction(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}') as client:
                self.assertEqual(client.get('/').status_code, 200)
                self.assertEqual(client.get('/api/state').status_code, 401)
                unlocked = client.post('/api/unlock', json={'password':'test-web-password'})
                self.assertEqual(unlocked.status_code, 200)
                self.assertIn('Max-Age=2592000', unlocked.headers['set-cookie'])
                self.assertIn('HttpOnly', unlocked.headers['set-cookie'])
                self.app.items = [{'status':'queued','filename':'a.mkv','file':{'url':'https://private.test/secret'},'project_url':URL}]
                response = client.get('/api/state')
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('private.test', response.text)
                self.assertNotIn('test-web-password', response.text)
                self.app.items[0]['id'] = 'link-test'
                link = client.get('/api/download-link/link-test')
                self.assertEqual(link.json()['url'], 'https://private.test/secret')
                opened = client.get('/api/download-link/link-test?open=1', follow_redirects=False)
                self.assertEqual(opened.status_code, 302)
                self.assertEqual(opened.headers['location'], 'https://private.test/secret')
                self.app.items[0]['file']['url'] = 'javascript:alert(1)'
                self.assertEqual(client.get('/api/download-link/link-test').status_code, 400)
                self.assertEqual(httpx.get(f'http://127.0.0.1:{server.server_port}/api/download-link/link-test').status_code, 401)
                self.assertEqual(client.get('/api/browser/image').status_code, 400)
                self.assertEqual(client.post('/api/preferences', json={'quality':720}, headers={'Origin':'https://evil.test'}).status_code,403)
                self.assertEqual(client.post('/api/preferences', json={'quality':720}).status_code, 200)
                self.assertIn("frame-ancestors 'none'", response.headers['content-security-policy'])
                self.assertEqual(client.get('/../pyproject.toml').status_code, 404)
        finally:
            server.shutdown()
            server.server_close()
            # Don't initialize Playwright merely to close an unused browser actor.

    def test_refresh_and_scan_use_authenticated_pages(self):
        def respond(request):
            if request.url.path == '/projects/all-projects':
                return httpx.Response(200, text='<div id="urlContainer"><a href="/test-project">Test project</a><a href="https://evil.test/x">ignore</a></div>')
            return httpx.Response(200, text=PAGE)
        def client(_):
            return httpx.Client(transport=httpx.MockTransport(respond))
        with patch('hi10_downloader.web.make_client', client), patch.object(self.app.cancel, 'wait', return_value=False), patch.object(self.app.download_cancel, 'wait', return_value=False):
            self.app.refresh()
            self.assertTrue(self.app.connected)
            self.assertEqual(len(self.app.catalog['projects']), 1)
            self.app.scan_projects({ident(URL)})
            self.assertEqual(self.app.snapshot()['projects'][0]['count'], 2)


if __name__ == '__main__':
    unittest.main()
