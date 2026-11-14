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

import numpy as np
import rasterio
from scipy import ndimage

from wadi2d.config.schema import RunConfig
from wadi2d.solver.layout import CLOSED, TILE
from wadi2d.tables.builder import GridTables
from wadi2d.terrain import Ground, RasterBed, apply_objects
from wadi2d.terrain.sections import with_tables

READ_WORKERS = max(1, (os.cpu_count() or 2) // 2)
"""Threads that read the kept cells' ground, each on its own handle of the DEM (W50)."""
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
) -> CellPixels:
    """The pixels of the cells in ``keep``, a strip of tiles at a time. ``tick`` may raise to stop the read.

    On a mesh ``keep`` is on a lattice of cells ``scale`` finest cells wide, and ``datum`` is shared by every size.
    """
    grid = tables.grid
    with RasterBed(cfg.terrain.dem) as probe:
        native = probe.native
    with RasterBed(cfg.terrain.dem, bed_stride(cfg, native)) as bed:
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
        with (
            rasterio.Env(GDAL_CACHEMAX=READ_CACHE_MB),
            _ThreadBeds(cfg.terrain.dem, bed.stride, grid.x0, grid.y0) as beds,
        ):
            for strip in range(count):
                a, b = int(first[strip]), int(first[strip + 1])
                tick(strip, count)
                if a == b:
                    continue
                if edit is None and beds.pick(rows[a:b], cols[a:b], k, datum, ground[a:b]):
                    continue
                _whole_strip(bed, edit, rows[a:b], cols[a:b], k, strip * TILE * k, datum, ground[a:b])
    return CellPixels(rows, cols, k, bed.pixel, datum, ground)


def _picked(z: np.ndarray, rows: np.ndarray, cols: np.ndarray, k: int, row0: int, col0: int) -> np.ndarray:
    """The k x k pixels of each cell from a window read at bed pixel (row0, col0), (cells, k * k)."""
    top = (rows.astype(np.int64) * k - row0)[:, None, None] + np.arange(k)[None, :, None]
    left = (cols.astype(np.int64) * k - col0)[:, None, None] + np.arange(k)[None, None, :]
    return z[top, left].reshape(rows.size, -1)


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
    z = bed.read(row0, col0, TILE * k, ncols, fill=False)
    holes = np.isnan(z)
    if holes.any() and (edit is not None or holes[top, left].any()):
        z = bed.read(row0, col0, TILE * k, ncols)
    if edit is not None:
        edit(z, row0, col0)
    out[:] = (z[top, left] - datum).astype(np.float32).reshape(rows.size, -1)


FILL_MARGIN = 64
"""Pixels round a tile's kept cells first read to fill their holes from; doubled until the nearest good pixel of
every hole is provably inside (W50)."""


def _raw(bed: RasterBed, row0: int, col0: int, nrows: int, ncols: int) -> tuple[np.ndarray, np.ndarray]:
    """Bed pixels counted from the grid origin as :meth:`RasterBed.read` counts them, and which are holes, unfilled.

    Through the bed's own window reader: ``read(fill=False)`` gives a window that is all holes as zeros, not NaN, so
    a hole could not be told from ground there. ``terrain/dem.py`` is left as it is: it is hashed into every grid
    cache key, and editing it would rebuild every user's tables once for nothing."""
    return bed._window(bed.row_origin + row0 * bed.stride, bed.col_origin + col0 * bed.stride, nrows, ncols)


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

    def __init__(self, path, stride: int, x0: float, y0: float, workers: int = READ_WORKERS) -> None:
        self.path, self.stride, self.origin = path, stride, (x0, y0)
        self.workers = workers
        self._local = threading.local()
        self._lock = threading.Lock()
        self._stack = ExitStack()
        self._pool = ThreadPoolExecutor(workers) if workers > 1 else None

    def _bed(self) -> RasterBed:
        bed = getattr(self._local, "bed", None)
        if bed is None:
            bed = RasterBed(self.path, self.stride)
            bed.bind(*self.origin)
            self._local.bed = bed
            with self._lock:
                self._stack.enter_context(bed)
        return bed

    def _tile(self, rows, cols, k: int, bounds: tuple[int, int, int, int]) -> np.ndarray | None:
        bed = self._bed()
        row0, col0 = int(rows.min()) * k, int(cols.min()) * k
        box = (row0, col0, (int(rows.max()) + 1) * k - row0, (int(cols.max()) + 1) * k - col0)
        z, bad = _raw(bed, *box)
        if _picked(bad, rows, cols, k, row0, col0).any():
            z = _filled_near(bed, box, bounds)
            if z is None:
                return None
        return _picked(z, rows, cols, k, row0, col0)

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
        for group, picked in zip(
            groups, mapper(lambda g: self._tile(rows[g], cols[g], k, bounds), groups), strict=True
        ):
            if picked is None:
                return False
            out[group] = (picked - datum).astype(np.float32)
        return True

    def __enter__(self) -> _ThreadBeds:
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True)
        self._stack.close()
