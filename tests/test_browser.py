import unittest
from unittest.mock import MagicMock, patch

from hi10_downloader.browser import LoginBrowser
from hi10_downloader.cli import BASE


class LoginBrowserTests(unittest.TestCase):
    def test_credentials_fill_fields_but_never_submit_login(self):
        fields = {'#user_login': MagicMock(), '#user_pass': MagicMock()}
        page = MagicMock()
        page.url = BASE + '/wp-login.php'
        # Accessing a submit button would fail this test.
        page.locator.side_effect = lambda selector: fields[selector]
        driver = MagicMock()
        driver.chromium.launch.return_value.new_context.return_value.new_page.return_value = page
        with patch('playwright.sync_api.sync_playwright') as factory:
            factory.return_value.start.return_value = driver
            browser = LoginBrowser()
            try:
                browser.call('start')
                browser.call('credentials', username='test-user', password='test-password')
                fields['#user_login'].fill.assert_called_once_with('test-user')
                fields['#user_pass'].fill.assert_called_once_with('test-password')
                self.assertFalse(page.mouse.click.called)
                self.assertFalse(page.keyboard.press.called)
                page.locator.assert_any_call('#user_login')
                page.locator.assert_any_call('#user_pass')
                self.assertEqual(page.locator.call_count, 2)
            finally:
                browser.call('close')
