"""How to take a window out of the chunk store: mapped chunks against plain file reads, over a whole block.

Args: store_folder(dem_*) variant(map|file|reuse|filereuse|ahead) workers [limit]. Windows of 1,857 pixels on the table build's lattice of
1,280, in the build's order, wherever all the chunks under a window hold data. ``map`` is the store's own ``take``
(chunks mapped, ``OPEN_CHUNKS`` of them held); ``file`` reads the rows a window needs from each chunk file into a
buffer of the thread's own and copies from there; ``reuse`` is ``map`` into arrays the thread keeps, so no window
costs fresh pages from the system; ``ahead`` is ``reuse`` with the rows a window needs asked of the system in one
request before they are touched (Windows' PrefetchVirtualMemory), for a store that is not in the file cache
(``evict_store.py`` puts it out).
"""

import ctypes
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

import wadi2d.demstore.chunks as chunks_mod
from wadi2d.demstore.chunks import CHUNK, ChunkStore, _copy, span

folder, variant, workers = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
limit = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9
chunks_mod.OPEN_CHUNKS = int(os.environ.get("W84_OPEN_CHUNKS", chunks_mod.OPEN_CHUNKS))
SIZE, PITCH, HUGE = 1857, 1280, 1e30

have = {(int(p.name[1:6]), int(p.name[8:13])) for p in folder.glob("r*.npy")}
rows = [r for r, _ in have]
cols = [c for _, c in have]
store = ChunkStore(Path("unused.tif"), folder, ((max(rows) + 1) * CHUNK, (max(cols) + 1) * CHUNK), "float32")
windows = []
for row in range(min(rows) * CHUNK, (max(rows) + 1) * CHUNK - SIZE, PITCH):
    for col in range(min(cols) * CHUNK, (max(cols) + 1) * CHUNK - SIZE, PITCH):
        if all(key in have for key in store.keys(row, col, 1, SIZE, SIZE)):
            windows.append((row, col))
windows = windows[:limit]

local = threading.local()
offsets: dict[tuple[int, int], int] = {}


def offset_of(path: Path) -> int:
    with open(path, "rb") as f:
        np.lib.format.read_magic(f)
        np.lib.format.read_array_header_1_0(f)
        return f.tell()


def take_file(row: int, col: int, z: np.ndarray, mask: np.ndarray) -> None:
    buf = getattr(local, "buf", None)
    if buf is None:
        buf = local.buf = np.empty((CHUNK, CHUNK), np.float32)
    nr, nc = z.shape
    for cr in range(row // CHUNK, (row + nr - 1) // CHUNK + 1):
        i0, i1 = span(row, 1, nr, cr * CHUNK, (cr + 1) * CHUNK)
        for cc in range(col // CHUNK, (col + nc - 1) // CHUNK + 1):
            j0, j1 = span(col, 1, nc, cc * CHUNK, (cc + 1) * CHUNK)
            path, _void = store._paths((cr, cc))
            shape = store._shape((cr, cc))
            if shape not in offsets:
                offsets[shape] = offset_of(path)
            part = buf[: i1 - i0, : shape[1]]
            with open(path, "rb", buffering=0) as f:
                f.seek(offsets[shape] + (row + i0 - cr * CHUNK) * shape[1] * 4)
                f.readinto(memoryview(part).cast("B"))
            _copy(part, 0, col + j0 - cc * CHUNK, 1, i1 - i0, j1 - j0, z, mask, i0, j0, HUGE)


class _Range(ctypes.Structure):
    _fields_ = [("address", ctypes.c_void_p), ("size", ctypes.c_size_t)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.PrefetchVirtualMemory.argtypes = [
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(_Range),
    ctypes.c_ulong,
]
_kernel32.PrefetchVirtualMemory.restype = ctypes.c_int
_kernel32.GetCurrentProcess.restype = ctypes.c_void_p
_ME = _kernel32.GetCurrentProcess()


def take_ahead(row: int, col: int, z: np.ndarray, mask: np.ndarray) -> None:
    nr, nc = z.shape
    for cr in range(row // CHUNK, (row + nr - 1) // CHUNK + 1):
        i0, i1 = span(row, 1, nr, cr * CHUNK, (cr + 1) * CHUNK)
        for cc in range(col // CHUNK, (col + nc - 1) // CHUNK + 1):
            j0, j1 = span(col, 1, nc, cc * CHUNK, (cc + 1) * CHUNK)
            held = store.chunk((cr, cc))
            r0, c0 = row + i0 - cr * CHUNK, col + j0 - cc * CHUNK
            first = held.ctypes.data + (r0 * held.shape[1] + c0) * held.itemsize
            size = ((i1 - i0 - 1) * held.shape[1] + (j1 - j0)) * held.itemsize
            _kernel32.PrefetchVirtualMemory(_ME, 1, ctypes.byref(_Range(first, size)), 0)
            _copy(held, r0, c0, 1, i1 - i0, j1 - j0, z, mask, i0, j0, HUGE)


def one(window) -> float:
    if variant in ("reuse", "filereuse", "ahead"):
        held = getattr(local, "held", None)
        if held is None:
            held = local.held = (np.zeros((SIZE, SIZE)), np.ones((SIZE, SIZE), bool))
        z, mask = held
    else:
        z = np.zeros((SIZE, SIZE))
        mask = np.ones((SIZE, SIZE), bool)
    if variant in ("map", "reuse"):
        store.take(window[0], window[1], 1, z, mask, HUGE)
    elif variant == "ahead":
        take_ahead(window[0], window[1], z, mask)
    else:
        take_file(window[0], window[1], z, mask)
    return float(z[::97, ::89].sum())


with ThreadPoolExecutor(workers) as pool:
    list(pool.map(one, windows[-workers:]))  # the kernel compiled, the threads started: on the last windows
    t0 = time.perf_counter()
    check = sum(pool.map(one, windows))
    wall = time.perf_counter() - t0
print(
    f"{variant:4s} w={workers:2d} open={chunks_mod.OPEN_CHUNKS}: {len(windows)} windows, {wall:6.2f} s, "
    f"{1000 * wall / len(windows):5.2f} ms a window wall, {1000 * wall * min(workers, len(windows)) / len(windows):5.1f} "
    f"ms of a thread, check {check:.6e}"
)
