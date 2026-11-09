"""Validate supported private state without silently accepting unknown versions."""
import math


def mapping(value):
    return isinstance(value, dict)


def project(value):
    return mapping(value) and all(isinstance(value.get(k), str) for k in ('id', 'url', 'title')) and isinstance(value.get('scanned', False), bool)


def catalog(value):
    if not mapping(value) or value.get('schema_version', 1) not in {1, 2}:
        return False
    projects = value.get('projects')
    return isinstance(projects, list) and all(project(p) for p in projects) and len({p['id'] for p in projects}) == len(projects) and isinstance(value.get('excluded_ids', []), list)


def queue(value):
    return isinstance(value, list) and all(mapping(e) and isinstance(e.get('filename'), str) and e.get('status') in {'queued', 'downloading', 'failed', 'interrupted', 'complete'} and ('file' not in e or mapping(e['file'])) for e in value)


def schedule(value):
    return mapping(value) and (value.get('starts_at') is None or (type(value.get('starts_at')) in {int, float} and math.isfinite(value['starts_at'])))


def manifest(value):
    return mapping(value) and all(isinstance(k, str) and mapping(v) and isinstance(v.get('url'), str) and isinstance(v.get('size'), int) and isinstance(v.get('sha256'), str) for k, v in value.items())


def session(value):
    return mapping(value) and isinstance(value.get('cookies'), list) and len(value['cookies']) <= 1000 and all(
        mapping(c) and all(isinstance(c.get(k), str) for k in ('name', 'value', 'domain', 'path'))
        and (type(c.get('expires', -1)) in {int, float} and math.isfinite(c.get('expires', -1)))
        and isinstance(c.get('secure', True), bool) for c in value['cookies'])


def auth_secret(value):
    import re
    return mapping(value) and isinstance(value.get('secret'), str) and bool(re.fullmatch('[a-f0-9]{64}', value['secret']))


def access_sessions(value):
    import re
    return mapping(value) and len(value) <= 256 and all(isinstance(k, str) and re.fullmatch('[a-f0-9]{48}', k) and type(v) is int for k,v in value.items())
