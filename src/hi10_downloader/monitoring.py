"""Opt-in project polling and automatic queues, using the service scheduler.

The private seen ledger tracks logical selected files, rather than URLs or
qualities. Queue and ledger updates commit together so clearing a queue or
restarting the service cannot repeatedly add the same episode.
"""
import hashlib
import time

from . import schema
from .storage import load_json, save_json, transaction

MAX_PROJECTS = 200
MAX_TRACKED = 100000
CHECK_BATCH = 5


def identity(item):
    return hashlib.sha256(item['key'].encode()).hexdigest()


class ProjectMonitoring:
    def __init__(self, app):
        self.app = app
        self.path = app.config / 'monitoring.json'
        self.state = load_json(self.path, schema.monitoring) if self.path.exists() else {
            'version': 1, 'paused': False, 'interval_minutes': 60,
            'projects': {}, 'last_run': None,
            'message': 'Select projects to monitor. Existing missing files and future additions will download automatically.',
        }
        self.retry_after = 0

    def save(self):
        save_json(self.path, self.state)
        self.app.scheduler_wake.set()

    def changed(self, pid):
        self.app.touch_library(pid)

    def public_project(self, pid):
        entry = self.state['projects'].get(pid)
        return {
            'monitored': bool(entry),
            'monitor_last_checked': entry.get('last_checked') if entry else None,
            'monitor_error': entry.get('last_error') if entry else None,
        }

    def public(self):
        excluded = set(self.app.catalog.get('excluded_ids', []))
        available = {p['id'] for p in self.app.catalog['projects']}
        active = [p for pid, p in self.state['projects'].items() if pid in available and pid not in excluded]
        return {
            'paused': self.state['paused'], 'interval_minutes': self.state['interval_minutes'],
            'count': len(self.state['projects']), 'active_count': len(active),
            'next_check': min((p['next_check'] for p in active), default=None),
            'last_run': self.state['last_run'], 'message': self.state['message'],
        }

    def set_projects(self, ids, enabled):
        if not isinstance(ids, list) or not ids or any(not isinstance(pid, str) for pid in ids) or type(enabled) is not bool:
            raise ValueError('Select projects and choose whether to monitor them.')
        ids = set(ids)
        for pid in ids:
            self.app.project_position(pid)
        if enabled and ids.intersection(self.app.catalog.get('excluded_ids', [])):
            raise ValueError('Include excluded projects before monitoring them.')
        projects = self.state['projects']
        if enabled and len(set(projects) | ids) > MAX_PROJECTS:
            raise ValueError(f'Monitoring supports at most {MAX_PROJECTS} projects at once.')
        for pid in ids:
            if enabled:
                projects.setdefault(pid, {'seen': [], 'next_check': 0, 'last_checked': None, 'last_error': None})
            else:
                projects.pop(pid, None)
            self.changed(pid)
        self.state['message'] = 'Monitoring selection updated. Missing files will be checked in the background.'
        self.retry_after = 0
        self.save()

    def settings(self, paused, interval):
        if type(paused) is not bool or type(interval) is not int or not 15 <= interval <= 10080:
            raise ValueError('Choose a monitoring interval between 15 minutes and 7 days.')
        if interval != self.state['interval_minutes']:
            for record in self.state['projects'].values():
                record['next_check'] = (record.get('last_checked') or 0) + interval * 60
        self.state.update(paused=paused, interval_minutes=interval)
        if not paused:
            self.retry_after = 0
        self.state['message'] = 'Monitoring paused.' if paused else 'Monitoring enabled.'
        if paused:
            if self.app.job['running'] and self.app.job['kind'] == 'monitor':
                self.app.cancel.set()
            if self.app.download_job['running'] and self.app.download_job.get('source') == 'monitor':
                self.app.download_cancel.set()
        self.save()

    def check_now(self):
        if self.state['paused']:
            raise ValueError('Resume monitoring before checking now.')
        if not self.state['projects']:
            raise ValueError('Choose projects to monitor first.')
        for record in self.state['projects'].values():
            record['next_check'] = 0
        self.retry_after = 0
        self.state['message'] = 'Check requested; waiting for the current operation if needed.'
        self.save()

    def clear(self):
        for pid in list(self.state['projects']):
            self.changed(pid)
        self.state['projects'] = {}
        self.state['message'] = 'No projects are monitored. Queue entries and files are preserved.'
        if self.app.job['kind'] == 'monitor' and self.app.job['running']:
            self.app.cancel.set()
        self.save()

    def tick(self, now=None):
        app = self.app
        now = time.time() if now is None else now
        with app.lock:
            if app.shutdown.is_set() or self.state['paused'] or not self.state['projects']:
                return False
            if app.job['running'] or now < self.retry_after:
                return False
            if not app.state_path.exists() or (not app.connected and app.session_status in {'missing', 'expired'}):
                self.state['message'] = 'Monitoring needs a working saved session. Verify or import your session.'
                return False
            excluded = set(app.catalog.get('excluded_ids', []))
            available = {p['id'] for p in app.catalog['projects']}
            if not app.download_job['running'] and app.schedule.get('starts_at') is None:
                # Never adopt manual entries, or automatically retry an attempted file.
                pending = {
                    e['id'] for e in app.items if e.get('monitor_auto') and not e.get('monitor_attempted')
                    and e['status'] in {'queued', 'interrupted'}
                    and e.get('project_id') in self.state['projects'] and e.get('project_id') in available
                    and e.get('project_id') not in excluded
                }
                if pending:
                    self.retry_after = now + 300  # Back off if verification fails before any file starts.
                    app.start_downloads(pending, source='monitor')
                    return True
            due = sorted(
                (p['next_check'], pid) for pid, p in self.state['projects'].items()
                if pid in available and pid not in excluded and p['next_check'] <= now
            )
            ids = [pid for _, pid in due[:CHECK_BATCH]]
            if not ids:
                return False
            for pid in ids:
                self.state['projects'][pid]['next_check'] = now + self.state['interval_minutes'] * 60
            self.state['message'] = f'Checking {len(ids)} monitored projects…'
            self.save()
            app.start_job('monitor', lambda: self.run(ids))
            return True

    def run(self, ids):
        app = self.app
        try:
            app.scan_projects(set(ids))
            for pid in ids:
                with app.lock:
                    record = self.state['projects'].get(pid)
                    if not record or self.state['paused'] or pid in app.catalog.get('excluded_ids', []) or app.cancel.is_set():
                        continue
                    project = app.get_project(pid)
                    if project.get('error'):
                        record.update(last_checked=time.time(), last_error=project['error'])
                        self.changed(pid)
                        self.save()
                        continue
                    files = app.selected(project)
                    manifest = dict(app.manifest())
                    seen = set(record['seen'])
                additions = [item for item in files if identity(item) not in seen]
                missing = {item['key'] for item in additions if not app.is_complete(project, item, manifest)}
                with app.lock:
                    # Configuration can change while checks run. A re-enabled record
                    # is a new opt-in and must not inherit a stale check's results.
                    if self.state['projects'].get(pid) is not record or self.state['paused'] or app.cancel.is_set():
                        continue
                    tracked = sum(len(r['seen']) for r in self.state['projects'].values())
                    if tracked + len(additions) > MAX_TRACKED:
                        record.update(last_checked=time.time(), last_error='Monitoring identity limit reached. Unmonitor older projects to free space.')
                        self.changed(pid)
                        self.save()
                        continue
                    try:
                        with transaction(app.config, app.output):
                            if missing:
                                app.queue([pid], file_keys=missing, monitoring=True)
                            record.update(seen=sorted(seen | {identity(item) for item in additions}), last_checked=time.time(), last_error=None)
                            self.changed(pid)
                            self.state['last_run'] = time.time()
                            self.state['message'] = 'Monitored projects checked. New/missing files are queued for automatic download.'
                            self.save()
                    except ValueError:
                        record.update(last_error='Could not queue monitored files. Check the queue limit and project selections.')
                        self.changed(pid)
                        self.save()
        except OSError:
            app.request_shutdown()  # Restart must recover a pending queue/ledger transaction first.
            raise
        except Exception:
            if app.shutdown.is_set() or app.cancel.is_set():
                raise
            with app.lock:
                for pid in ids:
                    record = self.state['projects'].get(pid)
                    if record:
                        record.update(last_error='Check stopped or failed. Verify session/connectivity and retry.',
                                      next_check=time.time() + min(300, self.state['interval_minutes'] * 60))
                        self.changed(pid)
                self.state['message'] = 'Monitoring check needs attention. Verify your saved session and connectivity.'
                self.save()
            raise
