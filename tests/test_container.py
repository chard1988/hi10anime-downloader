import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import httpx

from hi10_downloader.container import ensure_session, login_from_environment, main


class ContainerTests(unittest.TestCase):
    def test_login_requires_credentials_without_session(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'HI10_USERNAME'):
                login_from_environment(Path('/unused'))

    def test_valid_session_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'session.json'
            state.write_text(json.dumps({'cookies': []}))
            client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='<div id="urlContainer"></div>')))
            with patch('hi10_downloader.container.make_client', return_value=client), patch('hi10_downloader.container.login_from_environment') as login:
                ensure_session(state)
                login.assert_not_called()

    def test_forbidden_session_attempts_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'session.json'
            state.write_text('{}')
            client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
            with patch('hi10_downloader.container.make_client', return_value=client), patch('hi10_downloader.container.login_from_environment') as login:
                ensure_session(state)
                login.assert_called_once_with(state)

    def test_batch_uses_persistent_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'HI10_CONFIG_DIR': tmp, 'HI10_DOWNLOAD_DIR': tmp + '/videos', 'HI10_PROJECT_LIMIT': '2'}):
                with patch('hi10_downloader.container.ensure_session'), patch('hi10_downloader.container.scan') as scan, patch('hi10_downloader.container.download') as download:
                    self.assertEqual(main(), 0)
                    args = scan.call_args.args[0]
                    self.assertEqual(args.limit, 2)
                    self.assertEqual(args.output, Path(tmp) / 'videos')
                    self.assertEqual(args.state, Path(tmp) / 'session.json')
                    download.assert_called_once_with(args)

    def test_unraid_template_fields(self):
        root = ET.parse(Path(__file__).resolve().parents[1] / 'unraid/hi10-downloader.xml').getroot()
        fields = {node.attrib['Target']: node.attrib for node in root.findall('Config')}
        self.assertEqual(fields['HI10_WEB_PASSWORD']['Mask'], 'true')
        self.assertEqual(fields['8080']['Type'], 'Port')
        self.assertEqual(root.findtext('WebUI'), 'http://[IP]:[PORT:8080]/')
        self.assertEqual(fields['/downloads']['Type'], 'Path')
        self.assertIn('/config', fields)


if __name__ == '__main__':
    unittest.main()
