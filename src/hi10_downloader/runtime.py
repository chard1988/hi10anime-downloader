"""Bounded project cache, persistent access cookies, and the download scheduler."""
from collections import OrderedDict, deque
from datetime import datetime
import hashlib
import hmac
import json
import secrets
import shutil
import os
from threading import Event, Thread, RLock
import time
import logging

from .cli import child_path, save_json
from .storage import load_json
from . import schema

ACCESS_DAYS = 30


class RuntimeState:
    def init_runtime(self):
        if self.catalog_path.exists() and any(p.get('scanned') and 'variants' in p for p in self.catalog['projects']):
            backup = self.config / 'library-legacy-backup.json'
            if not backup.exists():
                shutil.copy2(self.catalog_path, backup)
                os.chmod(backup, 0o600)
        self.project_dir = self.config / 'projects'
        self.project_dir.mkdir(exist_ok=True)
        stored_ids = {path.stem for path in self.project_dir.glob('*.json')}
        for entry in self.catalog['projects']:
            if entry['id'] in stored_ids and not entry.get('_detail'):
                entry.pop('variants', None)
                entry['_detail'] = True
        self._queue_groups_cache = {}
        self._positions = {}
        self._details = OrderedDict()
        self._summaries = {}
        self._library_payload = None
        self.library_version = 1
        self._full_revision = 1
        self._changes = deque(maxlen=256)
        self._restoring = False
        self._manifest_signature = self.manifest_signature()
        self._manifest_cache = self._read_manifest()
        if self.catalog.get('manifest_signature') == list(self._manifest_signature or ()):
            self._summaries = {p['id']: p['_summary'] for p in self.catalog['projects'] if '_summary' in p}
        self.schedule_path = self.config / 'schedule.json'
        self.schedule = load_json(self.schedule_path, schema.schedule) if self.schedule_path.exists() else {'starts_at': None, 'message': ''}
        self.scheduler_wake = Event()
        self.shutdown = Event()
        self.session_status = 'saved' if self.state_path.exists() else 'missing'
        self.last_verified = 0
        self.session_info_path = self.config / 'session-status.json'
        if self.session_info_path.exists() and self.state_path.exists():
            try:
                info = load_json(self.session_info_path)
                if info['fingerprint'] == self.session_fingerprint() and time.time() - info['verified_at'] < 300:
                    self.connected = True
                    self.last_verified = info['verified_at']
                    self.session_status = 'connected'
                    self.session_message = 'Saved session restored.'
            except (OSError, ValueError, KeyError):
                pass
        secret_path = self.config / 'web-auth.json'
        if not secret_path.exists():
            save_json(secret_path, {'secret': secrets.token_hex(32)})
        self._auth_secret = load_json(secret_path, schema.auth_secret)['secret'].encode()
        self.login_attempts = {}
        self.auth_lock = RLock()
        self.access_sessions_path = self.config / 'access-sessions.json'
        self.access_sessions = {}
        if self.access_sessions_path.exists():
            try:
                sessions = json.loads(self.access_sessions_path.read_text())
                if not schema.access_sessions(sessions):
                    raise ValueError()
                self.access_sessions = sessions
            except (ValueError, UnicodeError):
                # Never revive revoked tokens from a historical backup.
                logging.getLogger(__name__).warning('Invalid access-session state; all interface sessions invalidated')
                save_json(self.access_sessions_path, {})
        for entry in self.items:
            entry.setdefault('id', self.entry_id(entry))

    def allow_login(self, peer):
        with self.auth_lock:
            now = time.monotonic()
            self.login_attempts = {k: [t for t in v if now - t < 300] for k, v in self.login_attempts.items() if v and now - v[-1] < 300}
            if len(self.login_attempts) >= 1024 and peer not in self.login_attempts:
                return False
            attempts = self.login_attempts.setdefault(peer, [])
            if len(attempts) >= 10 or sum(map(len, self.login_attempts.values())) >= 100:
                return False
            attempts.append(now)
            return True

    def access_cookie(self, now=None):
        with self.auth_lock:
            current = time.time() if now is None else now
            expiry = int(current) + ACCESS_DAYS * 86400
            nonce = secrets.token_hex(24)
            self.access_sessions = {k: v for k, v in self.access_sessions.items() if v > current}
            if len(self.access_sessions) >= 256:
                del self.access_sessions[min(self.access_sessions, key=self.access_sessions.get)]
            self.access_sessions[nonce] = expiry
            save_json(self.access_sessions_path, self.access_sessions)
            signature = hmac.new(self._auth_secret, f'{expiry}:{nonce}:{self.password}'.encode(), hashlib.sha256).hexdigest()
            return f'{expiry}.{nonce}.{signature}'

    def valid_access_cookie(self, value):
        with self.auth_lock:
            try:
                expiry, nonce, signature = value.split('.')
                if int(expiry) <= time.time() or self.access_sessions.get(nonce) != int(expiry):
                    return False
                expected = hmac.new(self._auth_secret, f'{expiry}:{nonce}:{self.password}'.encode(), hashlib.sha256).hexdigest()
                return hmac.compare_digest(expected, signature)
            except (ValueError, TypeError):
                return False

    def revoke_access_cookie(self, value):
        with self.auth_lock:
            try:
                _, nonce, _ = value.split('.')
            except ValueError:
                return
            self.access_sessions.pop(nonce, None)
            save_json(self.access_sessions_path, self.access_sessions)

    def session_fingerprint(self):
        return hashlib.sha256(self.state_path.read_bytes()).hexdigest()

    def manifest_signature(self):
        path = child_path(self.output, 'hi10-manifest.json')
        try:
            stat = path.stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def _read_manifest(self):
        path = child_path(self.output, 'hi10-manifest.json')
        return load_json(path, schema.manifest) if path.exists() else {}

    def cached_manifest(self, check_disk=True):
        if check_disk:
            signature = self.manifest_signature()
            if signature != self._manifest_signature:
                self._manifest_cache = self._read_manifest()
                self._manifest_signature = signature
                self._summaries.clear()
                self.touch_library()
        return self._manifest_cache

    def save_manifest(self, manifest, project_id):
        with self.lock:
            save_json(child_path(self.output, 'hi10-manifest.json'), manifest)
            self._manifest_cache = manifest
            self._manifest_signature = self.manifest_signature()
            self._summaries.pop(project_id, None)
            # Updating one completed project's counts must not invalidate the entire library.
            project = self.get_project(project_id)
            summary = self.summary_for(project)
            self.catalog['projects'][self.project_position(project_id)]['_summary'] = summary
            self.touch_library(project_id)

    def touch_library(self, project_id=None):
        self.library_version += 1
        self._library_payload = None
        if project_id is None:
            self._full_revision = self.library_version
            self._changes.clear()
        else:
            self._changes.append((self.library_version, project_id))

    def project_position(self, project_id):
        position = self._positions.get(project_id)
        projects = self.catalog['projects']
        if position is None or position >= len(projects) or projects[position]['id'] != project_id:
            self._positions = {p['id']: index for index, p in enumerate(projects)}
            position = self._positions.get(project_id)
        if position is None:
            raise ValueError('Project not found. Refresh the library.')
        return position

    def remember_project(self, project):
        self._details[project['id']] = project
        self._details.move_to_end(project['id'])
        while len(self._details) > 8:
            self._details.popitem(last=False)
        return project

    def load_project(self, entry):
        if 'variants' in entry:
            return entry
        project_id = entry['id']
        if project_id in self._details:
            self._details.move_to_end(project_id)
            return self._details[project_id]
        path = child_path(self.project_dir, project_id + '.json')
        return self.remember_project(load_json(path))

    def store_project(self, project, refresh_summary=True):
        if refresh_summary:
            self._summaries.pop(project['id'], None)
        summary = self.summary_for(project)
        data = {k: v for k, v in project.items() if k not in {'_summary', '_detail'}}
        save_json(child_path(self.project_dir, project['id'] + '.json'), data)
        self.remember_project(project)
        entry = {k: project[k] for k in ('id', 'url', 'title', 'folder', 'scanned', 'error', 'preferred') if k in project}
        entry.update(_detail=True, _summary=summary)
        self.catalog['projects'][self.project_position(project['id'])] = entry
        self.touch_library(project['id'])

    def write_index(self):
        data = {k: v for k, v in self.catalog.items() if k != 'manifest_signature'}
        data['schema_version'] = 2
        data['manifest_signature'] = list(self._manifest_signature or ())
        save_json(self.catalog_path, data)

    def warm_library(self):
        with self.lock:
            ids = [p['id'] for p in self.catalog['projects']]
            self.job['total'] = len(ids)
            if all(pid in self._summaries for pid in ids) and not any('variants' in p and p.get('scanned') for p in self.catalog['projects']):
                self.job.update(done=len(ids), message='Saved library restored from cache')
                return
        for index, project_id in enumerate(ids):
            if self.cancel.is_set():
                return
            with self.lock:
                entry = self.catalog['projects'][self.project_position(project_id)]
                if project_id not in self._summaries:
                    project = self.load_project(entry)
                    self.summary_for(project)
                if 'variants' in entry and entry.get('scanned'):
                    self.store_project(entry, refresh_summary=False)  # One-time migration from the old monolithic library.
                else:
                    entry['_summary'] = self._summaries[project_id]
                    entry.update({k: self._summaries[project_id].get(k) for k in ('title', 'scanned', 'error')})
                self.job.update(done=index + 1, message=f'Restoring library · {index + 1} / {len(ids)}')
            self.shutdown.wait(0.001)  # Let status/control requests acquire the lock between projects.
        with self.lock:
            self.write_index()
            self.touch_library()

    def restore(self):
        self._restoring = True
        try:
            self.warm_library()
            if self.state_path.exists() and not self.cancel.is_set():
                self.verify(force=True)
        finally:
            self._restoring = False

    def start_services(self):
        self._restoring = True
        self.start_job('restore', self.restore)
        scheduler = Thread(target=self.scheduler_loop, daemon=True, name='download-scheduler')
        self.workers.append(scheduler)
        scheduler.start()

    @staticmethod
    def entry_id(entry):
        item = entry.get('file', {})
        path = f"{entry.get('folder', '')}/{item.get('subfolder', '')}/{entry.get('filename', '')}"
        return hashlib.sha256(path.encode()).hexdigest()[:20]

    def pending_count(self):
        excluded = set(self.catalog.get('excluded_ids', []))
        return sum(e['status'] in {'queued', 'interrupted', 'failed'} and e.get('project_id') not in excluded for e in self.items)

    def save_queue(self):
        self._queue_groups_cache.clear()
        save_json(self.jobs_path, self.items)

    def set_schedule(self, value):
        try:
            target = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if target.tzinfo is None:
                raise ValueError()
            timestamp = target.timestamp()
        except (ValueError, AttributeError, OverflowError):
            raise ValueError('Choose a valid date and time with a timezone.') from None
        if timestamp <= time.time():
            raise ValueError('Choose a future start time.')
        if not self.pending_count():
            raise ValueError('Add files to the queue first.')
        self.schedule = {'starts_at': timestamp, 'message': 'Scheduled. The server and container must be running.'}
        save_json(self.schedule_path, self.schedule)
        self.scheduler_wake.set()

    def cancel_schedule(self):
        self.schedule = {'starts_at': None, 'message': ''}
        save_json(self.schedule_path, self.schedule)
        self.scheduler_wake.set()

    def start_due(self, now=None):
        with self.lock:
            target = self.schedule.get('starts_at')
            if target is None or target > (time.time() if now is None else now):
                return False
            if self.download_job['running'] or (self.job['running'] and self.job['kind'] != 'scan'):
                return False
            if not self.pending_count():
                self.cancel_schedule()
                return False
            # Only an explicitly saved schedule can auto-start after a container restart.
            self.start_downloads()
            return True

    def scheduler_loop(self):
        while not self.shutdown.is_set():
            try:
                self.start_due()
            except Exception:
                with self.lock:
                    self.schedule['message'] = 'Scheduled start needs attention. Check your saved session and queue.'
            with self.lock:
                target = self.schedule.get('starts_at')
                delay = 60 if target is None else max(2, min(60, target - time.time()))
            self.scheduler_wake.wait(delay)
            self.scheduler_wake.clear()

    def request_shutdown(self):
        self.shutdown.set()
        self.scheduler_wake.set()
        self.cancel.set()
        self.download_cancel.set()

    def close(self, timeout=65):
        self.request_shutdown()
        deadline = time.monotonic() + timeout
        for thread in list(self.workers):
            thread.join(max(0, deadline - time.monotonic()))
        if self.browser and self.browser.active and time.monotonic() < deadline:
            try:
                self.browser.call('close', timeout=max(.1, deadline - time.monotonic()))
            except ValueError:
                logging.getLogger(__name__).warning('Login browser did not finish closing before shutdown')
        if any(thread.is_alive() for thread in self.workers):
            logging.getLogger(__name__).warning('Shutdown deadline reached; unfinished work will be recovered on startup')
