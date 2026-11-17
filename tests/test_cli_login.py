from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from playwright.sync_api import Error as BrowserError
from hi10_downloader.cli import login, main


class DesktopLoginTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state=Path(self.directory.name)/'capture/session.json'
        self.playwright=MagicMock()
        self.browser=self.playwright.chromium.launch.return_value
        self.context=self.browser.new_context.return_value
        self.context.storage_state.return_value={'cookies':[
            {'name':'auth','value':'fixture','domain':'.hi10anime.com','path':'/'},
            {'name':'other','value':'fixture','domain':'other.invalid','path':'/'}],
            'origins':[{'origin':'https://other.invalid'}]}

    def capture(self, browser='chromium'):
        with patch('playwright.sync_api.sync_playwright') as factory,patch('builtins.input',return_value=''),redirect_stdout(StringIO()):
            factory.return_value.__enter__.return_value=self.playwright
            login(SimpleNamespace(state=self.state,browser=browser))

    def test_installed_chrome_keeps_sandbox_and_saves_only_site_cookies(self):
        self.capture('chrome')
        self.playwright.chromium.launch.assert_called_once_with(headless=False,chromium_sandbox=True,channel='chrome')
        saved=json.loads(self.state.read_text())
        self.assertEqual(len(saved['cookies']),1)
        self.assertEqual(saved['origins'],[])
        self.assertEqual(self.state.stat().st_mode & 0o777,0o600)
        self.browser.close.assert_called_once()

    def test_bundled_browser_remains_default_with_sandbox(self):
        self.capture()
        self.playwright.chromium.launch.assert_called_once_with(headless=False,chromium_sandbox=True)

    def test_sandbox_error_is_actionable_and_does_not_disable_it(self):
        self.playwright.chromium.launch.side_effect=BrowserError('No usable sandbox! private diagnostics')
        with self.assertRaisesRegex(ValueError,'login --browser chrome') as error:
            self.capture()
        self.assertNotIn('private diagnostics',str(error.exception))
        self.assertEqual(self.playwright.chromium.launch.call_count,1)
        self.assertFalse(self.state.exists())

    def test_navigation_failure_closes_browser_without_saving(self):
        self.context.new_page.return_value.goto.side_effect=BrowserError('private URL')
        with self.assertRaisesRegex(ValueError,'navigation or session capture failed'):
            self.capture('chrome')
        self.browser.close.assert_called_once()
        self.assertFalse(self.state.exists())

    def test_cli_parses_browser_and_reports_launch_error_without_traceback(self):
        output=StringIO()
        with patch('sys.argv',['hi10','--state',str(self.state),'login','--browser','chrome']),patch('playwright.sync_api.sync_playwright') as factory,redirect_stderr(output):
            factory.return_value.__enter__.return_value=self.playwright
            self.playwright.chromium.launch.side_effect=BrowserError('Executable does not exist: private path')
            self.assertEqual(main(),1)
        self.assertIn('Could not start the chrome login browser',output.getvalue())
        self.assertNotIn('private path',output.getvalue())
        self.assertNotIn('Traceback',output.getvalue())
