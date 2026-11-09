"""Host compatibility gate: no credentials or external website access."""
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True,chromium_sandbox=True)
    try:
        page=browser.new_page()
        page.set_content('<title>Sandbox fixture</title>')
        assert page.title()=='Sandbox fixture'
        print('Sandboxed Chromium launched and rendered as the container user.')
    finally:
        browser.close()
