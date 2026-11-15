"""ChunkStore: a raster's pixels decoded once and kept raw beside the grid cache (W84).

A compressed DEM is decoded block by block on every read: on Block 2 (LZW, 128-pixel blocks, no overviews) the domain
mask, the tables, the strip tables and the products' ground each decoded the same ground again, the tables twice
over where the tiles' windows overlap, and the threads shared nothing. Here a chunk of ``CHUNK`` x ``CHUNK`` pixels
is read through GDAL the first time any window touches it, written as a raw array, and mapped from then on by every
thread and every later process. Only the chunks a job touches are made.

What is kept is what GDAL gave: the file's own values in the file's own type, NaN where GDAL's mask says no data. A
reader that tells bad pixels by 'not finite' therefore finds the pixels the masked read gave it. The source file is
never written to, and nothing is written beside it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from collections import OrderedDict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from numba import njit
from rasterio.windows import Window

from wadi2d.io.identity import file_identity

CHUNK = 2048
"""Pixels along a chunk: 16 of the usual 128-pixel blocks, 16 MB of float32, about one square km at 0.5 m."""
STORE_FORMAT = "1"
"""1: raw .npy chunks in the source's type, NaN where masked, an empty .void file for a chunk with no data."""
OPEN_CHUNKS = 96
"""Chunks a process keeps mapped: address space and file cache the system can take back, not memory it must hold."""
FILL_WORKERS = max(1, (os.cpu_count() or 2) // 2)
"""Threads that decode missing chunks ahead of a read that needs many, each on its own handle of the raster."""
STORE_ENV = "WADI2D_DEM_STORE"
"""Set to 0 to read the raster through GDAL every time, as before W84."""
AHEAD_CHUNKS = 16
"""A window over this many chunks has its missing ones made ahead on ``FILL_WORKERS`` threads; a smaller one makes
them as it meets them, on the thread that reads (the tiles of a table build are already on every core)."""
LOCK_STRIPES = 64
FLOATS = ("float32", "float64")
"""Types a store holds: the reader marks no-data as NaN, which an integer cannot carry."""

Key = tuple[int, int]
"""(chunk row, chunk column)."""
_MISSING = object()


def enabled() -> bool:
    return os.environ.get(STORE_ENV, "").strip().lower() not in ("0", "off", "false", "no")


@njit(cache=True, nogil=True)
def _copy(src, r0, c0, step, nr, nc, z, mask, zr, zc, huge):
    """``nr`` x ``nc`` pixels of ``src`` from (r0, c0), every ``step``-th, into ``z`` and ``mask`` at (zr, zc): the
    value as float64, or 0 and masked where it is not finite or above ``huge``. Every pixel is stored without a
    branch, so the row is copied at the speed of memory, and a row that held a bad pixel is put right after."""
    for i in range(nr):
        bad = 0
        for j in range(nc):
            v = np.float64(src[r0 + i * step, c0 + j * step])
            b = not (v <= huge and v > -np.inf)  # NaN fails both comparisons
            z[zr + i, zc + j] = v
            mask[zr + i, zc + j] = b
            bad += b
        if bad:
            for j in range(nc):
                if mask[zr + i, zc + j]:
                    z[zr + i, zc + j] = 0.0


def _span(first: int, step: int, count: int, lo: int, hi: int) -> tuple[int, int]:
    """Which of the samples ``first + i * step``, i < ``count``, lie in [lo, hi): the range of i."""
    a = max(0, -((first - lo) // step))
    b = min(count, -((first - hi) // step))
    return a, b


class ChunkStore:
    """One raster's chunks in one folder. Safe across threads, and across processes: a chunk is written under a
    name of its own and renamed into place, and two writers of one chunk write the same bytes."""

    def __init__(self, source: Path, folder: Path, shape: tuple[int, int], dtype: str) -> None:
        self.source, self.folder = Path(source), Path(folder)
        self.height, self.width = shape
        self.dtype = np.dtype(dtype)
        self._lock = threading.Lock()
        self._open: OrderedDict[Key, np.ndarray | None] = OrderedDict()
        self._stripes = [threading.Lock() for _ in range(LOCK_STRIPES)]
        self.filled = 0
        """Chunks this process decoded from the source."""

    # Where a chunk lies.

    def _paths(self, key: Key) -> tuple[Path, Path]:
        stem = f"r{key[0]:05d}_c{key[1]:05d}"
        return self.folder / f"{stem}.npy", self.folder / f"{stem}.void"

    def _shape(self, key: Key) -> tuple[int, int]:
        return min(CHUNK, self.height - key[0] * CHUNK), min(CHUNK, self.width - key[1] * CHUNK)

    def keys(self, row: int, col: int, step: int, nr: int, nc: int) -> list[Key]:
        """The chunks under ``nr`` x ``nc`` samples from native (row, col), ``step`` pixels apart."""
        rows = range(row // CHUNK, (row + (nr - 1) * step) // CHUNK + 1)
        cols = range(col // CHUNK, (col + (nc - 1) * step) // CHUNK + 1)
        return [(r, c) for r in rows for c in cols]

    # A chunk: from memory, from disk, from the source.

    def chunk(self, key: Key) -> np.ndarray | None:
        """The chunk's pixels, read-only; None when it holds no data at all."""
        with self._lock:
            held = self._open.get(key, _MISSING)
            if held is not _MISSING:
                self._open.move_to_end(key)
                return held
        with self._stripes[hash(key) % LOCK_STRIPES]:  # one thread makes a chunk; the others wait for it
            with self._lock:
                held = self._open.get(key, _MISSING)
            if held is _MISSING:
                held = self._load(key)
                if held is _MISSING:
                    held = self._fill(key)
                with self._lock:
                    self._open[key] = held
                    while len(self._open) > OPEN_CHUNKS:
                        self._open.popitem(last=False)
        return held

    def _load(self, key: Key):
        path, void = self._paths(key)
        if void.is_file():
            return None
        if not path.is_file():
            return _MISSING
        try:
            held = np.load(path, mmap_mode="r")
        except (OSError, ValueError, EOFError):
            return _MISSING  # cut short or not ours: made again, and replaced if the system lets go of it
        if held.shape != self._shape(key) or held.dtype != self.dtype:
            return _MISSING
        return np.asarray(held)

    def _fill(self, key: Key) -> np.ndarray | None:
        """Decode the chunk from the source and keep it. A chunk that cannot be written (a full or read-only disk) is
        still returned: the store then saves nothing, and loses nothing."""
        height, width = self._shape(key)
        # a handle of its own, closed at once: a raster handle is not safe across threads, and a handle kept would
        # keep the decoded blocks in GDAL's cache, which nothing reads twice
        with rasterio.open(self.source) as src:
            read = src.read(1, window=Window(key[1] * CHUNK, key[0] * CHUNK, width, height), masked=True)
        values = np.ascontiguousarray(read.filled(np.nan), dtype=self.dtype)
        with self._lock:
            self.filled += 1
        path, void = self._paths(key)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        nothing = bool(np.isnan(values).all())
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as f:
                if not nothing:
                    np.save(f, values)
                    f.flush()
                    # on disk before it has its name: a power cut leaves no chunk of zeros
                    os.fsync(f.fileno())
            try:
                os.replace(tmp, void if nothing else path)
            except OSError:  # another process placed the same chunk and holds it open
                tmp.unlink(missing_ok=True)
        except OSError:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            return None if nothing else values
        if nothing:
            return None
        held = self._load(key)
        return values if held is _MISSING else held

    def _known(self, key: Key) -> bool:
        with self._lock:
            if key in self._open:
                return True
        path, void = self._paths(key)
        return path.is_file() or void.is_file()

    def ensure(self, keys: Iterable[Key], workers: int | None = None) -> int:
        """Make the chunks of ``keys`` that are missing, on ``workers`` threads (``FILL_WORKERS``); how many were."""
        workers = FILL_WORKERS if workers is None else workers
        missing = [key for key in dict.fromkeys(keys) if not self._known(key)]
        if len(missing) > 1 and workers > 1:
            with ThreadPoolExecutor(min(workers, len(missing))) as pool:
                for _ in pool.map(self.chunk, missing):
                    pass
        return len(missing)

    # Pixels.

    def take(
        self,
        row: int,
        col: int,
        step: int,
        z: np.ndarray,
        mask: np.ndarray,
        huge: float,
        wanted: np.ndarray | None = None,
    ) -> None:
        """Fill ``z`` and ``mask`` (the same shape, every sample inside the raster) with the pixels at native
        (row + i * step, col + j * step); every element of both is written, whatever they held. Under a chunk with
        no data they are 0 and True. With ``wanted``, so they are under a chunk none of whose samples is wanted,
        and that chunk is never made."""
        nr, nc = z.shape
        if nr == 0 or nc == 0:
            return
        if wanted is None:
            keys = self.keys(row, col, step, nr, nc)
            if (
                len(keys) >= AHEAD_CHUNKS
            ):  # one large window, a strip of tiles read whole: decoded on every core
                self.ensure(keys)
        for cr in range(row // CHUNK, (row + (nr - 1) * step) // CHUNK + 1):
            i0, i1 = _span(row, step, nr, cr * CHUNK, (cr + 1) * CHUNK)
            if i1 <= i0:
                continue
            for cc in range(col // CHUNK, (col + (nc - 1) * step) // CHUNK + 1):
                j0, j1 = _span(col, step, nc, cc * CHUNK, (cc + 1) * CHUNK)
                if j1 <= j0:
                    continue
                skipped = wanted is not None and not wanted[i0:i1, j0:j1].any()
                held = None if skipped else self.chunk((cr, cc))
                if held is None:
                    z[i0:i1, j0:j1] = 0.0
                    mask[i0:i1, j0:j1] = True
                    continue
                _copy(held, row + i0 * step - cr * CHUNK, col + j0 * step - cc * CHUNK, step, i1 - i0, j1 - j0,
                      z, mask, i0, j0, huge)  # fmt: skip


_STORES: dict[str, ChunkStore] = {}
_STORES_LOCK = threading.Lock()


def store_key(source: Path, src, content_limit_mb: float) -> str:
    """What a store belongs to: the file as it stands (its size and time, its content when small), its name, its
    grid and its type. Not its folder: a DEM moved with its date keeps its store, as it keeps its grid cache."""
    text = json.dumps(
        {
            "store": STORE_FORMAT,
            "chunk": CHUNK,
            "name": source.name,
            "file": file_identity(source, content_limit_mb),
            "shape": [src.height, src.width],
            "dtype": src.dtypes[0],
            "transform": list(src.transform)[:6],
        },
        sort_keys=True,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def store_for(
    source: str | Path, src, cache_dir: str | Path | None, content_limit_mb: float
) -> ChunkStore | None:
    """The store of the raster open as ``src``, under ``cache_dir``; None when there is no cache folder, the store is
    switched off, or the raster is not one it can hold. One object per folder in a process, so its threads share
    the chunks they map and wait for the chunk another is making."""
    if cache_dir is None or not enabled() or src.dtypes[0] not in FLOATS:
        return None
    source = Path(source)
    folder = Path(cache_dir) / f"dem_{store_key(source, src, content_limit_mb)}"
    with _STORES_LOCK:
        store = _STORES.get(str(folder))
        if store is None:
            store = _STORES[str(folder)] = ChunkStore(source, folder, (src.height, src.width), src.dtypes[0])
            _describe(store)
    return store


def _describe(store: ChunkStore) -> None:
    """A note in the folder saying what it is, for whoever finds 16 MB files in a cache."""
    note = store.folder / "source.json"
    try:
        store.folder.mkdir(parents=True, exist_ok=True)
        if not note.is_file():
            stat = store.source.stat()
            note.write_text(
                json.dumps(
                    {
                        "what": "Wadi2D working copy of a terrain raster: raw pixel chunks, made on first read. "
                        "Safe to delete; it is made again.",
                        "source": str(store.source),
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "chunk_pixels": CHUNK,
                        "format": STORE_FORMAT,
                    },
                    indent=1,
                ),
                encoding="utf-8",
            )
    except OSError:
        pass  # a folder that cannot be written: the store reads through and keeps nothing
