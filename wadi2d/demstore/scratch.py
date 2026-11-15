"""Window arrays handed out again once nobody holds them (W84).

A bed returns a fresh float64 window and its mask from every read, 31 MB for a 20 m tile at 0.5 m. Fresh memory of
that size comes from the system page by page as it is first written, and on Windows the threads of one process take
those pages one after another: a window read from the chunk store cost 15 ms of a thread alone and 76 ms on 16 threads,
most of it waiting for pages. The readers (a tile of the tables, a tile of the products' ground) drop a window before
they read the next, so a thread's last pair of arrays is given out again when it is free.

Free is not assumed, it is counted: the arrays are handed out again only when the interpreter holds no reference to
them but this module's own. Every way of keeping a window alive holds one: the array itself, a slice or any other
view of it (a view refers to the array that owns the memory), a memoryview. So a caller who keeps a window keeps it;
the next read then takes fresh arrays, as before. The count is checked against one measured at import on arrays held
the same way, with and without a view; if the interpreter does not count as expected (a build without the lock that
makes the count exact, a future change) nothing is ever handed out twice.
"""

from __future__ import annotations

import sys
import threading

import numpy as np

KEEP_PIXELS = 16 << 20
"""The largest window a thread keeps for the next read: 128 MB of float64 and 16 MB of mask."""
SMALLEST_SHARE = 4
"""A window under a quarter of the kept arrays takes its own: a small window kept alive must not hold a large one."""


def _refs(pair: tuple[np.ndarray, np.ndarray]) -> tuple[int, int]:
    """How many references the interpreter counts on each array of a kept pair, this function's own included."""
    z, mask = pair
    return sys.getrefcount(z), sys.getrefcount(mask)


def _calibrate() -> tuple[int, int] | None:
    """What ``_refs`` gives for a pair nobody else holds; None when the count cannot be trusted."""
    if not getattr(sys, "_is_gil_enabled", lambda: True)():
        return None
    pair = (np.zeros(4), np.ones(4, bool))
    alone = _refs(pair)
    view = pair[0].reshape(-1)[:2].reshape(1, 2)  # how a kept array goes out: a view of a view of it
    with_view = _refs(pair)
    other = pair[1]
    with_both = _refs(pair)
    del view, other
    counted = with_view == (alone[0] + 1, alone[1]) and with_both == (alone[0] + 1, alone[1] + 1)
    return alone if counted and _refs(pair) == alone else None


_ALONE = _calibrate()


class Scratch:
    """One thread's last window arrays, per thread; ``arrays`` gives them again when they are free."""

    def __init__(self) -> None:
        self._local = threading.local()

    def arrays(self, nrows: int, ncols: int) -> tuple[np.ndarray, np.ndarray, bool]:
        """A float64 (nrows, ncols) array and a bool one, and whether they are used ones: used arrays hold
        whatever the last window left in them, fresh ones hold zeros and True."""
        n = nrows * ncols
        held = getattr(self._local, "held", None)
        if (
            held is not None
            and _ALONE is not None
            and n <= held[0].size <= SMALLEST_SHARE * n
            and _refs(held) == _ALONE
        ):
            z = held[0].reshape(-1)[:n].reshape(nrows, ncols)
            mask = held[1].reshape(-1)[:n].reshape(nrows, ncols)
            return z, mask, True
        z = np.zeros((nrows, ncols), np.float64)
        mask = np.ones((nrows, ncols), bool)
        if 0 < n <= KEEP_PIXELS:
            self._local.held = (z, mask)
        return z, mask, False
