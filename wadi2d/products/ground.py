"""The ground of every kept cell, pixel by pixel, and the ground of every face, from what built the tables.

Pixels come through the same ``RasterBed`` and the same pixel edits as the tables, so a burned line is burned here
too, a channel is cut and a dyke stands: a depth read on the raw DEM would be wrong in both. Elevations are held over
the lowest cell of the domain, so float32 keeps its resolution at any datum.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
import rasterio
from numba import njit
from rasterio.windows import Window
from scipy import ndimage

from wadi2d.config.schema import RunConfig
from wadi2d.demstore import cache_folder, open_bed
from wadi2d.solver.layout import CLOSED, TILE
from wadi2d.tables.builder import GridTables
from wadi2d.terrain import Ground, RasterBed, apply_objects
from wadi2d.terrain.dem import HUGE_ELEVATION
from wadi2d.terrain.sections import with_tables

READ_WORKERS = max(1, (os.cpu_count() or 2) // 2)
"""Threads that read the kept cells' ground, each on its own handle of the DEM (W50)."""
STRIPS_AHEAD = 4
"""Strips of tiles whose kept cells are with the reading threads at once. One strip has some forty tiles with cells
kept, of uneven work, and its slowest (a hole to fill) held the other threads idle for half the stage (W84)."""
READ_CACHE_MB = 256
"""GDAL's block cache while they read. Each block is read about once, so a large cache holds nothing worth keeping,
and closing the handles freed it at 1.2 s a handle: 21 s of Block 2's 32 s (W50)."""


@dataclass
class CellPixels:
    """The kept cells and their pixels; ``ground`` is (cells, k * k), rows south, over ``datum``."""

    rows: np.ndarray
    cols: np.ndarray
    k: int
    pixel: float
    datum: float
    ground: np.ndarray


def face_sills(tables: GridTables, datum: float) -> tuple[np.ndarray, np.ndarray]:
    """The ground of each west and north face over ``datum``, float32; a closed face is infinitely high."""
    grid = tables.grid
    below = (tables.zmin - datum).astype(np.float32)
    sills = []
    for over_cell in (tables.frx, tables.fry):
        over = grid.from_tiles(over_cell, CLOSED)
        sills.append(np.where(over >= CLOSED, np.inf, below + over).astype(np.float32))
    return sills[0], sills[1]


def bed_stride(cfg: RunConfig, native: float) -> int:
    """The DEM stride of the pixel maps: the job's own, unless they ask for a coarser pixel."""
    wanted = cfg.outputs.pixels.pixel_m
    if wanted <= 0.0:
        return cfg.terrain.pixel_stride
    stride = round(wanted / native)
    if stride < 1 or abs(stride * native - wanted) > 1e-6 * wanted:
        raise ValueError(f"outputs.pixels.pixel_m {wanted} is not a multiple of the DEM pixel {native}")
    return stride


