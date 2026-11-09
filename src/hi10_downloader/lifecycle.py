"""Exclusive service ownership of private state and download manifests (Linux)."""
import fcntl
from pathlib import Path


class ServiceLocks:
    def __init__(self, config, output):
        self.files = []
        try:
            for directory in sorted({Path(config).resolve(), Path(output).resolve()}):
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / '.hi10-service.lock'
                descriptor = path.open('a')
                self.files.append(descriptor)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Another Hi10 service owns this appdata or download directory.') from None
        except Exception:
            self.close()
            raise

    def close(self):
        for descriptor in self.files:
            descriptor.close()
        self.files.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
