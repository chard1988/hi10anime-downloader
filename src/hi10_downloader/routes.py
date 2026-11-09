"""Shared API routes, independent of the production or test HTTP transport."""
import json
import mimetypes
import os
from pathlib import Path
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit
from .runtime import ACCESS_DAYS
from . import __version__


class Routes:
    def authenticated(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            return 'hi10_access' in cookie and self.server.app.valid_access_cookie(cookie['hi10_access'].value)
        except Exception:
            return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/healthz':
            stopping = self.server.app.shutdown.is_set()
            self.send(503 if stopping else 200, {'status': 'stopping' if stopping else 'ok'})
            return
        if path.startswith('/api/'):
            if not self.authenticated():
                self.send(401, {'error': 'Unlock the web interface first.'})
                return
            try:
                if path == '/api/state':
                    query = parse_qs(urlsplit(self.path).query)
                    version = int(query['library_version'][0]) if 'library_version' in query else None
                    page = int(query.get('download_page', ['0'])[0])
                    state = self.server.app.snapshot(version, page, query.get('download_filter', ['all'])[0], query.get('grouped', ['0'])[0] == '1', json.loads(query.get('group_pages', ['{}'])[0]))
                    # Queue stores private URLs on disk; expose only status fields.
                    state['downloads'] = [{k: v for k, v in e.items() if k in {'id', 'project', 'filename', 'status', 'bytes', 'total', 'message', 'destination', 'group_id'}} for e in state['downloads']]
                    self.send(200, state)
                elif path == '/api/diagnostics':
                    import platform
                    import shutil
                    with self.server.app.lock:
                        app = self.server.app
                        self.send(200, {'version': __version__, 'python': platform.python_version(),
                                        'queue_items': len(app.items), 'projects': len(app.catalog['projects']),
                                        'download_running': app.download_job['running'],
                                        'library_operation': app.job['kind'], 'library_running': app.job['running'],
                                        'free_download_bytes': shutil.disk_usage(app.output).free})
                elif path.startswith('/api/download-link/'):
                    entry_id = path.rsplit('/', 1)[-1]
                    with self.server.app.lock:
                        entry = next((e for e in self.server.app.items if e.get('id') == entry_id), None)
                        url = entry.get('file', {}).get('url', '') if entry else ''
                    parsed = urlsplit(url)
                    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or any(ord(c) < 32 or ord(c) == 127 for c in url):
                        raise ValueError('No valid download link is available for this item.')
                    if parse_qs(urlsplit(self.path).query).get('open') == ['1']:
                        self.send(302, b'', 'text/plain', {'Location': url})
                    else:
                        self.send(200, {'url': url})
                elif path.startswith('/api/project/'):
                    self.send(200, self.server.app.details(path.rsplit('/', 1)[-1]))
                elif path == '/api/browser/image':
                    if self.server.app.browser is None:
                        raise ValueError('Open the login browser first.')
                    self.send(200, self.server.app.browser.call('screenshot'), 'image/png')
                else:
                    self.send(404, {'error': 'Not found'})
            except (ValueError, OSError) as exc:
                self.send(400, {'error': str(exc) if isinstance(exc, ValueError) else 'Could not read application data.'})
            return
        names = {'/': 'index.html', '/style.css': 'style.css'}
        names.update({'/' + name: name for name in ('core.js', 'projects.js', 'downloads.js', 'render.js', 'details.js', 'browser.js', 'app.js')})
        if path not in names:
            self.send(404, {'error': 'Not found'})
            return
        asset = Path(__file__).parent / 'static' / names[path]
        self.send(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or 'text/plain')

    def do_POST(self):
        path = urlsplit(self.path).path
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            self.send(403, {'error': 'Cross-origin requests are not allowed.'})
            return
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.send(415, {'error': 'Expected JSON'})
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 2 * 1024 * 1024:
                raise ValueError('Request is empty or too large (maximum 2 MB).')
            self.connection.settimeout(20)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            if path == '/api/unlock':
                if not self.server.app.allow_login(getattr(self, 'client_address', ('unknown', 0))[0]):
                    self.send(429, {'error': 'Too many login attempts. Try again in five minutes.'}, extra={'Retry-After': '300'})
                    return
                if secrets.compare_digest(str(data.get('password', '')), self.server.app.password):
                    self.send(200, {}, extra={'Set-Cookie': f'hi10_access={self.server.app.access_cookie()}; Max-Age={ACCESS_DAYS * 86400}; HttpOnly; SameSite=Strict; Path=/'})
                else:
                    self.send(401, {'error': 'Incorrect web interface password.'})
                return
            if not self.authenticated():
                self.send(401, {'error': 'Unlock the web interface first.'})
                return
            if path == '/api/lock':
                cookie = SimpleCookie(self.headers.get('Cookie', ''))
                if 'hi10_access' in cookie:
                    self.server.app.revoke_access_cookie(cookie['hi10_access'].value)
                self.send(200, {}, extra={'Set-Cookie': 'hi10_access=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/'})
                return
            self.send(200, self.server.app.action(path, data))
        except ValueError as exc:
            message = str(exc) if not isinstance(exc, json.JSONDecodeError) and 'http' not in str(exc) else 'Invalid JSON or action. Check your input and try again.'
            self.send(400, {'error': message})
        except (KeyError, TypeError):
            self.send(400, {'error': 'Invalid request. Check your input and selections.'})
        except OSError:
            self.send(500, {'error': 'Could not save data. Check folder permissions.'})
