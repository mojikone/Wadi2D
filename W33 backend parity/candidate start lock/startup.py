"""The first touch of the GPU in a process, one process at a time.

Interface: :func:`cuda_device_count`.

Two processes starting CUDA at the same moment crash one of them with an access violation on this machine's driver
(W33: 6 of 16 processes in racing pairs, at the first device query; importing CuPy or loading NVRTC is safe). The first
device query of each process therefore runs under a lock file every Wadi2D process shares, which brings it to 0 of 36.
After that the processes use the card together as before.
"""

from __future__ import annotations

import os
import tempfile
import time
from functools import cache
from pathlib import Path

LOCK_NAME = "wadi2d_cuda_start.lock"
POLL_S = 0.05
WAIT_LIMIT_S = 120.0
"""A start-up that holds the lock longer than this is taken as hung: the waiter starts anyway, as it would have before."""


def lock_path() -> Path:
    return Path(tempfile.gettempdir()) / LOCK_NAME


class _StartLock:
    """An exclusive lock on one byte of the shared lock file, released when the block ends."""

    def __init__(self, path: Path, wait_limit_s: float = WAIT_LIMIT_S) -> None:
        self.path, self.wait_limit_s = path, wait_limit_s
        self.fd: int | None = None
        self.held = False

    def __enter__(self) -> _StartLock:
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        deadline = time.monotonic() + self.wait_limit_s
        while not self._try():
            if time.monotonic() > deadline:
                break
            time.sleep(POLL_S)
        return self

    def _try(self) -> bool:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        self.held = True
        return True

    def __exit__(self, *_exc) -> None:
        if self.held:
            if os.name == "nt":
                import msvcrt

                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


@cache
def cuda_device_count() -> int:
    """How many CUDA devices CuPy sees; the first call starts the context of device 0 under the shared lock.

    Raises what CuPy raises when it cannot load, as the callers expect.
    """
    with _StartLock(lock_path()):
        import cupy as cp  # inside the lock: a CuPy loading beside another process's first device query crashes too

        count = cp.cuda.runtime.getDeviceCount()
        if count > 0:
            _ = cp.cuda.Device().compute_capability
    return count
