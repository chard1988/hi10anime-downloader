"""Interactive login browser confined to a single Playwright owner thread."""
from concurrent.futures import Future, TimeoutError
from queue import Queue, Empty, Full
from threading import Thread
import time
import os
from urllib.parse import urlsplit

from .cli import BASE, LIST_URL


def fill_login_fields(page, username, password):
    """Fill credentials without submitting: the user controls the site's login flow."""
    page.locator('#user_login').fill(str(username)[:300])
    page.locator('#user_pass').fill(str(password)[:2000])


class LoginBrowser:
    def __init__(self):
        self.active = False
        self.commands = Queue(maxsize=8)
        self.thread = Thread(target=self._run, daemon=True, name="login-browser")
        self.thread.start()

    def call(self, action, timeout=50, **kwargs):
        future = Future()
        try:
            self.commands.put_nowait((action, kwargs, future))
        except Full:
            raise ValueError('Browser is busy. Wait before sending another command.') from None
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise ValueError("Browser operation timed out. Wait a moment and try again.") from None

    def _run(self):
        playwright = browser = context = page = proxy = None
        last_used = time.monotonic()
        while True:
            try:
                action, args, future = self.commands.get(timeout=5)
            except Empty:
                if browser and time.monotonic() - last_used > 900:
                    browser.close()
                    if proxy:
                        proxy.close(); proxy = None
                    playwright.stop()
                    playwright = browser = context = page = None
                    self.active = False
                continue
            if not future.set_running_or_notify_cancel():
                continue
            try:
                if action != 'screenshot':
                    last_used = time.monotonic()
                if action == "start":
                    if browser:
                        browser.close()
                    if playwright:
                        playwright.stop()
                    playwright = browser = context = page = None
                    self.active = False
                    if proxy:
                        proxy.close(); proxy = None
                    from .browser_proxy import BrowserProxy
                    proxy = BrowserProxy()
                    from playwright.sync_api import sync_playwright
                    playwright = sync_playwright().start()
                    browser = playwright.chromium.launch(headless=True, chromium_sandbox=os.environ.get('HI10_BROWSER_SANDBOX', '1') == '1', proxy=proxy.settings(), args=['--proxy-bypass-list=<-loopback>', '--disable-quic', '--force-webrtc-ip-handling-policy=disable_non_proxied_udp', '--disable-background-networking'])
                    context = browser.new_context(viewport={"width": 1000, "height": 760})
                    # Block private destinations even for subresources/redirects.
                    from .network import public_addresses
                    def guard(route):
                        parts = urlsplit(route.request.url)
                        try:
                            if parts.scheme not in {'https', 'http'}:
                                route.abort(); return
                            public_addresses(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80))
                        except Exception:
                            route.abort(); return
                        route.continue_()
                    context.route('**/*', guard)
                    page = context.new_page()
                    # Keep browser interaction limited to the intended service and login providers.
                    page.set_default_timeout(15000)
                    page.goto(BASE + "/wp-login.php", wait_until="domcontentloaded", timeout=30000)
                    self.active = True
                    result = {"width": 1000, "height": 760}
                elif action == "close":
                    if proxy:
                        proxy.close(); proxy = None
                    if browser:
                        browser.close()
                    if playwright:
                        playwright.stop()
                    playwright = browser = context = page = None
                    self.active = False
                    result = {}
                else:
                    if not page:
                        raise ValueError("Open the login browser first.")
                    host = urlsplit(page.url).hostname or ""
                    if host != "hi10anime.com":
                        raise ValueError("The login browser left Hi10. Reopen it to continue.")
                    if action == "screenshot":
                        result = page.screenshot(type="png")
                    elif action == "click":
                        page.mouse.click(max(0, min(999, float(args['x']))), max(0, min(759, float(args['y']))))
                        result = {}
                    elif action == "text":
                        page.keyboard.insert_text(str(args["text"])[:2000])
                        result = {}
                    elif action == "key":
                        key = args['key']
                        if key not in {"Tab", "Enter", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Control+A", "Escape", "Space"}:
                            raise ValueError("Unsupported key")
                        page.keyboard.press(key)
                        result = {}
                    elif action == "scroll":
                        page.mouse.wheel(0, max(-700, min(700, int(args["delta"]))))
                        result = {}
                    elif action == "credentials":
                        fill_login_fields(page, args['username'], args['password'])
                        result = {}
                    elif action == "capture":
                        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30000)
                        page.locator('#urlContainer').wait_for(timeout=15000)
                        result = context.storage_state()
                    else:
                        raise ValueError("Unknown browser action")
                future.set_result(result)
            except Exception:
                if action == 'start':
                    if browser:
                        browser.close()
                    if playwright:
                        playwright.stop()
                    if proxy:
                        proxy.close()
                    playwright = browser = context = page = proxy = None
                    self.active = False
                future.set_exception(ValueError("Login browser could not complete this action. Check the browser image; finish any CAPTCHA, then save the session. Chromium must be installed on the server."))
