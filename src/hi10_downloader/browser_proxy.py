"""Loopback-only authenticated HTTPS tunnel for the isolated login browser.

DNS is checked and pinned by this proxy, not re-resolved by Chromium. This closes
 the validation/re-resolution gap of browser request interception alone.
"""
import base64
import secrets
import selectors
import socket
import socketserver
from threading import BoundedSemaphore, Event, Thread
import time
from urllib.parse import urlsplit

from .network import public_addresses


class Tunnel(socketserver.StreamRequestHandler):
    timeout = 20

    def handle(self):
        if not self.server.slots.acquire(blocking=False):
            return
        remote = None
        try:
            line = self.rfile.readline(8193)
            if len(line) > 8192:
                return
            method, authority, protocol = line.decode('ascii').strip().split(' ')
            headers, size = {}, len(line)
            while True:
                line = self.rfile.readline(8193); size += len(line)
                if size > 32768:
                    return
                if line in {b'\r\n', b'\n'}:
                    break
                if not line:
                    return
                key, value = line.decode('ascii').split(':', 1)
                headers[key.strip().lower()] = value.strip()
            if headers.get('proxy-authorization') != self.server.authorization:
                self.wfile.write(b'HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="Hi10 browser"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                return
            parts = urlsplit('https://' + authority)
            if method != 'CONNECT' or parts.username or not parts.hostname or parts.path or parts.port != 443:
                self.wfile.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
                return
            addresses = public_addresses(parts.hostname, 443)
            remote = socket.create_connection((addresses[0], 443), timeout=15)
            self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n'); self.wfile.flush()
            deadline, count = time.monotonic() + 90, 0
            with selectors.DefaultSelector() as selector:
                selector.register(self.connection, selectors.EVENT_READ, remote)
                selector.register(remote, selectors.EVENT_READ, self.connection)
                while not self.server.stopping.is_set() and time.monotonic() < deadline:
                    for key, _ in selector.select(timeout=1):
                        data = key.fileobj.recv(65536)
                        if not data:
                            return
                        count += len(data)
                        if count > 32 * 1024**2:
                            return
                        key.data.sendall(data)
        except Exception:
            # Proxy request data and URLs can contain credentials; never log them.
            return
        finally:
            if remote:
                remote.close()
            self.server.slots.release()


class ProxyServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class BrowserProxy:
    def __init__(self):
        self.username, self.password = 'hi10', secrets.token_hex(24)
        self.server = ProxyServer(('127.0.0.1', 0), Tunnel)
        self.server.authorization = 'Basic ' + base64.b64encode(f'{self.username}:{self.password}'.encode()).decode()
        self.server.slots = BoundedSemaphore(8)
        self.server.stopping = Event()
        self.thread = Thread(target=self.server.serve_forever, daemon=True, name='browser-egress-proxy')
        self.thread.start()

    def settings(self):
        return {'server': f'http://127.0.0.1:{self.server.server_address[1]}', 'username': self.username, 'password': self.password}

    def close(self):
        self.server.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
