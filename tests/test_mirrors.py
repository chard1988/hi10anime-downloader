import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from hi10_downloader.cli import _download, save_json
from hi10_downloader.mirrors import check_mirrors, MirrorCheckError, try_next_mirror, MAX_MIRRORS
from hi10_downloader.parsing import parse_project, select_files
from hi10_downloader.web import Cancelled, ident
import test_runtime

URL = 'https://hi10anime.com/test-project'
LINKS = [f'https://mirror-{i}.invalid/Show_01_1080p.mkv?token=private-{i}' for i in range(3)]
VIDEO = b'\x1a\x45\xdf\xa3fixture-video'


def project():
    html='<h1>Show</h1>'+''.join(f'<a href="{url}">1080p</a>' for url in LINKS)
    html+='<a href="https://lower.invalid/Show_01_720p.mkv">720p</a>'
    return parse_project(html,URL)


class MirrorTests(unittest.TestCase):
    def test_same_file_quality_mirrors_are_retained_without_mixing_qualities(self):
        p=project()
        self.assertEqual(len(p['files']),1)
        self.assertEqual(p['files'][0]['resolution'],1080)
        self.assertEqual(p['files'][0]['mirrors'],LINKS)
        lower=select_files(p['variants'],preferred=720)[0]
        self.assertEqual(lower['resolution'],720)
        self.assertNotIn('mirrors',lower)
        self.assertTrue(all('mirrors' not in v for v in p['variants']))
        movie=parse_project(''.join(f'<a href="https://host-{i}.invalid/Movie_1080p.mkv">Film</a>' for i in range(3)),URL)
        self.assertEqual(len(movie['files']),1)
        self.assertEqual(len(movie['files'][0]['mirrors']),3)

    def test_sections_and_episodes_remain_separate(self):
        html=''
        for section in ('Season 1','Season 2'):
            html+=f'<h2>{section}</h2>'
            for episode in ('01','02'):
                for host in ('one','two'):
                    html+=f'<a href="https://{host}.invalid/Show_{episode}_1080p.mkv">Download</a>'
        p=parse_project(html,URL)
        self.assertEqual(len(p['files']),4)
        self.assertTrue(all(len(item['mirrors'])==2 for item in p['files']))

    def test_probe_all_alternatives_and_reject_html_http_200(self):
        requests=[]
        def respond(request):
            requests.append(request)
            if request.url.host=='mirror-0.invalid':return httpx.Response(404)
            if request.url.host=='mirror-1.invalid':return httpx.Response(200,content=b'<html>login</html>')
            return httpx.Response(206,headers={'Content-Range':'bytes 0-3/1000'},content=VIDEO[:4])
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result=check_mirrors(client,project()['files'][0],URL)
        self.assertEqual(result.urls,[LINKS[2]])
        self.assertEqual(result.checked,3)
        self.assertTrue(all(r.headers['Range']=='bytes=0-3' and r.headers['Referer']==URL for r in requests))
        self.assertEqual([str(r.url) for r in requests],LINKS)

    def test_ignored_range_is_closed_after_prefix_and_each_link_is_checked(self):
        class PrefixOnly(httpx.SyncByteStream):
            def __iter__(self):
                yield VIDEO[:4]
                raise AssertionError('Probe consumed video after prefix')
            def close(self):pass
        requested=[]
        with httpx.Client(transport=httpx.MockTransport(lambda r:(requested.append(str(r.url)) or httpx.Response(200,stream=PrefixOnly())))) as client:
            result=check_mirrors(client,project()['files'][0],URL)
        self.assertEqual(result.urls,LINKS)
        self.assertEqual(requested,LINKS)

    def test_single_link_never_adds_a_probe(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: self.fail('Unexpected probe'))) as client:
            result=check_mirrors(client,{'url':LINKS[0]},URL)
        self.assertEqual(result.checked,0)
        self.assertEqual(result.urls,[LINKS[0]])

    def test_invalid_certificate_is_skipped_for_a_valid_same_quality_mirror(self):
        requested=[]
        def respond(request):
            requested.append(str(request.url))
            if request.url.host=='mirror-0.invalid':
                raise httpx.ConnectError('[SSL: CERTIFICATE_VERIFY_FAILED] Hostname mismatch',request=request)
            return httpx.Response(200,content=VIDEO)
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result=check_mirrors(client,project()['files'][0],URL)
        self.assertEqual(result.urls,LINKS[1:])
        self.assertEqual(requested,LINKS)
        def invalid_certificate(request):
            raise httpx.ConnectError('CERTIFICATE_VERIFY_FAILED https://private/?token=SECRET',request=request)
        with httpx.Client(transport=httpx.MockTransport(invalid_certificate)) as client:
            with self.assertRaisesRegex(MirrorCheckError,'TLS certificate verification failed') as error:
                check_mirrors(client,project()['files'][0],URL)
        self.assertNotIn('SECRET',str(error.exception))

    def test_all_dead_stays_selected_quality_and_redacts_signed_urls(self):
        def respond(request):
            if request.url.host=='mirror-0.invalid':return httpx.Response(403)
            if request.url.host=='mirror-1.invalid':raise httpx.ConnectTimeout('private-token')
            return httpx.Response(200,headers={'Content-Type':'text/html'},content=b'login')
        with httpx.Client(transport=httpx.MockTransport(respond)) as client,self.assertRaises(MirrorCheckError) as error:
            check_mirrors(client,project()['files'][0],URL)
        self.assertIn('selected quality',str(error.exception))
        self.assertIn('HTTP 403',str(error.exception))
        self.assertIn('network timeout',str(error.exception))
        self.assertNotIn('private',str(error.exception))
        self.assertNotIn('https://',str(error.exception))

    def test_invalid_partial_response_is_not_active(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(206,headers={'Content-Range':'bytes 4-7/100'},content=VIDEO[:4]))) as client,self.assertRaisesRegex(MirrorCheckError,'invalid partial response'):
            check_mirrors(client,project()['files'][0],URL)

    def test_probe_cancellation_and_budget_and_count_are_bounded(self):
        done=[]
        def cancel():
            if done:raise Cancelled()
        def progress(number,total,active):
            if number:done.append(number)
        with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=VIDEO))) as client:
            with self.assertRaises(Cancelled):check_mirrors(client,project()['files'][0],URL,cancel,progress)
            self.assertEqual(done,[1])
            with patch('hi10_downloader.mirrors.time.monotonic',side_effect=[0,61]),self.assertRaisesRegex(MirrorCheckError,'time limit'):
                check_mirrors(client,project()['files'][0],URL)
            with self.assertRaisesRegex(MirrorCheckError,'Too many'):
                check_mirrors(client,{'url':'https://one.invalid/file.mkv','mirrors':[f'https://h{i}.invalid/file.mkv' for i in range(MAX_MIRRORS)]},URL)

    def test_redirects_use_the_existing_client_and_cookie_scope(self):
        requested=[]
        def respond(request):
            requested.append(request)
            if request.url.host=='mirror-0.invalid':
                return httpx.Response(302,headers={'Location':'https://cdn.invalid/Show_01_1080p.mkv'})
            if request.url.host=='cdn.invalid':return httpx.Response(200,content=VIDEO)
            return httpx.Response(404)
        cookies=httpx.Cookies();cookies.set('wordpress_logged_in_fixture','private',domain='hi10anime.com')
        with httpx.Client(transport=httpx.MockTransport(respond),follow_redirects=True,cookies=cookies) as client:
            result=check_mirrors(client,project()['files'][0],URL)
        self.assertEqual(result.urls,[LINKS[0]])
        self.assertTrue(all('cookie' not in r.headers for r in requested))
        self.assertTrue(all(r.headers['range']=='bytes=0-3' for r in requested))

    def test_invalid_port_or_embedded_credentials_never_open_a_connection(self):
        for bad in ('https://bad.invalid:not-a-port/file.mkv','https://user:private@bad.invalid/file.mkv'):
            requested=[]
            with httpx.Client(transport=httpx.MockTransport(lambda r:(requested.append(str(r.url)) or httpx.Response(200,content=VIDEO)))) as client:
                result=check_mirrors(client,{'url':bad,'mirrors':[bad,LINKS[1]]},URL)
            self.assertEqual(result.urls,[LINKS[1]])
            self.assertEqual(requested,[LINKS[1]])

    def test_retry_after_is_not_bypassed_by_switching_paths_on_same_host(self):
        first='https://one.invalid/a.mkv';other='https://one.invalid/b.mkv'
        response=httpx.Response(429,headers={'Retry-After':'60'},request=httpx.Request('GET',first))
        error=httpx.HTTPStatusError('rate limited',request=response.request,response=response)
        item={'url':first}
        self.assertFalse(try_next_mirror(item,[first,other],error))
        self.assertTrue(try_next_mirror(item,[first,other,LINKS[1]],error))
        self.assertEqual(item['url'],LINKS[1])

    def test_disk_policy_errors_do_not_switch_mirrors(self):
        for error in (OSError(28,'full'),ValueError('Insufficient free disk space'),ValueError('Download exceeds maximum file size.')):
            item={'url':LINKS[0]}
            self.assertFalse(try_next_mirror(item,LINKS,error))
            self.assertEqual(item['url'],LINKS[0])


