"""Real React browser checks with disposable state; no website downloads."""
from pathlib import Path
import os
import tempfile
from threading import Thread
import time

from playwright.sync_api import sync_playwright, expect
from waitress.server import create_server
from hi10_downloader.web import Application, ident
from hi10_downloader.server import application
from hi10_downloader.parsing import parse_project
from hi10_downloader.cli import save_json


def main():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        screenshots=Path(os.environ.get('HI10_E2E_ARTIFACTS',str(root/'screenshots')))
        screenshots.mkdir(parents=True,exist_ok=True)
        app=Application(root/'config',root/'output',password='test-password')
        url='https://hi10anime.com/e2e'
        project=parse_project('<h1>E2E project</h1><a href="https://mirror.invalid/01_1080p.mkv">1080p</a>',url)
        project.update(id=ident(url),scanned=True,choices={})
        app.catalog['projects']=[project];app.save_catalog()
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
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.set_default_timeout(15000)
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda message:errors.append(message.text) if message.type=='error' and 'Content Security Policy' in message.text else None)
                def combo(label,value):
                    field=page.get_by_role('combobox',name=label,exact=True)
                    field.click();field.fill(value)
                    page.get_by_role('option',name=value,exact=True).click()
                try:
                    page.goto(address)
                    page.get_by_label('Web interface password',exact=True).fill('test-password')
                    page.get_by_role('button',name='Unlock library',exact=True).click()
                    page.get_by_role('heading',name='Project library',exact=True).wait_for()
                    combo('Theme','Dark')
                    assert page.locator('html').evaluate("e=>e.classList.contains('dark')")
                    page.screenshot(path=str(screenshots/'react-projects-dark.png'),full_page=True)
                    page.reload();page.get_by_role('heading',name='Project library',exact=True).wait_for()
                    assert page.locator('html').evaluate("e=>e.classList.contains('dark')")
                    combo('Theme','Light')
                    assert not page.locator('html').evaluate("e=>e.classList.contains('dark')")
                    page.screenshot(path=str(screenshots/'react-projects-light.png'),full_page=True)
                    combo('Theme','System')
                    page.emulate_media(color_scheme='dark')
                    page.locator('html.dark').wait_for(state='attached')
                    page.emulate_media(color_scheme='light')
                    page.locator('html.dark').wait_for(state='detached')
                    print('React fixture: themes passed',flush=True)
                    page.get_by_role('button',name='Monitor project E2E project',exact=True).click()
                    page.get_by_role('button',name='Unmonitor project E2E project',exact=True).wait_for()
                    page.get_by_role('button',name='Monitoring · 1',exact=True).click()
                    sheet=page.get_by_role('dialog',name='Project monitoring',exact=True)
                    sheet.get_by_label('Check interval (minutes)',exact=True).fill('30')
                    sheet.get_by_role('checkbox',name='Pause automatic checks and downloads',exact=True).check()
                    sheet.get_by_role('button',name='Save settings',exact=True).click()
                    page.wait_for_timeout(300)
                    assert app.monitoring.state['paused'] and app.monitoring.state['interval_minutes']==30
                    page.keyboard.press('Escape');sheet.wait_for(state='hidden')
                    page.get_by_role('button',name='Review files for E2E project',exact=True).click()
                    page.get_by_role('dialog',name='E2E project',exact=True).wait_for()
                    page.get_by_role('button',name='Save choices',exact=True).click()
                    page.get_by_role('dialog',name='E2E project',exact=True).wait_for(state='hidden')
                    print('React fixture: navigating to downloads',flush=True)
                    page.get_by_role('button',name='Downloads',exact=False).first.click()
                    page.get_by_role('heading',name='Downloads',exact=True).wait_for()
                    page.get_by_role('button',name='E2E project',exact=True).click()
                    page.get_by_role('button',name='episode-000.mkv',exact=True).wait_for()
                    assert page.get_by_role('button',name='View download link',exact=True).count()==25
                    for count in (50,25):
                        size=page.get_by_role('combobox',name='Rows per page',exact=True).first
                        size.click();size.fill(f'{count} rows')
                        page.get_by_role('option',name=f'{count} rows',exact=True).click()
                        expect(page.get_by_role('button',name='View download link',exact=True)).to_have_count(count)
                    print('React fixture: row-count comboboxes passed',flush=True)
                    page.get_by_role('button',name='Close toast',exact=True).evaluate_all('(buttons)=>buttons.forEach(button=>button.click())')
                    expect(page.get_by_role('button',name='Close toast',exact=True)).to_have_count(0)
                    page.get_by_role('button',name='Next page',exact=True).first.click()
                    page.get_by_role('button',name='episode-025.mkv',exact=True).wait_for()
                    page.get_by_role('button',name='episode-025.mkv',exact=True).click()
                    page.get_by_text('Failure reason',exact=True).wait_for()
                    page.get_by_text('HTTP 403 Forbidden',exact=True).wait_for()
                    page.get_by_role('button',name='View download link',exact=True).first.click()
                    page.get_by_label('File URL',exact=True).fill('https://mirror.invalid/repaired.mkv')
                    page.get_by_role('button',name='Save URL',exact=True).click()
                    page.get_by_role('dialog',name='Download link',exact=True).wait_for(state='hidden')
                    assert app.items[25]['file']['url'].endswith('/repaired.mkv')
                    print('React fixture: URL editing passed',flush=True)
                    combo('Queue status','Failed')
                    page.get_by_role('button',name='E2E project',exact=True).click()
                    page.get_by_role('button',name='episode-001.mkv',exact=True).wait_for()
                    with page.expect_response(lambda r:'/api/state?' in r.url and 'download_search=episode-003' in r.url):
                        page.get_by_role('textbox',name='Search queue',exact=True).fill('episode-003')
                    expect(page.get_by_role('button',name='E2E project',exact=True)).to_have_attribute('aria-expanded','false')
                    page.get_by_role('button',name='E2E project',exact=True).click()
                    page.get_by_role('button',name='episode-003.mkv',exact=True).wait_for()
                    assert page.get_by_role('button',name='View download link',exact=True).count()==1
                    page.get_by_role('button',name='Settings',exact=True).click()
                    page.get_by_label('Start at a later date and time',exact=True).wait_for()
                    page.get_by_label('Download speed limit (kbps)',exact=True).fill('8000')
                    page.get_by_label('Maximum parallel downloads',exact=True).fill('2')
                    page.get_by_role('button',name='Save transfer settings',exact=True).click()
                    expect(page.get_by_role('button',name='Save transfer settings',exact=True)).to_be_enabled()
                    assert app.transfer_settings['speed_limit_kbps']==8000
                    assert app.transfer_settings['parallel_downloads']==2

                    page.keyboard.press('Escape')
                    print('React fixture: queue search and settings passed',flush=True)
                    page.set_viewport_size({'width':390,'height':844})
                    page.screenshot(path=str(screenshots/'react-downloads-mobile.png'),full_page=True)
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
                    page.get_by_role('button',name='Toggle Sidebar',exact=True).click()
                    page.get_by_role('button',name='Project library',exact=False).first.click()
                    page.get_by_role('heading',name='Project library',exact=True).wait_for()
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Library mobile overflow'
                    page.set_viewport_size({'width':1440,'height':1000})
                    page.get_by_role('button',name='Downloads',exact=False).first.click()
                    page.get_by_role('checkbox',name='Select project E2E project for exclusion',exact=True).check()
                    page.get_by_role('button',name='Exclude selected projects',exact=True).click()
                    page.get_by_role('checkbox',name='Select project E2E project for exclusion',exact=True).wait_for(state='hidden')
                    assert all(e['status']=='complete' for e in app.items)
                    page.reload();page.get_by_role('heading',name='Project library',exact=True).wait_for()
                    assert not page.get_by_label('Web interface password',exact=True).count()
                    page.get_by_role('button',name='Lock interface',exact=True).click()
                    page.get_by_label('Web interface password',exact=True).wait_for()
                    assert not errors,errors
                    page.screenshot(path=str(screenshots/'react-login.png'),full_page=True)
                except Exception:
                    try:
                        page.screenshot(path=str(screenshots/'react-error.png'),full_page=True,timeout=5000)
                        print(page.locator('body').inner_text(timeout=3000)[:7000],flush=True)
                    except Exception:
                        print('React fixture: could not capture failed page',flush=True)
                    print('Browser errors:',errors,flush=True)
                    raise
                browser.close()
                print('React E2E passed: unlock/lock, persisted light/dark/system themes, monitoring, details, grouped pagination, errors, URL editing, status/search, Sheets, mobile sidebar and exclusions.')
        finally:
            app.close(timeout=2);server.close();thread.join(timeout=2)

if __name__=='__main__':main()
