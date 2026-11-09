"""Local web UI with independent scan and download jobs for the unRAID service."""
import argparse
from copy import deepcopy
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import re
from pathlib import Path
import secrets
import signal
import logging
import uuid
from threading import Event, RLock, Thread
import time
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
import httpx

from .browser import LoginBrowser
from .cli import LIST_URL, child_path, file_folder, digest, download_one, clear_receipt, fetch_page, make_client, save_json
from .parsing import parse_project, project_links, select_files
from .sources import load_project_list
from .runtime import RuntimeState, ACCESS_DAYS
from .storage import load_json, transaction, recover_transaction, delete_file
from . import schema, __version__
from .lifecycle import ServiceLocks
from .routes import Routes
from .retries import retry_delay


class Cancelled(Exception):
    pass


def download_error(exc):
    """Describe the cause without leaking signed URLs, cookies, or headers."""
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        return f'HTTP {response.status_code} {response.reason_phrase}'.strip()
    if isinstance(exc, httpx.TimeoutException):
        return f'{type(exc).__name__}: the network operation timed out.'
    if isinstance(exc, httpx.ConnectError):
        detail = re.sub(r'https?://[^\s]+', '[private URL]', str(exc))[:400]
        return f'ConnectError: {detail or "could not connect to the download server"}'
    if isinstance(exc, httpx.HTTPError):
        return f'{type(exc).__name__}: download connection or HTTP protocol failed.'
    if isinstance(exc, OSError):
        return f'{type(exc).__name__}: {os.strerror(exc.errno) if exc.errno else "filesystem operation failed"}'
    if isinstance(exc, ValueError):
        return re.sub(r'https?://[^\s]+', '[private URL]', str(exc))[:500]
    return f'{type(exc).__name__}: unexpected download failure.'