class WebMirrorTests(unittest.TestCase):
    setUp=test_runtime.RuntimeTests.setUp
    tearDown=test_runtime.RuntimeTests.tearDown

    def queue_project(self):
        p=project();p.update(id=ident(URL),scanned=True,choices={})
        self.app.catalog['projects']=[p];self.p=p
        self.app.queue([p['id']])
        return self.app.items[0]

    def run_fixture(self,respond):
        with patch('hi10_downloader.web.make_client',return_value=httpx.Client(transport=httpx.MockTransport(respond))),patch.object(self.app.download_cancel,'wait',return_value=False):
            self.app.run_downloads()

    def test_active_link_download_and_verified_rerun_and_project_count(self):
        entry=self.queue_project();requests=[]
        def respond(request):
            requests.append(request)
            return httpx.Response(200,content=VIDEO) if request.url.host=='mirror-1.invalid' else httpx.Response(404)
        self.run_fixture(respond)
        self.assertEqual(entry['status'],'complete')
        self.assertEqual(entry['file']['url'],LINKS[1])
        self.assertIn('3 links; 1 active',entry['message'])
        self.assertEqual(len([r for r in requests if 'range' not in r.headers]),1)
        self.assertTrue(self.app.is_complete(self.p,self.app.selected(self.p)[0],self.app.manifest()))
        self.run_fixture(lambda r:self.fail('Verified file should not probe or download'))
        self.assertEqual(entry['status'],'complete')

    def test_all_dead_marks_one_failed_file_without_lower_quality_request(self):
        entry=self.queue_project();requested=[]
        self.run_fixture(lambda r:(requested.append(str(r.url)) or httpx.Response(404)))
        self.assertEqual(entry['status'],'failed')
        self.assertIn('No active download link',entry['message'])
        self.assertEqual(requested,LINKS)
        self.assertFalse(list(self.app.output.rglob('*.mkv')))

    def test_link_dying_after_probe_falls_back_to_another_active_mirror(self):
        entry=self.queue_project();full=[]
        def respond(request):
            if 'range' in request.headers:return httpx.Response(200,content=VIDEO[:4])
            full.append(str(request.url))
            return httpx.Response(410) if request.url.host=='mirror-0.invalid' else httpx.Response(200,content=VIDEO)
        self.run_fixture(respond)
        self.assertEqual(entry['status'],'complete')
        self.assertEqual(full,LINKS[:2])
        self.assertEqual(entry['file']['url'],LINKS[1])

    def test_stop_after_transfer_failure_does_not_request_another_mirror(self):
        entry=self.queue_project();full=[]
        def respond(request):
            if 'range' in request.headers:return httpx.Response(200,content=VIDEO)
            full.append(str(request.url));self.app.download_cancel.set()
            return httpx.Response(410)
        with self.assertRaises(Cancelled):self.run_fixture(respond)
        self.assertEqual(full,[LINKS[0]])
        self.assertEqual(entry['status'],'interrupted')

    def test_certificate_failure_after_probe_uses_next_active_mirror(self):
        entry=self.queue_project();full=[]
        def respond(request):
            if 'range' in request.headers:return httpx.Response(200,content=VIDEO[:4])
            full.append(str(request.url))
            if request.url.host=='mirror-0.invalid':
                raise httpx.ConnectError('CERTIFICATE_VERIFY_FAILED: Hostname mismatch',request=request)
            return httpx.Response(200,content=VIDEO)
        self.run_fixture(respond)
        self.assertEqual(entry['status'],'complete')
        self.assertEqual(full,LINKS[:2])

    def test_single_invalid_certificate_fails_once_with_actionable_error(self):
        entry=self.queue_project()
        entry['file'].pop('mirrors')
        entry['url_override']=LINKS[0]
        requested=[]
        def respond(request):
            requested.append(str(request.url))
            raise httpx.ConnectError('CERTIFICATE_VERIFY_FAILED: Hostname mismatch',request=request)
        self.run_fixture(respond)
        self.assertEqual(entry['status'],'failed')
        self.assertEqual(requested,[LINKS[0]])
        self.assertIn('edit this item',entry['message'])
        self.assertNotIn('after 3 attempts',entry['message'])
        self.assertFalse(list(self.app.output.rglob('*.mkv')))

    def test_old_queue_uses_cached_alternatives_at_its_queued_quality(self):
        entry=self.queue_project();entry['file'].pop('mirrors')
        self.p['preferred']=720  # Queued quality must not follow later project changes.
        requested=[]
        self.run_fixture(lambda r:(requested.append(str(r.url)) or (httpx.Response(200,content=VIDEO) if r.url.host=='mirror-1.invalid' else httpx.Response(404))))
        self.assertEqual(entry['status'],'complete')
        self.assertEqual(entry['file']['resolution'],1080)
        self.assertEqual(requested,LINKS+[LINKS[1]])

    def test_manual_url_edit_is_not_overridden_even_after_requeue(self):
        entry=self.queue_project()
        manual='https://manual.invalid/repaired.mkv'
        self.app.action('/api/downloads/edit-url',{'id':entry['id'],'url':manual})
        self.app.queue([self.p['id']])
        self.assertNotIn('mirrors',entry['file'])
        requested=[]
        self.run_fixture(lambda r:(requested.append(r) or httpx.Response(200,content=VIDEO)))
        self.assertEqual([str(r.url) for r in requested],[manual])
        self.assertTrue(all('range' not in r.headers for r in requested))
        self.assertEqual(entry['status'],'complete')


class CliMirrorTests(unittest.TestCase):
    def test_cli_uses_active_alternative_and_recognizes_its_manifest_on_rerun(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=project()
            args=argparse.Namespace(plan=root/'plan.json',state=root/'config/session.json',output=root/'output',retries=0,delay=0)
            save_json(args.plan,{'version':1,'projects':[p]})
            requested=[]
            def respond(request):
                requested.append(request)
                return httpx.Response(200,content=VIDEO) if request.url.host=='mirror-2.invalid' else httpx.Response(404)
            with patch('hi10_downloader.cli.make_client',return_value=httpx.Client(transport=httpx.MockTransport(respond))),redirect_stdout(io.StringIO()):_download(args)
            self.assertEqual(len([r for r in requested if 'range' not in r.headers]),1)
            self.assertEqual(next(iter(json.loads((args.output/'hi10-manifest.json').read_text()).values()))['url'],LINKS[2])
            with patch('hi10_downloader.cli.make_client',return_value=httpx.Client(transport=httpx.MockTransport(lambda r:self.fail('Unexpected rerun request')))),redirect_stdout(io.StringIO()):_download(args)
