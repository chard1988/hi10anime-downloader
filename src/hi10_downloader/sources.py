"""Resolve the site's known client-rendered project list without executing scripts."""
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .cli import LIST_URL, fetch_page
from .network import bounded_page

SCRIPT_HOST = 'xlordnoro.github.io'
DATA_HOST = 'raw.githubusercontent.com'


def load_project_list(client, html=None):
    html = html if html is not None else fetch_page(client, LIST_URL)
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.select_one('#urlContainer')
    if container is None:
        raise ValueError('The project list is unavailable. Verify your session again.')
    if container.select('a[href]'):
        return html
    for script in soup.select('script[src]'):
        url = urljoin(LIST_URL, script['src'])
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname != SCRIPT_HOST or parts.path != '/dynamic_all_projects_post.js':
            continue
        script_text = bounded_page(client, url, 100_000)
        if len(script_text) > 100_000:
            raise ValueError('The project-list script is larger than expected.')
        match = re.search(r'''\b(?:const|let|var)\s+githubRawUrl\s*=\s*(['"])(https://[^'"\s]+)\1''', script_text)
        if not match:
            raise ValueError('The project-list data source changed. Its resolver needs updating.')
        data_url = match.group(2)
        data_parts = urlsplit(data_url)
        if data_parts.scheme != 'https' or data_parts.hostname != DATA_HOST or not data_parts.path.startswith('/xlordnoro/xlordnoro.github.io/'):
            raise ValueError('The project-list script references an unexpected data source.')
        data_text = bounded_page(client, data_url, 4_000_000)
        if len(data_text) > 4_000_000:
            raise ValueError('The project-list data is larger than expected.')
        fragment = BeautifulSoup(data_text, 'html.parser')
        for anchor in fragment.select('a[href]'):
            target = urljoin(LIST_URL, anchor['href'])
            target_parts = urlsplit(target)
            if target_parts.scheme == 'https' and target_parts.hostname == 'hi10anime.com':
                element = soup.new_tag('a', href=target)
                element.string = anchor.get_text(' ', strip=True)
                container.append(element)
        break
    if not container.select('a[href]'):
        raise ValueError('No project links were found. The site may have changed its dynamic project list.')
    return str(soup)