def read_cells(
    cfg: RunConfig,
    tables: GridTables,
    keep: np.ndarray,
    tick: Callable[[int, int], None] = lambda _a, _b: None,
    scale: int = 1,
    datum: float | None = None,
    cache: str | Path | None = None,
) -> CellPixels:
    """The pixels of the cells in ``keep``, a strip of tiles at a time. ``tick`` may raise to stop the read.

    On a mesh ``keep`` is on a lattice of cells ``scale`` finest cells wide, and ``datum`` is shared by every size.
    ``cache`` is the run's cache folder, where the DEM's chunk store lies (W84); None takes the job's own.
    """
    grid = tables.grid
    with RasterBed(cfg.terrain.dem) as probe:
        native = probe.native
    with open_bed(cfg, cache if cache is not None else cache_folder(cfg), bed_stride(cfg, native)) as bed:
        k = bed.pixels_per_cell(grid.dx * scale)
        bed.bind(grid.x0, grid.y0)
        objects = with_tables(cfg).terrain.objects
        edit = apply_objects(grid, objects, bed.pixel, cfg.terrain, Ground(bed, grid.x0, grid.y0)).edit
        rows, cols = np.nonzero(keep)
        if datum is None:
            datum = float(tables.zmin[keep].min()) if rows.size else 0.0
        ground = np.empty((rows.size, k * k), np.float32)
        strips = rows // TILE
        first = np.searchsorted(strips, np.arange(strips.max() + 2 if rows.size else 1))
        count = len(first) - 1
        spans = [(int(first[strip]), int(first[strip + 1])) for strip in range(count)]
        with (
            rasterio.Env(GDAL_CACHEMAX=READ_CACHE_MB),
            _ThreadBeds(bed, grid.x0, grid.y0) as beds,
        ):
            # these only hand a strip's tiles to the readers and wait; with one reader, one strip at a time
            ahead = ThreadPoolExecutor(STRIPS_AHEAD if beds.workers > 1 else 1)
            try:
                picked = {
                    strip: ahead.submit(beds.pick, rows[a:b], cols[a:b], k, datum, ground[a:b])
                    for strip, (a, b) in enumerate(spans)
                    if edit is None and a < b
                }
                for strip, (a, b) in enumerate(spans):
                    tick(strip, count)
                    if a == b:
                        continue
                    if strip in picked and picked[strip].result():
                        continue
                    _whole_strip(bed, edit, rows[a:b], cols[a:b], k, strip * TILE * k, datum, ground[a:b])
            finally:
                ahead.shutdown(wait=True, cancel_futures=True)  # a stop waits for the strips in hand, not for all
    return CellPixels(rows, cols, k, bed.pixel, datum, ground)


@njit(cache=True, nogil=True)
def _any_picked(bad: np.ndarray, rows: np.ndarray, cols: np.ndarray, k: int, row0: int, col0: int) -> bool:
    """Whether any of the k x k pixels of a cell is marked in ``bad``, a window read at bed pixel (row0, col0)."""
    for n in range(rows.size):
        top, left = rows[n] * k - row0, cols[n] * k - col0
        for a in range(k):
            for b in range(k):
                if bad[top + a, left + b]:
                    return True
    return False


@njit(cache=True, nogil=True)
def _pick_into(z, rows, cols, k, row0, col0, datum, out, where) -> None:
    """The k x k pixels of each cell from ``z``, a window read at bed pixel (row0, col0), over ``datum``, into
    ``out[where[n]]`` as float32. Free of the interpreter lock and written where it belongs, so the reading threads
    pick as well as read: picked with index arrays and placed by the calling thread, 16 threads waited on one (W84:
    Block 2's ground 23 s with the read itself down to a few)."""
    for n in range(rows.size):
        top, left = rows[n] * k - row0, cols[n] * k - col0
        line = out[where[n]]
        for a in range(k):
            for b in range(k):
                line[a * k + b] = np.float32(z[top + a, left + b] - datum)


def _whole_strip(bed: RasterBed, edit, rows, cols, k: int, row0: int, datum: float, out: np.ndarray) -> None:
    """One strip of tiles read whole, from its first to its last kept column: what a terrain object edits, and
    where a kept pixel is a hole and needs the fill, whose nearest good pixel depends on the window."""
    col0 = int(cols.min()) * k
    ncols = (int(cols.max()) + 1) * k - col0
    top = (rows * k - row0)[:, None, None] + np.arange(k)[None, :, None]
    left = (cols * k - col0)[:, None, None] + np.arange(k)[None, None, :]
    # without the fill first: the cells kept are inside the DEM almost always, and the fill is a distance
    # transform of the whole strip. A strip with holes is read again with it when terrain objects edit it
    # (an edit may read the whole window, its lowest and highest ground) or when a kept pixel is a hole (W50)
    z = _read(bed, row0, col0, TILE * k, ncols, fill=False)
    holes = np.isnan(z)
    if holes.any() and (edit is not None or holes[top, left].any()):
        z = _read(bed, row0, col0, TILE * k, ncols)
    if edit is not None:
        edit(z, row0, col0)
    out[:] = (z[top, left] - datum).astype(np.float32).reshape(rows.size, -1)


