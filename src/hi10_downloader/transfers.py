"""Saved batch limits and a shared, cancellable bandwidth budget."""
from threading import Lock
import time


def valid_settings(value):
    return (isinstance(value, dict) and value.get('version') == 1
            and type(value.get('speed_limit_kbps')) is int and 0 <= value['speed_limit_kbps'] <= 10000000
            and type(value.get('parallel_downloads')) is int and 1 <= value['parallel_downloads'] <= 8)


class BandwidthBudget:
    """Reserve time per chunk across all workers; no accumulated idle burst."""
    def __init__(self, kbps, cancel, cancelled, clock=time.monotonic):
        self.bytes_per_second = kbps * 1000 / 8
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
