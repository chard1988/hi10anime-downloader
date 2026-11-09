import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from threading import Event
import unittest
import urllib.request

from hi10_downloader.storage import load_json, save_json
from hi10_downloader.lifecycle import ServiceLocks
from hi10_downloader.web import Application


class StorageTests(unittest.TestCase):
    def test_backup_recovery_preserves_damaged_original_privately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'queue.json'
            save_json(path, ['first'])
            save_json(path, ['second'])
            path.write_text('{truncated')
            self.assertEqual(load_json(path), ['first'])
            self.assertEqual(path.with_name('queue.json.corrupt').read_text(), '{truncated')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.with_name('queue.json.bak').stat().st_mode & 0o777, 0o600)
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_invalid_structure_recovers_and_missing_backup_preserves_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'queue.json'
            save_json(path, [])
            save_json(path, {'wrong': 'schema'})
            self.assertEqual(load_json(path, lambda data: isinstance(data, list)), [])
            other = Path(directory) / 'broken.json'
            other.write_text('{bad')
            with self.assertRaisesRegex(ValueError, 'Restore it'):
                load_json(other)
            self.assertEqual(other.read_text(), '{bad')

    def test_invalid_current_file_does_not_replace_good_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            save_json(path, {'v': 1}); save_json(path, {'v': 2})
            path.write_text('{bad')
            save_json(path, {'v': 3})
            self.assertEqual(json.loads(path.with_name('state.json.bak').read_text()), {'v': 1})


class LifecycleTests(unittest.TestCase):
    def test_conflicting_resource_locks_are_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = ServiceLocks(root/'config', root/'output')
            try:
                with self.assertRaisesRegex(ValueError, 'Another Hi10 service'):
                    ServiceLocks(root/'other-config', root/'output')
            finally:
                first.close()
            second = ServiceLocks(root/'config', root/'output')
            second.close()

    def test_shutdown_cancels_and_joins_both_workers_and_rejects_new_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Application(root/'config', root/'output', password='test')
            entered_scan, entered_download = Event(), Event()
            def scan():
                entered_scan.set(); app.cancel.wait(3)
            def download():
                entered_download.set(); app.download_cancel.wait(3)
            app.start_job('scan', scan); app.start_job('download', download)
            self.assertTrue(entered_scan.wait(1)); self.assertTrue(entered_download.wait(1))
            app.close(timeout=2)
            self.assertFalse(any(t.is_alive() for t in app.workers))
            self.assertTrue(app.shutdown.is_set())
            with self.assertRaisesRegex(ValueError, 'shutting down'):
                app.start_job('scan', lambda: None)

    def test_real_service_health_sigterm_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with socket.socket() as available:
                available.bind(('127.0.0.1', 0)); port = available.getsockname()[1]
            command = [sys.executable, '-m', 'hi10_downloader.web', '--host', '127.0.0.1', '--port', str(port), '--config', str(root/'config'), '--output', str(root/'output')]
            for _ in range(2):
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, 'HI10_WEB_PASSWORD': 'test-do-not-print'})
                try:
                    deadline = time.monotonic() + 8
                    while True:
                        try:
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=.5) as response:
                                self.assertEqual(json.load(response), {'status': 'ok'})
                            break
                        except OSError:
                            if process.poll() is not None or time.monotonic() >= deadline:
                                self.fail('Local service failed to become healthy')
                            time.sleep(.05)
                    process.send_signal(signal.SIGTERM)
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, stderr.decode())
                    self.assertNotIn(b'test-do-not-print', stdout + stderr)
                finally:
                    if process.poll() is None:
                        process.kill(); process.communicate()