FILL_MARGIN = 64
"""Pixels round a tile's kept cells first read to fill their holes from; doubled until the nearest good pixel of
every hole is provably inside (W50)."""


def _raw(bed: RasterBed, row0: int, col0: int, nrows: int, ncols: int) -> tuple[np.ndarray, np.ndarray]:
    """Bed pixels counted from the grid origin as :meth:`RasterBed.read` counts them, and which are holes, unfilled.

    Through the bed's own window reader, or at a stride through :func:`_strided_window`, which picks the same
    pixels: ``read(fill=False)`` gives a window that is all holes as zeros, not NaN, so a hole could not be told
    from ground there. ``terrain/dem.py`` is left as it is: it is hashed into every grid cache key, and editing it
    would rebuild every user's tables once for nothing. A bed on the chunk store picks those pixels itself, at any
    stride, with no decoding (W84)."""
    stored = getattr(bed, "store", None) is not None and bed.whole_pixels
    read = bed._window if bed.stride == 1 or stored else partial(_strided_window, bed)
    return read(bed.row_origin + row0 * bed.stride, bed.col_origin + col0 * bed.stride, nrows, ncols)


def _strided_window(bed: RasterBed, row: int, col: int, nrows: int, ncols: int) -> tuple[np.ndarray, np.ndarray]:
    """:meth:`RasterBed._window` at a stride, read whole and sliced. GDAL's nearest decimation of a window
    ``stride`` times the output takes the pixel at ``stride // 2`` in every block of ``stride``, so the slice is the
    same pixels, and the decimated read costs about five times the whole read (W80: Block 2 at 20 m and stride 2,
    the products' ground 40 s a strip of tiles). Same clipping, same holes, same values."""
    s = bed.stride
    skip_r = max(-(row // s), 0)
    skip_c = max(-(col // s), 0)
    nr = min(nrows - skip_r, (bed.src.height - (row + skip_r * s)) // s)
    nc = min(ncols - skip_c, (bed.src.width - (col + skip_c * s)) // s)
    z = np.zeros((nrows, ncols), np.float64)
    mask = np.ones((nrows, ncols), bool)
    if nr <= 0 or nc <= 0:
        return z, mask
    window = Window(col + skip_c * s, row + skip_r * s, nc * s, nr * s)
    a = bed.src.read(1, window=window, masked=True)[s // 2 :: s, s // 2 :: s]
    values = np.asarray(a.filled(np.nan), dtype=np.float64)
    bad = ~np.isfinite(values) | (values > HUGE_ELEVATION)
    values[bad] = 0.0
    z[skip_r : skip_r + nr, skip_c : skip_c + nc] = values
    mask[skip_r : skip_r + nr, skip_c : skip_c + nc] = bad
    return z, mask


def _read(bed: RasterBed, row0: int, col0: int, nrows: int, ncols: int, fill: bool = True) -> np.ndarray:
    """:meth:`RasterBed.read` through :func:`_raw`: the same pixels and the same fill, at a stride without GDAL's
    decimation."""
    z, mask = _raw(bed, row0, col0, nrows, ncols)
    if not mask.any() or mask.all():
        return z
    if not fill:
        z[mask] = np.nan
        return z
    nearest = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
    return z[tuple(nearest)]


def _filled_near(
    bed: RasterBed, box: tuple[int, int, int, int], bounds: tuple[int, int, int, int]
) -> np.ndarray | None:
    """``box`` (row, col, rows, cols) filled as the whole strip ``bounds`` would fill it: each hole takes its
    nearest good pixel inside ``bounds``. Read with a margin, which is doubled until every hole's nearest good pixel
    is nearer than any pixel beyond the margin (a tie with one beyond is not taken), so the distance transform of
    the margin picks the pixel the transform of the whole strip picks; None when it never is short of ``bounds``."""
    r, c, nr, nc = box
    top, left, bottom, right = bounds
    margin = FILL_MARGIN
    while True:
        r0, c0 = max(r - margin, top), max(c - margin, left)
        r1, c1 = min(r + nr + margin, bottom), min(c + nc + margin, right)
        if (r0, c0, r1, c1) == bounds:
            return None  # as wide as the strip: the strip itself is read
        z, bad = _raw(bed, r0, c0, r1 - r0, c1 - c0)
        inner = (slice(r - r0, r - r0 + nr), slice(c - c0, c - c0 + nc))
        if not bad.all():
            distance, nearest = ndimage.distance_transform_edt(bad, return_indices=True)
            dr, dc = np.nonzero(bad[inner])
            reach = distance[inner][dr, dc]
            rr, cc = dr + (r - r0), dc + (c - c0)
            room = np.full(reach.shape, np.inf)
            for gap, open_side in (
                (rr + 1, r0 > top), (r1 - r0 - rr, r1 < bottom), (cc + 1, c0 > left), (c1 - c0 - cc, c1 < right),
            ):  # fmt: skip
                if open_side:
                    room = np.minimum(room, gap)
            if (reach < room).all():
                return z[tuple(nearest)][inner]
        margin *= 2


class _ThreadBeds:
    """The DEM on one handle per reading thread, bound to the grid.

    A strip of tiles read whole spans the bounding box of its kept cells, on one core; on Block 2 that is the whole
    0.5 m DEM, 109 s. Read tile by tile, only where cells are kept, on every core, the pixels are the same: a pixel
    read is the file's own value whatever window holds it, and a hole is filled from the pixel the strip's own fill
    would take (W50)."""

    def __init__(self, source: RasterBed, x0: float, y0: float, workers: int = READ_WORKERS) -> None:
        self.source, self.origin = source, (x0, y0)
        self.workers = workers
        self._local = threading.local()
        self._lock = threading.Lock()
        self._stack = ExitStack()
        self._pool = ThreadPoolExecutor(workers) if workers > 1 else None

    def _bed(self) -> RasterBed:
        bed = getattr(self._local, "bed", None)
        if bed is None:
            bed = self.source.reopen()  # a handle of this thread's own, on the source's chunk store if it has one
            bed.bind(*self.origin)
            self._local.bed = bed
            with self._lock:
                self._stack.enter_context(bed)
        return bed

    def _tile(self, rows, cols, k: int, bounds: tuple[int, int, int, int], datum: float, out, where) -> bool:
        """One tile column's kept cells into their rows ``where`` of ``out``; False when a hole's fill needs the
        strip."""
        bed = self._bed()
        row0, col0 = int(rows.min()) * k, int(cols.min()) * k
        box = (row0, col0, (int(rows.max()) + 1) * k - row0, (int(cols.max()) + 1) * k - col0)
        z, bad = _raw(bed, *box)
        if _any_picked(bad, rows, cols, k, row0, col0):
            z = _filled_near(bed, box, bounds)
            if z is None:
                return False
        _pick_into(z, rows, cols, k, row0, col0, datum, out, where)
        return True

    def pick(self, rows, cols, k: int, datum: float, out: np.ndarray) -> bool:
        """The ground of one strip's kept cells into ``out``, tile column by tile column over the box of the cells
        kept in each; False, and ``out`` unspecified, when a hole's fill needs the strip read whole."""
        row0 = int(rows.min()) // TILE * TILE * k
        # what the strip reads whole, and so where its fill looks
        bounds = (row0, int(cols.min()) * k, row0 + TILE * k, (int(cols.max()) + 1) * k)
        tiles = cols // TILE
        order = np.argsort(tiles, kind="stable")
        cuts = np.flatnonzero(np.diff(tiles[order])) + 1
        groups = np.split(order, cuts)
        mapper = self._pool.map if self._pool is not None and len(groups) > 1 else map
        rows, cols = np.asarray(rows, np.int64), np.asarray(cols, np.int64)
        # every tile is seen to its end, also after one has failed: none is left writing into ``out`` when the
        # caller reads the strip whole over it
        done = list(mapper(lambda g: self._tile(rows[g], cols[g], k, bounds, float(datum), out, g), groups))
        return all(done)

    def __enter__(self) -> _ThreadBeds:
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True)
        self._stack.close()
