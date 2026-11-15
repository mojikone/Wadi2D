"""Tables built on every core (W81): tiles and strip pieces go to a pool of threads, each with its own handle on the
bed, the kernels serial and free of the interpreter lock inside them.

A tile's tables depend on its own pixels alone and land in its own slots of the output arrays, so the order the
threads take them in changes nothing: the tables are the one-thread build's to the digit (the tests compare).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

TABLE_WORKERS = max(1, (os.cpu_count() or 2) // 2)
"""Threads of a table build: one per physical core of a two-way SMT machine. The environment variable
``WADI2D_TABLE_WORKERS`` overrides it; 1 builds on the calling thread, as before W81."""
TABLE_WORKERS_ENV = "WADI2D_TABLE_WORKERS"


def table_workers(workers: int | None = None) -> int:
    """The threads a build uses: ``workers`` when given, else the environment's, else ``TABLE_WORKERS``."""
    if workers is not None:
        return max(1, int(workers))
    given = os.environ.get(TABLE_WORKERS_ENV, "").strip()
    return max(1, int(given)) if given else TABLE_WORKERS


class ThreadBeds:
    """One bed per thread: a bed with ``reopen`` (a raster, whose handle is not safe across threads) is opened again
    on each worker thread that reads it, the thread that made this keeps the bed itself (it only waits while the
    workers run), any other bed is shared. ``close`` closes the handles it opened."""

    def __init__(self, bed) -> None:
        self.bed = bed
        self._owner = threading.get_ident()
        self._local = threading.local()
        self._opened: list = []
        self._lock = threading.Lock()

    def get(self):
        if not hasattr(self.bed, "reopen") or threading.get_ident() == self._owner:
            return self.bed
        own = getattr(self._local, "bed", None)
        if own is None:
            own = self.bed.reopen()
            self._local.bed = own
            with self._lock:
                self._opened.append(own)
        return own

    def close(self) -> None:
        for bed in self._opened:
            bed.close()
        self._opened.clear()


def run_all(items: Iterable[int], work: Callable[[int], None], workers: int) -> None:
    """``work(item)`` for every item, on ``workers`` threads; the first error is raised once all have stopped."""
    items = list(items)
    if workers <= 1 or len(items) <= 1:
        for item in items:
            work(item)
        return
    with ThreadPoolExecutor(min(workers, len(items))) as pool:
        for _ in pool.map(work, items):
            pass
