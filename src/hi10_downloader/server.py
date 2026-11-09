"""Production WSGI boundary; routing is shared with the legacy test adapter."""
from email.message import Message
from http import HTTPStatus
import io
import json
import logging
import os
from types import SimpleNamespace
import uuid

from .routes import Routes


class WSGIRoutes(Routes):
    def __init__(self, app, environ):
        self.server = SimpleNamespace(app=app)
        self.path = environ.get('PATH_INFO', '/') + ('?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else '')
        self.headers = Message()
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_', '-')] = value
        for key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            if environ.get(key):
                self.headers[key.replace('_', '-')] = environ[key]
        self.rfile = environ['wsgi.input']
        self.connection = SimpleNamespace(settimeout=lambda timeout: None)
        self.client_address = (environ.get('REMOTE_ADDR', 'unknown'), 0)
        self.secure = environ.get('wsgi.url_scheme') == 'https' or os.environ.get('HI10_WEB_ORIGIN', '').startswith('https://')
        self.response = None

    def send(self, status, data, content_type='application/json', extra=None):
        body = json.dumps(data).encode() if content_type == 'application/json' else data
        headers = [('Content-Type', content_type), ('Content-Length', str(len(body))),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                   ('Referrer-Policy', 'no-referrer'),
                   ('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
        for key, value in (extra or {}).items():
            if key.lower() == 'set-cookie' and self.secure:
                value += '; Secure'
            headers.append((key, value))
        self.response = (status, headers, body)
        return True


def application(app):
    def dispatch(environ, start_response):
        request_id = uuid.uuid4().hex
        routes = WSGIRoutes(app, environ)
        allowed = {h.strip().lower() for h in os.environ.get('HI10_ALLOWED_HOSTS', '').split(',') if h.strip()}
        host = routes.headers.get('Host', '').lower()
        origin = os.environ.get('HI10_WEB_ORIGIN', '').rstrip('/')
        try:
            if allowed and host not in allowed:
                routes.send(400, {'error': 'Unrecognized Host header.'})
            elif origin and routes.headers.get('Origin') and routes.headers['Origin'] != origin:
                routes.send(403, {'error': 'Cross-origin requests are not allowed.'})
            elif environ['REQUEST_METHOD'] == 'GET':
                routes.do_GET()
            elif environ['REQUEST_METHOD'] == 'POST':
                routes.do_POST()
            else:
                routes.send(405, {'error': 'Method not allowed.'}, extra={'Allow': 'GET, POST'})
        except Exception:
            # Never log exception text, request URLs, bodies, or authorization data.
            logging.getLogger(__name__).error('request_failed request_id=%s', request_id)
            routes.send(500, {'error': 'Request failed. See request ID in service logs.', 'request_id': request_id})
        status, headers, body = routes.response
        headers.append(('X-Request-ID', request_id))
        start_response(f'{status} {HTTPStatus(status).phrase}', headers)
        return [body]
    return dispatch
