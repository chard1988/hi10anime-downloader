import json
from pathlib import Path
import tempfile
import unittest
from hi10_downloader.web import Application, validate_state
from hi10_downloader.storage import save_json


class FailClosedTests(unittest.TestCase):
    def test_bad_access_session_state_never_restores_revoked_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);app=Application(root/'config',root/'output',password='test')
            token=app.access_cookie();app.revoke_access_cookie(token)
            path=app.access_sessions_path;path.write_text('{truncated')
            restored=Application(app.config,app.output,password='test')
            self.assertFalse(restored.valid_access_cookie(token))

    def test_unknown_state_version_is_rejected_without_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);config=root/'config';config.mkdir()
            save_json(config/'state-format.json',{'version':999})
            with self.assertRaisesRegex(ValueError,'Unsupported appdata version'):
                Application(config,root/'output',password='test')
            self.assertEqual(json.loads((config/'state-format.json').read_text()),{'version':999})

    def test_invalid_cookie_expiry_is_rejected(self):
        for expiry in ['later',float('nan'),float('inf')]:
            with self.assertRaises(ValueError):
                validate_state({'cookies':[{'name':'auth','value':'test','domain':'hi10anime.com','path':'/','expires':expiry}]})
