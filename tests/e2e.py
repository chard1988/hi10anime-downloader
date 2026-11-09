"""Real browser checks using private disposable fixtures; no website downloads."""
from pathlib import Path
import tempfile
from threading import Thread
import time

from playwright.sync_api import sync_playwright
from waitress.server import create_server
from hi10_downloader.web import Application, ident
from hi10_downloader.server import application
from hi10_downloader.parsing import parse_project
from hi10_downloader.cli import save_json


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        app=Application(root/'config',root/'output',password='test-password')
        url='https://hi10anime.com/e2e'
        project=parse_project('<h1>E2E project</h1><a href="https://mirror.invalid/01_1080p.mkv">1080p</a>',url)
        project.update(id=ident(url),scanned=True,choices={})
        app.catalog['projects']=[project]
        app.save_catalog()
        app.connected=True;app.last_verified=time.time();app.session_status='connected'
        save_json(app.state_path,{'cookies':[]})
        app.items=[{'id':str(i),'project_id':project['id'],'project':project['title'],'project_url':url,'folder':project['folder'],'filename':f'episode-{i:03}.mkv','file':{'url':f'https://mirror.invalid/{i}.mkv'},'status':'failed' if i%2 else 'complete','bytes':0,'total':None,'message':'HTTP 403 Forbidden'} for i in range(101)]
        app.save_queue()
        server=create_server(application(app),host='127.0.0.1',port=0)
        thread=Thread(target=server.run,daemon=True);thread.start()
        address=f'http://127.0.0.1:{server.effective_port}'
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                page=browser.new_page()
                page.goto(address)
                page.locator('#web-password').fill('test-password');page.locator('#unlock-form button').click()
                page.locator('[data-view="downloads"]').click()
                group=page.locator('.queue-project-group')
                group.locator('summary strong').click()
                page.locator('.download-item').first.wait_for()
                assert page.locator('.download-item').count()==50
                group.get_by_role('button',name='Next items for '+project['title'],exact=True).click()
                page.get_by_text('episode-050.mkv',exact=True).wait_for()
                assert page.locator('.download-item').count()==50
                page.get_by_text('episode-050.mkv',exact=True).click()
                page.locator('#queue-details-50').get_by_text('Destination',exact=True).wait_for()
                page.locator('#download-filter').select_option('failed')
                page.get_by_text('episode-001.mkv',exact=True).wait_for()
                assert page.locator('.download-item').count()==50
                page.get_by_role('button',name='View download link',exact=True).first.click()
                page.locator('#download-link-value').fill('https://mirror.invalid/repaired.mkv')
                page.locator('#save-download-link').click()
                page.locator('#download-link-dialog').wait_for(state='hidden')
                assert app.items[1]['file']['url'].endswith('/repaired.mkv')
                ids=page.locator('[id]').evaluate_all('(elements) => elements.map(element => element.id)')
                assert len(ids)==len(set(ids)), 'Duplicate DOM IDs'
                page.locator('#download-settings').focus()
                page.keyboard.press('Enter')
                page.locator('#schedule-time').wait_for(state='visible')
                page.keyboard.press('Escape')
                page.locator('#download-settings-dialog').wait_for(state='hidden')
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), page.locator('body *').evaluate_all('(elements) => elements.filter(e => e.getBoundingClientRect().right > innerWidth + 1).map(e => ({tag:e.tagName,id:e.id,cls:e.className,width:e.getBoundingClientRect().width})).slice(0,15)')
                page.set_viewport_size({'width':1280,'height':720})
                group.get_by_role('checkbox',name='Select project '+project['title']+' for exclusion',exact=True).check()
                page.locator('#exclude-queue-projects').click()
                page.locator('.queue-project-group').wait_for(state='hidden')
                assert all(e['status']=='complete' for e in app.items)
                page.reload()
                page.locator('#app').wait_for(state='visible')
                assert page.locator('#unlock').is_hidden()
                assert not page.locator('#download-job-bar').count()
                browser.close()
                print('Browser E2E: login, grouped server pagination, details, filters, URL edit, settings, exclusion, persistent session passed.')
        finally:
            app.close(timeout=2);server.close();thread.join(timeout=2)


if __name__=='__main__':
    main()