def ident(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def validate_state(data):
    if not isinstance(data, dict) or not isinstance(data.get('cookies'), list):
        raise ValueError('Choose a Playwright storage-state JSON file with a cookies array.')
    cookies = []
    for cookie in data['cookies']:
        if not isinstance(cookie, dict) or not all(isinstance(cookie.get(k), str) for k in ('name', 'value', 'domain', 'path')):
            raise ValueError('The session contains an invalid cookie.')
        if cookie['domain'].lstrip('.') == 'hi10anime.com':
            cookies.append(cookie)
    if not cookies:
        raise ValueError('No Hi10 cookies found in this session.')
    result = {'cookies': cookies, 'origins': []}
    if not schema.session(result):
        raise ValueError('Invalid session cookie fields or expiration.')
    return result


class Application(RuntimeState):
    def __init__(self, config: Path, output: Path, password=None):
        self.config, self.output = config, output
        config.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=True, exist_ok=True)
        recover_transaction(config, output)
        format_path = config / 'state-format.json'
        if format_path.exists():
            state_format = load_json(format_path, lambda d: isinstance(d, dict) and type(d.get('version')) is int)
            if state_format.get('version') not in {1, 2, 3}:
                raise ValueError('Unsupported appdata version. Use a compatible image or restore a backup.')
        save_json(format_path, {'version': 3})
        self.state_path = config / 'session.json'
        self.catalog_path = config / 'library.json'
        self.lock = RLock()
        self.cancel = Event()
        self.download_cancel = Event()
        self.workers = []
        self.browser = None
        self.connected = False
        self.session_message = 'Saved session found. Verify it before scanning.' if self.state_path.exists() else 'Connect your Hi10 account to load the library.'
        self.catalog = load_json(self.catalog_path, schema.catalog) if self.catalog_path.exists() else {'projects': [], 'default_quality': 0}
        self.jobs_path = config / 'downloads.json'
        self.items = load_json(self.jobs_path, schema.queue) if self.jobs_path.exists() else []
        for item in self.items:
            if item['status'] == 'downloading':
                item['status'] = 'interrupted'
                item['message'] = 'Server restarted. Click Start downloads to continue.'
        self.job = {'kind': '', 'running': False, 'done': 0, 'total': 0, 'message': 'Ready', 'error': None}
        self.download_job = dict(self.job)
        password_path = config / 'web-password.json'
        if password:
            self.password = password
        else:
            if not password_path.exists():
                save_json(password_path, {'password': secrets.token_urlsafe(18)})
            self.password = load_json(password_path, lambda d: isinstance(d, dict) and isinstance(d.get('password'), str))['password']
            print('Web interface password is stored in the private appdata web-password.json file.', flush=True)

        self.init_runtime()

    def save_catalog(self, project=None):
        if project is not None:
            self.store_project(project)
            return
        # Refresh/import may still contain full legacy projects. Store each only once.
        for entry in list(self.catalog['projects']):
            if 'variants' in entry and entry.get('scanned'):
                self.store_project(entry)
        self.write_index()
        self.touch_library()

    def start_job(self, kind, function):
        with self.lock:
            if self.shutdown.is_set():
                raise ValueError('The service is shutting down.')
            downloading = kind == 'download'
            current = self.download_job if downloading else self.job
            if current['running']:
                raise ValueError('Another download batch is running.' if downloading else 'Another library operation is running. Wait or stop it first.')
            other = self.job if downloading else self.download_job
            if other['running'] and (self.job['kind'] != 'scan' if downloading else kind != 'scan'):
                raise ValueError('Wait for the current operation to finish. Only scans and downloads can run together.')
            cancel = self.download_cancel if downloading else self.cancel
            cancel.clear()
            job = {'id': uuid.uuid4().hex, 'kind': kind, 'running': True, 'done': 0, 'total': 0, 'message': 'Starting…', 'error': None, 'project_id': None, 'project_ids': []}
            if downloading:
                self.download_job = job
            else:
                self.job = job
            def run():
                logging.getLogger(__name__).info('job_started job_id=%s kind=%s', job['id'], kind)
                try:
                    function()
                except Cancelled:
                    with self.lock:
                        job['message'] = 'Stopped'
                except Exception as exc:
                    with self.lock:
                        # Avoid exposing signed URLs, cookie values, or internal tracebacks.
                        job['error'] = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) and 'http' not in str(exc) else 'Operation failed. Check connectivity, saved session, and folder permissions.'
                        job['message'] = 'Needs attention'
                finally:
                    with self.lock:
                        try:
                            if kind == 'scan':
                                self.write_index()
                        finally:
                            job['running'] = False
                            logging.getLogger(__name__).info('job_finished job_id=%s kind=%s failed=%s', job['id'], kind, bool(job['error']))
                            self.scheduler_wake.set()
            thread = Thread(target=run, daemon=True, name=f'hi10-{kind}')
            self.workers = [t for t in self.workers if t.is_alive()] + [thread]
            thread.start()

    def idle(self, include_download=True):
        if self.job['running'] or (include_download and self.download_job['running']):
            raise ValueError('Wait for the current operation to finish before changing the session or selections.')

    def selected(self, project, include_disabled=False):
        project = self.load_project(project)
        variants = project.get('variants', [])
        if not include_disabled and project.get('sections') and 'selected_sections' in project:
            variants = [v for v in variants if v.get('section_id') in project['selected_sections']]
        return select_files(variants, project.get('preferred', self.catalog.get('default_quality', 0)),
                            project.get('choices', {}), project.get('section_qualities', {}))

    def verify(self, force=False):
        with self.lock:
            if not force and self.connected and time.time() - self.last_verified < 300:
                return None
            self.session_status = 'checking'
            self.session_message = 'Checking your saved Hi10 session…'
        try:
            with make_client(self.state_path) as client:
                html = fetch_page(client, LIST_URL)
                project_links(html, LIST_URL)
        except (httpx.TimeoutException, httpx.TransportError):
            with self.lock:
                self.session_status = 'error'
                self.session_message = 'Could not reach Hi10. Your saved session is retained; retry verification.'
            raise ValueError(self.session_message) from None
        except Exception:
            with self.lock:
                self.connected = False
                self.session_status = 'expired' if self.state_path.exists() else 'missing'
                self.session_message = 'Saved session could not access Hi10. It is retained; verify again or sign in if expired.'
            raise ValueError(self.session_message) from None
        with self.lock:
            self.connected = True
            self.last_verified = time.time()
            self.session_status = 'connected'
            self.session_message = 'Session verified and saved on the server.'
            save_json(self.session_info_path, {'verified_at': self.last_verified, 'fingerprint': self.session_fingerprint()})
            if self.job['kind'] in {'session', 'restore'}:
                self.job['message'] = 'Session verified'
        return html

    def refresh(self):
        verified_html = self.verify()
        with make_client(self.state_path) as client:
            html = load_project_list(client, html=verified_html)
        urls = project_links(html, LIST_URL)
        urls = [url for url in urls if urlsplit(url).hostname == 'hi10anime.com' and urlsplit(url).scheme == 'https']
        soup = BeautifulSoup(html, 'html.parser')
        from urllib.parse import urljoin
        labels = {urljoin(LIST_URL, a['href']).split('#')[0]: a.get_text(' ', strip=True) for a in soup.select('#urlContainer a[href]')}
        with self.lock:
            old = {p['url']: p for p in self.catalog['projects']}
            self.catalog['projects'] = [old.get(url, {'id': ident(url), 'url': url, 'title': labels.get(url) or urlsplit(url).path.strip('/'), 'scanned': False, 'variants': [], 'choices': {}}) for url in urls]
            self.save_catalog()
            self.job.update(done=len(urls), total=len(urls), message=f'Loaded {len(urls)} projects. Scan pages to detect files.')

    def scan_projects(self, ids):
        self.verify()
        with self.lock:
            targets = [p['id'] for p in self.catalog['projects'] if p['id'] in ids and p['id'] not in self.catalog.get('excluded_ids', [])]
            self.job.update(total=len(targets), project_ids=targets)
        with make_client(self.state_path) as client:
            failures = 0
            for index, project_id in enumerate(targets):
                with self.lock:
                    project = self.get_project(project_id)
                if self.cancel.is_set():
                    raise Cancelled()
                with self.lock:
                    self.job.update(message=f'Scanning {project["title"]}', project_id=project_id)
                try:
                    parsed = parse_project(fetch_page(client, project['url']), project['url'])
                    error = None if parsed['variants'] else 'No direct MKV links detected. This page may need a host-specific resolver.'
                    with self.lock:
                        project.update({k: parsed[k] for k in ('title', 'folder', 'variants', 'candidate_count', 'sections')})
                        project.update(scanned=True, error=error)
                        if 'selected_sections' in project:
                            valid = {s['id'] for s in project['sections']}
                            project['selected_sections'] = [sid for sid in project['selected_sections'] if sid in valid]
                            project['section_qualities'] = {sid: q for sid, q in project.get('section_qualities', {}).items() if sid in valid}
                except Exception:
                    with self.lock:
                        project['error'] = 'Could not scan this page. Check access and retry.'
                with self.lock:
                    self.job['done'] = index + 1
                    failures += bool(project.get('error'))
                    self.save_catalog(project)
                if self.cancel.wait(1):
                    raise Cancelled()
        with self.lock:
            self.write_index()
            self.job.update(message=f'Scan finished · {failures} projects need attention' if failures else 'Scan finished. Review qualities and queue your projects.', project_id=None)

    def manifest(self):
        return self.cached_manifest()

    def is_complete(self, project, item, manifest):
        target = child_path(file_folder(self.output, project['folder'], item), item['filename'])
        key = str(target.relative_to(self.output))
        record = manifest.get(key)
        return bool(record and record['url'] == item['url'] and target.is_file() and target.stat().st_size == record['size'])

    def summary_for(self, project):
        project_id = project['id']
        if project_id in self._summaries:
            return self._summaries[project_id]
        project = self.load_project(project)
        files = self.selected(project) if project.get('scanned') else []
        complete = sum(self.is_complete(project, item, self._manifest_cache) for item in files)
        summary = {k: project.get(k) for k in ('id', 'title', 'url', 'scanned', 'error')} | {
            'excluded': project_id in self.catalog.get('excluded_ids', []),
            'count': len(files) if project.get('scanned') else None,
            'remaining': len(files) - complete if project.get('scanned') else None,
            'qualities': sorted({v['resolution'] for v in project.get('variants', [])}, reverse=True),
            'preferred': project.get('preferred', self.catalog.get('default_quality', 0)),
            'complete': complete, 'section_count': len(project.get('sections', [])),
            'selected_section_count': len(project.get('selected_sections', project.get('sections', [])))}
        self._summaries[project_id] = summary
        return summary

    def snapshot(self, known_library_version=None, download_page=0, download_filter="all", grouped=False, group_pages=None):
        with self.lock:
            self.manifest()  # One cheap manifest stat; no per-file work on unchanged polls.
            if self._library_payload is None:
                projects = []
                for entry in self.catalog['projects']:
                    if self._restoring and entry['id'] not in self._summaries:
                        projects.append({k: entry.get(k) for k in ('id', 'title', 'url', 'scanned', 'error')} | {
                            'count': None, 'remaining': None, 'complete': 0, 'qualities': [],
                            'preferred': self.catalog.get('default_quality', 0), 'section_count': 0,
                            'selected_section_count': 0, 'restoring': True})
                    else:
                        projects.append(self.summary_for(entry))
                self._library_payload = projects
            if download_filter not in {'all', 'queued', 'downloading', 'complete', 'failed', 'interrupted'}:
                raise ValueError('Choose a valid queue filter.')
            cache_key = (download_filter, id(self.items), self.library_version)
            cached = self._queue_groups_cache.get(cache_key)
            if cached is None:
                filtered = [e for e in self.items if download_filter == 'all' or e['status'] == download_filter]
                groups = {}
                for entry in filtered:
                    group_id = entry.get('project_id') or ident(entry.get('project_url') or entry.get('project', 'Unknown project'))
                    if group_id not in groups:
                        title = entry.get('project', 'Unknown project').split(' / ')[0]
                        try:
                            title = self.catalog['projects'][self.project_position(group_id)]['title']
                        except ValueError:
                            pass
                        groups[group_id] = {'id': group_id, 'title': title, 'items': []}
                    groups[group_id]['items'].append(entry)
                self._queue_groups_cache = {k:v for k,v in self._queue_groups_cache.items() if k[1:] == cache_key[1:]}
                for group in groups.values():
                    group['failed'] = sum(e['status'] == 'failed' for e in group['items'])
                    group['complete'] = sum(e['status'] == 'complete' for e in group['items'])
                self._queue_groups_cache[cache_key] = (filtered, groups)
            else:
                filtered, groups = cached
            page_total = max(1, (len(groups) + 4) // 5) if grouped else max(1, (len(filtered) + 49) // 50)
            page = max(0, min(download_page, page_total - 1))
            page_groups = list(groups.values())[page * 5:(page + 1) * 5] if grouped else []
            group_pages = group_pages or {}
            if not isinstance(group_pages, dict) or len(group_pages) > 5 or any(not isinstance(k, str) or type(v) is not int or v < 0 for k,v in group_pages.items()):
                raise ValueError('Invalid project item pages.')
            pages = {g['id']: min(group_pages.get(g['id'], 0), max(0,(len(g['items'])-1)//50)) for g in page_groups}
            page_entries = [e for g in page_groups if g['id'] in group_pages for e in g['items'][pages[g['id']]*50:(pages[g['id']]+1)*50]] if grouped else filtered[page * 50:(page + 1) * 50]
            downloads = []
            for entry in page_entries:
                public = {k: v for k, v in entry.items() if k in {'id', 'project', 'filename', 'status', 'bytes', 'total', 'message'}}
                public['group_id'] = entry.get('project_id') or ident(entry.get('project_url') or entry.get('project', 'Unknown project'))
                if entry.get('folder') and entry.get('filename'):
                    public['destination'] = str(self.output.absolute() / entry['folder'] / entry.get('file', {}).get('subfolder', '') / entry['filename'])
                downloads.append(public)
            public_groups = [{'id': g['id'], 'title': g['title'], 'count': len(g['items']),
                              'loaded': g['id'] in group_pages, 'page': pages[g['id']],
                              'failed': g['failed'], 'complete': g['complete']} for g in page_groups]
            unchanged = known_library_version == self.library_version
            delta = (known_library_version is not None and not unchanged and known_library_version >= self._full_revision
                     and self._changes and known_library_version >= self._changes[0][0] - 1)
            changed_ids = {pid for version, pid in self._changes if version > (known_library_version or 0)} if delta else set()
            updates = [self._summaries[pid] for pid in changed_ids if pid in self._summaries]
            public_job = dict(self.job)
            public_job['project_ids'] = self.job.get('project_ids', [])[:1]
            return {'projects': None if unchanged or delta else self._library_payload, 'project_updates': updates,
                    'app_version': __version__, 'library_version': self.library_version, 'job': public_job,
                    'download_job': dict(self.download_job), 'downloads': downloads,
                    'download_groups': public_groups, 'download_page_total': page_total,
                    'download_filtered_total': len(filtered), 'download_filter': download_filter,
                    'download_page': page, 'download_total': len(self.items), 'pending_count': self.pending_count(),
                    'schedule': dict(self.schedule), 'browser_active': bool(self.browser and self.browser.active),
                    'session': {'saved': self.state_path.exists(), 'connected': self.connected,
                                'status': self.session_status, 'message': self.session_message},
                    'default_quality': self.catalog.get('default_quality', 0), 'output': str(self.output)}

    def get_project(self, project_id):
        return self.load_project(self.catalog['projects'][self.project_position(project_id)])

    def details(self, project_id):
        with self.lock:
            p = self.get_project(project_id)
            selected = {f['key']: f for f in self.selected(p, include_disabled=True)}
            groups = {}
            for variant in p['variants']:
                groups.setdefault(variant['key'], {'key': variant['key'], 'filename': selected[variant['key']]['filename'], 'qualities': set(), 'selected': selected[variant['key']]['resolution'], 'section_id': variant.get('section_id')})['qualities'].add(variant['resolution'])
            sections = []
            for section in p.get('sections', []):
                section_files = [f for f in selected.values() if f.get('section_id') == section['id']]
                sections.append(section | {'count': len(section_files),
                    'enabled': section['id'] in p.get('selected_sections', [s['id'] for s in p.get('sections', [])]),
                    'qualities': sorted({v['resolution'] for v in p['variants'] if v.get('section_id') == section['id']}, reverse=True),
                    'preferred': p.get('section_qualities', {}).get(section['id'], 0)})
            return {'id': p['id'], 'title': p['title'], 'sections': sections, 'files': [g | {'qualities': sorted(g['qualities'], reverse=True)} for g in groups.values()], 'choices': p.get('choices', {})}

    def queue(self, ids):
        with self.lock:
            self.idle()
            batch = []
            for project_id in dict.fromkeys(ids):
                if project_id in self.catalog.get('excluded_ids', []):
                    continue
                p = self.get_project(project_id)
                if not p.get('scanned') or not p['variants']:
                    raise ValueError('Scan all selected projects and detect files before queuing them.')
                for item in self.selected(p):
                    entry = {'project': p['title'] + (' / ' + item['section_title'] if item.get('section_title') else ''),
                             'project_id': project_id, 'project_url': p['url'], 'folder': p['folder'], 'file': item,
                             'filename': item['filename'], 'status': 'queued', 'bytes': 0, 'total': None, 'message': ''}
                    entry['id'] = self.entry_id(entry)
                    batch.append(entry)
                    if len(batch) + len(self.items) > int(os.environ.get('HI10_MAX_QUEUE_ITEMS', '50000')):
                        raise ValueError('Queue item limit reached. Clear completed entries before adding more.')
            if not batch:
                raise ValueError('Choose at least one scanned project with downloads.')
            existing = {entry['id']: entry for entry in self.items}
            added = 0
            for entry in batch:
                previous = existing.get(entry['id'])
                if previous is None:
                    self.items.append(entry)
                    existing[entry['id']] = entry
                    added += 1
                elif previous['status'] != 'complete':
                    override = previous.get('url_override')
                    previous.update(entry)  # Refresh links without adding duplicates.
                    if override:
                        previous['file'] = dict(previous['file'], url=override)
                        previous['url_override'] = override
            self.save_queue()
            return {'added': added, 'pending': self.pending_count()}

    def start_downloads(self, entry_ids=None, source='all'):
        with self.lock:
            if self.shutdown.is_set():
                raise ValueError('The service is shutting down.')
            if self.download_job['running'] or (self.job['running'] and self.job['kind'] != 'scan'):
                raise ValueError('A download batch or session operation is already running.')
            if not self.pending_count():
                raise ValueError('The queue has no pending files.')
            if not self.state_path.exists():
                raise ValueError('Save or import a Hi10 session first.')
            targets = [entry for entry in self.items if entry['status'] in {'queued', 'interrupted', 'failed'}
                       and entry.get('project_id') not in self.catalog.get('excluded_ids', [])
                       and (entry_ids is None or entry.get('id') in entry_ids)]
            if not targets:
                raise ValueError('No eligible pending files selected.')
            for entry in targets:
                entry.update(status='queued', bytes=0, total=None, message='')
            self.cancel_schedule()
            self.save_queue()
            def run():
                self.verify()
                self.run_downloads(targets)
            self.start_job('download', run)
            self.download_job.update(source=source, total=len(targets))

    def run_downloads(self, targets=None):
        targets = targets if targets is not None else self.items
        manifest = self.manifest()
        with self.lock:
            self.download_job['total'] = len(targets)
        try:
            with make_client(self.state_path) as client:
                for index, entry in enumerate(targets):
                    if self.download_cancel.is_set():
                        raise Cancelled()
                    item = entry.get('file', {})
                    def progress(size, total):
                        if self.download_cancel.is_set():
                            raise Cancelled()
                        with self.lock:
                            entry.update(bytes=size, total=total)
                    with self.lock:
                        entry['status'] = 'downloading'
                        self._queue_groups_cache.clear()
                        self.download_job['message'] = entry['filename']
                    attempts = 0
                    try:
                        folder = file_folder(self.output, entry['folder'], item)
                        folder.mkdir(parents=True, exist_ok=True)
                        target = child_path(folder, item['filename'])
                        key = str(target.relative_to(self.output))
                        if target.exists():
                            record = manifest.get(key)
                            receipt = target.with_name(target.name + '.receipt.json')
                            if not record and receipt.exists():
                                record = load_json(receipt)
                            if record and record['url'] == item['url'] and target.stat().st_size == record['size'] and digest(target) == record['sha256']:
                                manifest[key] = record
                                self.save_manifest(manifest, entry.get('project_id') or ident(entry['project_url']))
                                clear_receipt(target)
                                with self.lock:
                                    entry.update(status='complete', bytes=record['size'], total=record['size'], message='Verified existing file')
                            else:
                                raise ValueError('An untracked or changed file exists. Move it before retrying.')
                        else:
                            for attempt in range(3):
                                attempts = attempt + 1
                                try:
                                    record = download_one(client, item, entry['project_url'], target, progress=progress)
                                    manifest[key] = record
                                    self.save_manifest(manifest, entry.get('project_id') or ident(entry['project_url']))
                                    clear_receipt(target)
                                    with self.lock:
                                        entry.update(status='complete', bytes=record['size'], total=record['size'])
                                    break
                                except (httpx.HTTPError, ValueError, OSError) as exc:
                                    delay = retry_delay(exc, attempt)
                                    if attempt == 2 or delay is None:
                                        raise
                                    if self.download_cancel.wait(delay):
                                        raise Cancelled()
                    except Cancelled:
                        raise
                    except Exception as exc:
                        with self.lock:
                            suffix = f' (after {attempts} attempts)' if attempts > 1 else ''
                            entry.update(status='failed', message=download_error(exc) + suffix)
                    with self.lock:
                        self.download_job['done'] = index + 1
                        self.save_queue()
                    if self.download_cancel.wait(1):
                        raise Cancelled()
            with self.lock:
                failed = sum(e['status'] == 'failed' for e in targets)
                self.download_job['message'] = f'Batch finished · {failed} failed' if failed else 'All downloads complete'
        finally:
            with self.lock:
                for entry in targets:
                    if entry['status'] == 'downloading':
                        entry.update(status='interrupted', message='Stopped. Click Start downloads to continue.')
                self.write_index()
                self.save_queue()

    def login_browser(self):
        with self.lock:
            if self.browser is None:
                self.browser = LoginBrowser()
            return self.browser

    def action(self, path, data):
        with self.lock:
            try:
                with transaction(self.config, self.output):
                    return self._action(path, data)
            except OSError:
                self.request_shutdown()  # Restart replays an interrupted durable transaction.
                raise

    def _action(self, path, data):
        if self.shutdown.is_set():
            raise ValueError('The service is shutting down.')
        if path == '/api/browser/action':
            with self.lock:
                self.idle()
            action = data.get('action')
            if action not in {'click', 'text', 'key', 'scroll', 'credentials', 'close'}:
                raise ValueError('Unsupported browser action')
            return self.login_browser().call(action, **{k: v for k, v in data.items() if k != 'action'})
        if path == '/api/stop':
            with self.lock:
                target = data.get('target') or ('scan' if self.job['running'] else 'download')
                if target not in {'scan', 'download'}:
                    raise ValueError('Choose which operation to stop.')
                job = self.download_job if target == 'download' else self.job
                if target == 'scan' and job['kind'] != 'scan':
                    raise ValueError('No scan is running.')
                if job['running']:
                    (self.download_cancel if target == 'download' else self.cancel).set()
                    job['message'] = 'Stop requested. Waiting for the current network operation…'
                if target == 'download':
                    self.cancel_schedule()
            return {}
        with self.lock:
            if path in {'/api/downloads/start-selected', '/api/downloads/remove-selected'}:
                ids = data.get('ids')
                if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
                    raise ValueError('Select queue items first.')
                ids = set(ids)
                if not ids.issubset({e.get('id') for e in self.items}):
                    raise ValueError('Some selected items are no longer in the queue. Clear the selection and try again.')
                if path.endswith('/start-selected'):
                    self.start_downloads(ids, source='selected')
                else:
                    self.idle()
                    self.items = [e for e in self.items if e.get('id') not in ids]
                    self.save_queue()
                    if not self.pending_count():
                        self.cancel_schedule()
                return {}
            if path in {'/api/downloads/start', '/api/downloads/retry'}:
                if path.endswith('/retry'):
                    entry = next((e for e in self.items if e.get('id') == data.get('id')), None)
                    if entry is None or entry['status'] not in {'failed', 'interrupted', 'queued'}:
                        raise ValueError('Choose a pending or failed queue item.')
                    self.start_downloads({entry['id']})
                else:
                    self.start_downloads()
                return {}
            self.idle(include_download=path != '/api/scan')
            if path == '/api/downloads/edit-url':
                entry = next((e for e in self.items if e.get('id') == data.get('id')), None)
                if entry is None or entry['status'] not in {'queued', 'failed', 'interrupted'}:
                    raise ValueError('Choose a queued, failed, or interrupted item. Stop the batch before editing links.')
                url = data.get('url')
                if not isinstance(url, str):
                    raise ValueError('Enter a valid HTTP or HTTPS download URL.')
                url = url.strip()
                try:
                    parsed = urlsplit(url)
                    valid = parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password
                    parsed.port
                except ValueError:
                    valid = False
                if not valid or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
                    raise ValueError('Enter a valid HTTP or HTTPS download URL without credentials or whitespace.')
                entry['file'] = dict(entry['file'], url=url)
                entry.update(url_override=url, status='queued', bytes=0, total=None, message='Download URL updated. Ready to retry.')
                self.save_queue()
            elif path == '/api/projects/exclude':
                ids = data.get('ids')
                excluded = data.get('excluded')
                if not isinstance(ids, list) or not ids or not isinstance(excluded, bool):
                    raise ValueError('Select projects and choose exclude or include.')
                for pid in ids:
                    self.project_position(pid)
                stored = set(self.catalog.get('excluded_ids', []))
                stored = stored.union(ids) if excluded else stored.difference(ids)
                self.catalog['excluded_ids'] = sorted(stored)
                if excluded:
                    self.items = [e for e in self.items if e.get('project_id') not in stored or e['status'] == 'complete']
                    self.save_queue()
                    if not self.pending_count():
                        self.cancel_schedule()
                # Excluding a project changes eligibility, not its files or counts.
                # Keep cached summaries so the next poll does not rescan the library.
                for pid in set(ids):
                    row = self.catalog['projects'][self.project_position(pid)]
                    summary = self._summaries.get(pid) or row.get('_summary')
                    if summary is not None:
                        summary = dict(summary, excluded=pid in stored)
                        self._summaries[pid] = summary
                        row['_summary'] = summary
                    self.touch_library(pid)
                self.write_index()
            elif path == '/api/session/verify':
                self.start_job('session', lambda: self.verify(force=True))
            elif path == '/api/session/import':
                save_json(self.state_path, validate_state(data['state']))
                self.connected = False
                self.last_verified = 0
                def verify_import():
                    self.verify(force=True)
                    if self.browser and self.browser.active:
                        self.browser.call('close')
                self.start_job('session', verify_import)
            elif path == '/api/session/delete':
                for name in ('session.json', 'session.json.bak', 'session.json.corrupt', 'session-status.json.bak', 'session-status.json.corrupt'):
                    delete_file(self.config / name)
                self.connected = False
                self.last_verified = 0
                self.session_status = 'missing'
                delete_file(self.session_info_path)
                self.session_message = 'Session removed.'
                if self.browser:
                    self.browser.call('close')
            elif path == '/api/browser/start':
                def open_browser():
                    self.login_browser().call('start')
                    username, password = os.environ.get('HI10_USERNAME'), os.environ.get('HI10_PASSWORD')
                    if username and password:
                        self.login_browser().call('credentials', username=username, password=password)
                    with self.lock:
                        self.job['message'] = 'Login browser ready. Click Log In inside the website after reCAPTCHA loads, then save the session.'
                self.start_job('login', open_browser)
            elif path == '/api/browser/capture':
                def capture():
                    state = validate_state(self.login_browser().call('capture'))
                    save_json(self.state_path, state)
                    self.verify(force=True)
                    self.login_browser().call('close')
                self.start_job('session', capture)
            elif path == '/api/refresh':
                self.start_job('refresh', self.refresh)
            elif path == '/api/scan':
                ids = set(data.get('ids', []))
                self.start_job('scan', lambda: self.scan_projects(ids))
                self.job['project_ids'] = list(ids)
            elif path == '/api/preferences':
                quality = int(data['quality'])
                if quality < 0 or quality > 9000:
                    raise ValueError('Invalid quality')
                self.catalog['default_quality'] = quality
                self._summaries.clear()
                self._restoring = True
                def update_preferences():
                    try:
                        self.warm_library()
                        self.job['message'] = 'Quality preference updated'
                    finally:
                        self._restoring = False
                self.start_job('preferences', update_preferences)
                self.touch_library()
            elif path == '/api/project/settings':
                original = self.get_project(data['id'])
                project = deepcopy(original)
                if 'quality' in data:
                    quality = int(data['quality'])
                    if quality not in {0, *(v['resolution'] for v in project['variants'])}:
                        raise ValueError('Choose a detected quality')
                    project['preferred'] = quality
                if 'choices' in data:
                    choices = data['choices']
                    available = {}
                    for variant in project['variants']:
                        available.setdefault(variant['key'], {0}).add(variant['resolution'])
                    if not isinstance(choices, dict) or any(key not in available or int(value) not in available[key] for key, value in choices.items()):
                        raise ValueError('Choose a detected file quality')
                    project['choices'] = {key: int(value) for key, value in choices.items()}
                section_ids = {section['id'] for section in project.get('sections', [])}
                if 'sections' in data:
                    selected_sections = data['sections']
                    if not isinstance(selected_sections, list) or any(section_id not in section_ids for section_id in selected_sections):
                        raise ValueError('Choose detected collection sections')
                    project['selected_sections'] = list(dict.fromkeys(selected_sections))
                if 'section_qualities' in data:
                    qualities = data['section_qualities']
                    if not isinstance(qualities, dict):
                        raise ValueError('Invalid section qualities')
                    for section_id, quality in qualities.items():
                        available = {0, *(v['resolution'] for v in project['variants'] if v.get('section_id') == section_id)}
                        if section_id not in section_ids or int(quality) not in available:
                            raise ValueError('Choose a detected section quality')
                    project['section_qualities'] = {section_id: int(quality) for section_id, quality in qualities.items()}
                original.clear()
                original.update(project)
                self.save_catalog(original)
                self.write_index()
            elif path == '/api/queue':
                if not self.state_path.exists():
                    raise ValueError('Save a login session before downloading.')
                return self.queue(data.get('ids', []))
            elif path == '/api/downloads/remove':
                entry_id = data.get('id')
                self.items = [entry for entry in self.items if entry.get('id') != entry_id or entry['status'] == 'downloading']
                self.save_queue()
                if not self.pending_count():
                    self.cancel_schedule()
            elif path == '/api/downloads/clear-completed':
                self.items = [entry for entry in self.items if entry['status'] != 'complete']
                self.save_queue()
            elif path == '/api/downloads/schedule':
                self.set_schedule(data.get('starts_at'))
            elif path == '/api/downloads/unschedule':
                self.cancel_schedule()
            else:
                raise ValueError('Unknown action')
        return {}


class Handler(Routes, BaseHTTPRequestHandler):
    server_version = 'Hi10Web/0.3.0b1'

    def log_message(self, *args):
        pass  # Never log private requests or credentials.

    def send(self, status, data, content_type='application/json', extra=None):
        body = json.dumps(data).encode() if content_type == 'application/json' else data
        try:
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionError, TimeoutError):
            # Browsers may close polling/image requests while a response is in flight.
            # There is no peer left to receive an error response. Background jobs continue.
            self.close_connection = True
            return False
        return True

    def handle(self):
        try:
            super().handle()
        except (ConnectionError, TimeoutError):
            # Also cover disconnects while reading request lines/headers or request bodies.
            self.close_connection = True



def main():
    parser = argparse.ArgumentParser(description='Hi10 web interface')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--host', default=os.environ.get('HI10_WEB_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('HI10_WEB_PORT', '8080')))
    parser.add_argument('--config', type=Path, default=Path(os.environ.get('HI10_CONFIG_DIR', '.hi10')))
    parser.add_argument('--output', type=Path, default=Path(os.environ.get('HI10_DOWNLOAD_DIR', 'downloads')))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    for name in ('httpx', 'httpcore'):
        logging.getLogger(name).setLevel(logging.WARNING)
    from .config import validate
    validate()
    leases = ServiceLocks(args.config, args.output)
    try:
        _serve(args)
    finally:
        leases.close()


def _serve(args):
    app = Application(args.config, args.output, os.environ.get('HI10_WEB_PASSWORD'))
    from waitress.server import create_server
    from .server import application
    server = create_server(application(app), host=args.host, port=args.port, threads=4,
                           connection_limit=64, channel_timeout=20, cleanup_interval=5,
                           max_request_header_size=32768, max_request_body_size=2 * 1024 * 1024,
                           inbuf_overflow=65536, outbuf_overflow=1048576,
                           clear_untrusted_proxy_headers=True)
    app.start_services()
    print(f'Hi10 web interface: http://{args.host}:{args.port}', flush=True)
    def stop(signum, frame):
        app.request_shutdown()
        server.close()
        raise KeyboardInterrupt
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    main()
