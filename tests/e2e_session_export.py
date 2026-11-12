"""Export synthetic HttpOnly cookies from an isolated browser, never a user profile."""
import json
from pathlib import Path
import shutil
import tempfile
from playwright.sync_api import sync_playwright
from hi10_downloader.web import validate_state


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        extension=root/'extension'
        shutil.copytree(Path(__file__).resolve().parents[1]/'browser-extension/hi10-session-export',extension)
        # Only this disposable test copy has a worker, to discover its extension ID.
        manifest=json.loads((extension/'manifest.json').read_text())
        manifest['background']={'service_worker':'fixture-worker.js'}
        (extension/'manifest.json').write_text(json.dumps(manifest))
        (extension/'fixture-worker.js').write_text('chrome.runtime.onInstalled.addListener(() => {});')
        with sync_playwright() as playwright:
            # Trusted local fixture only. Production login sandbox settings are untouched.
            context=playwright.chromium.launch_persistent_context(str(root/'profile'),headless=True,channel='chromium',
                args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}'])
            try:
                worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                extension_id=worker.url.split('/')[2]
                awaitable_requests=[]
                context.on('request',lambda request:awaitable_requests.append(request.url))
                context.add_cookies([
                    {'name':'wordpress_logged_in_fixture','value':'not-a-real-session','domain':'.hi10anime.com','path':'/','httpOnly':True,'secure':True,'sameSite':'Lax'},
                    {'name':'private-other-site','value':'must-not-export','domain':'other.invalid','path':'/','httpOnly':True,'secure':True}])
                page=context.new_page()
                page.goto(f'chrome-extension://{extension_id}/popup.html')
                with page.expect_download() as download_info:
                    page.get_by_role('button',name='Save session.json').click()
                download=download_info.value
                assert download.suggested_filename=='session.json'
                target=root/'fixture-session.json'
                download.save_as(target)
                state=validate_state(json.loads(target.read_text()))
                assert len(state['cookies'])==1
                assert state['cookies'][0]['httpOnly'] is True
                assert state['cookies'][0]['value']=='not-a-real-session'
                assert state['cookies'][0]['expires']==-1
                assert state['origins']==[]
                assert not any(url.startswith(('http://','https://')) for url in awaitable_requests),awaitable_requests
                print('Extension E2E passed: real cookie API exported synthetic HttpOnly session, rejected other-site cookies, downloaded importable JSON, and made no web requests.')
            finally:
                context.close()


if __name__=='__main__':main()
