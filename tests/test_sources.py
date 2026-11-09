import unittest
import httpx

from hi10_downloader.parsing import project_links
from hi10_downloader.cli import LIST_URL
from hi10_downloader.sources import load_project_list


class SourceTests(unittest.TestCase):
    def test_dynamic_list_uses_referenced_source_and_keeps_only_site_links(self):
        visited = []
        def respond(request):
            visited.append(str(request.url))
            if request.url.host == 'hi10anime.com':
                return httpx.Response(200, text='<div id="urlContainer"></div><script src="https://xlordnoro.github.io/dynamic_all_projects_post.js"></script>')
            if request.url.host == 'xlordnoro.github.io':
                return httpx.Response(200, text="const githubRawUrl = 'https://raw.githubusercontent.com/xlordnoro/xlordnoro.github.io/master/formattedPostUrls_sorted.txt';")
            return httpx.Response(200, text='<a href="https://hi10anime.com/archives/1">Project One</a><a href="https://evil.test/x">Ignore</a>')
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            html = load_project_list(client)
        self.assertEqual(project_links(html, LIST_URL), ['https://hi10anime.com/archives/1'])
        self.assertIn('Project One', html)
        self.assertEqual(len(visited), 3)

    def test_existing_links_do_not_fetch_scripts(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='<div id="urlContainer"><a href="/archives/1">One</a></div>'))) as client:
            self.assertEqual(project_links(load_project_list(client), LIST_URL), ['https://hi10anime.com/archives/1'])

    def test_empty_list_is_an_error(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='<div id="urlContainer"></div>'))) as client:
            with self.assertRaisesRegex(ValueError, 'No project links'):
                load_project_list(client)

    def test_unexpected_data_source_is_rejected(self):
        def respond(request):
            if request.url.host == 'hi10anime.com':
                return httpx.Response(200, text='<div id="urlContainer"></div><script src="https://xlordnoro.github.io/dynamic_all_projects_post.js"></script>')
            return httpx.Response(200, text="const githubRawUrl = 'https://localhost/private';")
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(ValueError, 'unexpected data source'):
                load_project_list(client)
