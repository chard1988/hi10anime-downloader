"""Small, authenticated range probes for alternative links of one selected file."""
from collections import Counter
from dataclasses import dataclass
import re
import time
from urllib.parse import urlsplit
import httpx
from .retries import certificate_verification_failed

MAX_MIRRORS = 32


class MirrorCheckError(ValueError):
    pass


@dataclass
class MirrorSelection:
    urls: list[str]
    checked: int = 0

    @property
    def message(self):
        return f'Checked {self.checked} links; {len(self.urls)} active.' if self.checked else ''


def urls_for(item):
    urls = item.get('mirrors', [])
    if not isinstance(urls, list) or any(not isinstance(url, str) for url in urls):
        raise MirrorCheckError('Invalid alternative download links. Rescan this project.')
    return list(dict.fromkeys([item['url'], *urls]))


def _probe(client, url, project_url, cancel, deadline):
    parsed = urlsplit(url)
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
        return 'invalid URL'
    parsed.port  # Validate malformed ports before opening a connection.
    with client.stream('GET', url, headers={'Range': 'bytes=0-3', 'Referer': project_url,
                       'Accept-Encoding': 'identity'}, timeout=httpx.Timeout(5, connect=5)) as response:
        cancel()
        if response.status_code not in {200, 206}:
            return f'HTTP {response.status_code}'
        if any(kind in response.headers.get('content-type', '').lower() for kind in ('text/', 'json', 'xml')):
            return 'document instead of video'
        if response.headers.get('content-encoding', 'identity').lower() != 'identity':
            return 'unexpected compressed response'
        if response.status_code == 206:
            match = re.fullmatch(r'bytes 0-(\d+)/(\d+|\*)', response.headers.get('content-range', ''))
            if not match or int(match[1]) < 3 or (match[2] != '*' and int(match[2]) < 4):
                return 'invalid partial response'
        prefix = bytearray()
        for chunk in response.iter_bytes(chunk_size=4):
            cancel()
            if time.monotonic() > deadline:
                raise MirrorCheckError('Download-link checking time limit reached. Retry the item later.')
            prefix.extend(chunk[:4-len(prefix)])
            if len(prefix) == 4:
                break  # Close immediately even if the server ignored Range and sent HTTP 200.
        return None if prefix == b'\x1a\x45\xdf\xa3' else 'not a Matroska video'


def check_mirrors(client, item, project_url, cancel=lambda: None, progress=lambda done, total, active: None):
    urls = urls_for(item)
    if len(urls) == 1:
        return MirrorSelection(urls)  # Single-link files keep their existing download path.
    if len(urls) > MAX_MIRRORS:
        raise MirrorCheckError(f'Too many alternative links for one file (limit {MAX_MIRRORS}).')
    active, failures = [], Counter()
    deadline = time.monotonic() + 60
    progress(0, len(urls), 0)
    for number, url in enumerate(urls, 1):
        cancel()
        if time.monotonic() > deadline:
            raise MirrorCheckError('Download-link checking time limit reached. Retry the item later.')
        try:
            reason = _probe(client, url, project_url, cancel, deadline)
        except httpx.TimeoutException:
            reason = 'network timeout'
        except httpx.HTTPError as exc:
            reason = 'TLS certificate verification failed' if certificate_verification_failed(exc) else 'connection or HTTP failure'
        except (ValueError, httpx.InvalidURL) as exc:
            if isinstance(exc, MirrorCheckError):
                raise
            reason = 'invalid response or URL'
        if reason:
            failures[reason] += 1
        else:
            active.append(url)
        progress(number, len(urls), len(active))
    if not active:
        reasons = ', '.join(f'{reason} ({count})' for reason, count in failures.items())
        raise MirrorCheckError(f'No active download link for the selected quality: {len(urls)} links checked; {reasons}.')
    return MirrorSelection(active, len(urls))


def try_next_mirror(item, urls, error):
    """Fallback after a successful probe goes stale; never retry disk/size policy errors."""
    eligible = isinstance(error, httpx.HTTPError) or (isinstance(error, ValueError) and str(error).startswith(
        ('Download returned a document', 'Response is not a Matroska', 'Download incomplete', 'Expected a complete file')))
    if eligible:
        index = urls.index(item['url'])
        limited_host = urlsplit(item['url']).hostname if isinstance(error, httpx.HTTPStatusError) and error.response.headers.get('Retry-After') else None
        for url in urls[index+1:]:
            if limited_host and urlsplit(url).hostname == limited_host:
                continue  # Keep Retry-After handling for this server in the caller.
            item['url'] = url
            return True
    return False
