"""Pinned-address HTTP connections: validate every DNS answer and redirect hop."""
import ipaddress
import os
import socket
import time

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend


def permitted(address):
    ip = ipaddress.ip_address(address.split('%')[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    exceptions = [ipaddress.ip_network(value.strip()) for value in os.environ.get('HI10_ALLOWED_NETWORKS', '').split(',') if value.strip()]
    return (ip.is_global and not ip.is_multicast) or any(ip in net for net in exceptions)


def public_addresses(host, port):
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise httpcore.ConnectError('DNS resolution failed') from None
    addresses = list(dict.fromkeys(r[4][0] for r in records))
    if not addresses or any(not permitted(address) for address in addresses):
        raise httpcore.ConnectError('Outbound policy blocked a non-public destination')
    return addresses


class PublicBackend(SyncBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        host = host.decode('ascii') if isinstance(host, bytes) else host
        addresses = public_addresses(host, port)
        deadline = time.monotonic() + (timeout if timeout is not None else 15)
        error = None
        for address in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise httpcore.ConnectTimeout('Connection deadline exceeded')
            try:
                # TLS is still negotiated by httpcore with the ORIGINAL hostname/SNI.
                return super().connect_tcp(address, port, timeout=remaining, local_address=local_address, socket_options=socket_options)
            except httpcore.ConnectError as exc:
                error = exc
        raise error or httpcore.ConnectError('Connection failed')

    def connect_unix_socket(self, *args, **kwargs):
        raise httpcore.ConnectError('Unix socket connections are not allowed')


class PublicTransport(httpx.HTTPTransport):
    def __init__(self):
        super().__init__(trust_env=False, retries=0)
        # httpx/httpcore are locked and covered by transport integration tests.
        self._pool._network_backend = PublicBackend()


def client(**kwargs):
    return httpx.Client(transport=PublicTransport(), trust_env=False, follow_redirects=True,
                        max_redirects=5, timeout=httpx.Timeout(30, connect=15), **kwargs)


def bounded_page(client, url, limit=4_000_000):
    deadline = time.monotonic() + 45
    with client.stream('GET', url) as response:
        response.raise_for_status()
        if 'wp-login.php' in str(response.url) or '/not-allowed' in str(response.url):
            raise ValueError('Session is expired or lacks access. Sign in again.')
        chunks, size = [], 0
        for chunk in response.iter_bytes(65536):
            size += len(chunk)
            if size > limit:
                raise ValueError('Page exceeds the configured response size limit.')
            if time.monotonic() > deadline:
                raise ValueError('Page fetch deadline exceeded.')
            chunks.append(chunk)
        return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')
