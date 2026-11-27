"""Saved batch limits and a shared, cancellable bandwidth budget."""
from threading import Lock
import time


def valid_settings(value):
    return (isinstance(value, dict) and value.get('version') == 1
            and type(value.get('speed_limit_kbps')) is int and 0 <= value['speed_limit_kbps'] <= 10000000
            and type(value.get('parallel_downloads')) is int and 1 <= value['parallel_downloads'] <= 8)


class BandwidthBudget:
    """Reserve time per chunk across all workers; no accumulated idle burst."""
    def __init__(self, kbps, cancel, cancelled, clock=time.monotonic, parallel_downloads=1):
        self.bytes_per_second = kbps * 1000 / 8
        # Keep the combined reservation of one chunk per worker near 250 ms.
        self.chunk_size = max(1, min(65536, int(self.bytes_per_second / parallel_downloads / 4))) if kbps else 65536
        self.cancel = cancel
        self.cancelled = cancelled
        self.clock = clock
        self.lock = Lock()
        self.next_slot = clock()

    def consume(self, size):
        if self.cancel.is_set():
            raise self.cancelled()
        if not self.bytes_per_second or not size:
            return
        with self.lock:
            self.next_slot = max(self.clock(), self.next_slot) + size / self.bytes_per_second
            ready = self.next_slot
        while True:
            remaining = ready - self.clock()
            if remaining <= 0:
                return
            if self.cancel.wait(min(remaining, .25)):
                raise self.cancelled()


class TransferRate:
    """Five-second rolling byte rate in fixed buckets, guarded by the app lock."""
    WINDOW = 5.0
    BUCKET = .25

    def __init__(self, clock=time.monotonic):
        from collections import deque
        self.clock = clock
        self.samples = deque()
        self.reset()

    def reset(self):
        self.samples.clear()
        self.total = 0
        self.started = self.clock()

    def _expire(self, now):
        while self.samples and self.samples[0][0] <= now - self.WINDOW:
            self.total -= self.samples.popleft()[1]

    def add(self, size):
        now = self.clock()
        self._expire(now)
        if size <= 0:
            return
        bucket = int(now / self.BUCKET) * self.BUCKET
        if self.samples and self.samples[-1][0] == bucket:
            self.samples[-1][1] += size
        else:
            self.samples.append([bucket, size])
        self.total += size

    def speed(self):
        now = self.clock()
        self._expire(now)
        elapsed = max(self.BUCKET, min(self.WINDOW, now - self.started))
        return self.total / elapsed
