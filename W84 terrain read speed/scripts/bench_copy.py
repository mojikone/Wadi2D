"""The floor of a window read: the copy kernel alone, private memory to private memory, no file and no fresh page.

Args: workers [repeats]. Each thread copies a 1,857-pixel float32 window of its own into float64 and mask arrays of
its own, again and again; what limits it is memory, not the store. Compare with bench_store_read.py's ``reuse``.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from wadi2d.demstore.chunks import _copy

workers = int(sys.argv[1])
repeats = int(sys.argv[2]) if len(sys.argv) > 2 else 200
SIZE, HUGE = 1857, 1e30
rng = np.random.default_rng(1)


def work(_i: int) -> float:
    src = (100.0 + rng.random((2048, 2048))).astype(np.float32)
    z = np.zeros((SIZE, SIZE))
    mask = np.ones((SIZE, SIZE), bool)
    _copy(src, 3, 5, 1, SIZE, SIZE, z, mask, 0, 0, HUGE)
    t0 = time.perf_counter()
    for _ in range(repeats):
        _copy(src, 3, 5, 1, SIZE, SIZE, z, mask, 0, 0, HUGE)
    return time.perf_counter() - t0


with ThreadPoolExecutor(workers) as pool:
    t0 = time.perf_counter()
    inside = list(pool.map(work, range(workers)))
print(
    f"copy alone, w={workers:2d}: {1000 * sum(inside) / (workers * repeats):5.2f} ms of a thread a window, "
    f"{1000 * max(inside) / (repeats * workers):5.2f} ms a window wall"
)
