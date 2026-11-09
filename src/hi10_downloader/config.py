"""Validate deployment settings before accepting requests."""
import ipaddress
import os
from urllib.parse import urlsplit


def validate():
    for name, default, minimum in [('HI10_MAX_QUEUE_ITEMS', 50000, 1), ('HI10_MAX_FILE_BYTES', 100*1024**3, 1), ('HI10_MIN_FREE_BYTES', 256*1024**2, 0), ('HI10_DOWNLOAD_DEADLINE', 21600, 1)]:
        try:
            if int(os.environ.get(name, str(default))) < minimum:
                raise ValueError()
        except ValueError:
            raise ValueError(f'{name} must be an integer of at least {minimum}.') from None
    for value in os.environ.get('HI10_ALLOWED_NETWORKS', '').split(','):
        if value.strip():
            try:
                ipaddress.ip_network(value.strip())
            except ValueError:
                raise ValueError('HI10_ALLOWED_NETWORKS must contain valid CIDR networks.') from None
    origin = os.environ.get('HI10_WEB_ORIGIN', '')
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise ValueError('HI10_WEB_ORIGIN must be an HTTP(S) origin without path or credentials.')
