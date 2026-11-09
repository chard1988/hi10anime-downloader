import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpcore
import httpx

from hi10_downloader.network import PublicBackend, public_addresses, permitted, bounded_page
from hi10_downloader.server import application
from hi10_downloader.storage import transaction, recover_transaction, save_json, load_json
from hi10_downloader.web import Application


class NetworkPolicyTests(unittest.TestCase):
    def test_private_mixed_ipv6_and_metadata_are_blocked(self):
        for address in ['127.0.0.1', '10.0.1.100', '169.254.169.254', '::1', '::ffff:127.0.0.1', 'fc00::1', '224.0.0.1']:
            self.assertFalse(permitted(address), address)
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ['1.1.1.1', '127.0.0.1']]
        with patch('socket.getaddrinfo', return_value=records), self.assertRaises(httpcore.ConnectError):
            public_addresses('mixed.test', 443)

    def test_connections_pin_validated_address_not_hostname(self):
        with patch('hi10_downloader.network.public_addresses', return_value=['1.1.1.1']), patch('httpcore._backends.sync.SyncBackend.connect_tcp', return_value='stream') as connect:
            self.assertEqual(PublicBackend().connect_tcp('public.test', 443, timeout=2), 'stream')
            self.assertEqual(connect.call_args.args[:2], ('1.1.1.1', 443))

    def test_explicit_exception_is_narrow_and_stream_size_is_bounded(self):
        with patch.dict('os.environ', {'HI10_ALLOWED_NETWORKS': '10.0.1.100/32'}):
            self.assertTrue(permitted('10.0.1.100'))
            self.assertFalse(permitted('10.0.1.101'))
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'x'*100))) as client:
            with self.assertRaisesRegex(ValueError, 'size limit'):
                bounded_page(client, 'https://public.test', limit=10)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = Application(root/'config', root/'output', password='private')
        self.client = httpx.Client(transport=httpx.WSGITransport(app=application(self.app)), base_url='http://local.test')

    def tearDown(self):
        self.client.close(); self.app.close(timeout=1); self.temp.cleanup()

    def test_logout_revokes_copied_cookie_even_after_restart(self):
        self.assertEqual(self.client.post('/api/unlock', json={'password':'private'}).status_code, 200)
        value = self.client.cookies['hi10_access']
        self.assertTrue(self.app.valid_access_cookie(value))
        self.assertEqual(self.client.post('/api/lock', json={}).status_code, 200)
        self.assertFalse(self.app.valid_access_cookie(value))
        restored = Application(self.app.config, self.app.output, password='private')
        self.assertFalse(restored.valid_access_cookie(value))

    def test_rate_limit_and_health_without_site_connection(self):
        self.assertEqual(self.client.get('/healthz').json(), {'status':'ok'})
        for _ in range(10):
            self.assertEqual(self.client.post('/api/unlock', json={'password':'wrong'}).status_code, 401)
        self.assertEqual(self.client.post('/api/unlock', json={'password':'wrong'}).status_code, 429)
        self.assertEqual(self.client.get('/api/state').status_code, 401)

    def test_proxy_spoof_does_not_enable_secure_cookie_but_configured_origin_does(self):
        response = self.client.post('/api/unlock', json={'password':'private'}, headers={'X-Forwarded-Proto':'https'})
        self.assertNotIn('; Secure', response.headers['set-cookie'])
        with patch.dict('os.environ', {'HI10_WEB_ORIGIN':'https://hi10.test','HI10_ALLOWED_HOSTS':'local.test'}):
            response = self.client.post('/api/unlock', json={'password':'private'})
            self.assertIn('; Secure', response.headers['set-cookie'])
            self.assertEqual(self.client.post('/api/unlock', json={'password':'private'},headers={'Origin':'http://hi10.test'}).status_code,403)
            self.assertEqual(self.client.get('/healthz',headers={'Host':'unknown.test'}).status_code,400)

    def test_request_failure_has_request_id_without_exception_secrets(self):
        self.app.access_cookie = lambda: (_ for _ in ()).throw(RuntimeError('SECRET'))
        response = self.client.post('/api/unlock', json={'password':'private'})
        self.assertEqual(response.status_code, 500)
        self.assertIn('X-Request-ID', response.headers)
        self.assertNotIn('SECRET', response.text)


class TransactionTests(unittest.TestCase):
    def test_failed_commit_rolls_forward_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config=root/'config'; output=root/'output';config.mkdir();output.mkdir()
            first,second=config/'a.json',output/'b.json'
            save_json(first,{'old':1});save_json(second,{'old':2})
            import hi10_downloader.storage as storage
            real=storage._single_save
            def interrupted(path,data):
                if Path(path)==second:
                    raise OSError('simulated power failure')
                return real(path,data)
            with patch.object(storage,'_single_save',side_effect=interrupted),self.assertRaises(OSError):
                with transaction(config,output):
                    save_json(first,{'new':1});save_json(second,{'new':2})
            self.assertTrue((config/'pending-transaction.json').exists())
            recover_transaction(config,output)
            self.assertEqual(load_json(first),{'new':1});self.assertEqual(load_json(second),{'new':2})
            self.assertFalse((config/'pending-transaction.json').exists())

    def test_transaction_cannot_escape_owned_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'config';config.mkdir()
            save_json(config/'pending-transaction.json',{'version':1,'writes':{str(root/'escape.json'):{'bad':True}}})
            with self.assertRaisesRegex(ValueError,'invalid destination'):
                recover_transaction(config,root/'output')
            self.assertFalse((root/'escape.json').exists())
