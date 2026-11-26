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


def monitoring(value):
    import re
    def timestamp(v):return type(v) in {int,float} and math.isfinite(v) and v>=0
    if not mapping(value) or value.get('version')!=1 or type(value.get('paused')) is not bool:
        return False
    if type(value.get('interval_minutes')) is not int or not 15<=value['interval_minutes']<=10080:
        return False
    projects=value.get('projects')
    if not mapping(projects) or len(projects)>200:return False
    count=0
    for pid,record in projects.items():
        if not isinstance(pid,str) or not mapping(record):return False
        seen=record.get('seen')
        if not isinstance(seen,list) or any(not isinstance(k,str) or not re.fullmatch('[a-f0-9]{64}',k) for k in seen):return False
        count+=len(seen)
        if count>100000 or len(set(seen))!=len(seen) or not timestamp(record.get('next_check')):return False
        if record.get('last_checked') is not None and not timestamp(record['last_checked']):return False
        if record.get('last_error') is not None and not isinstance(record['last_error'],str):return False
    return (value.get('last_run') is None or timestamp(value['last_run'])) and isinstance(value.get('message'),str)
