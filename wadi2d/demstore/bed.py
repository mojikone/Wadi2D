"""StoredBed: the ``RasterBed`` every reader knows, its pixels taken from the chunk store (W84).

It gives what ``RasterBed`` gives, pixel for pixel and mask for mask (the tests compare the two on windows inside,
across and past the raster, at every stride): only where the pixels come from changes. ``terrain/dem.py`` is left as
it is, because it is hashed into every grid cache key and the tables do not change; a bed with no store behind it is
a ``RasterBed``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from rasterio.windows import Window

from wadi2d.config.schema import RunConfig
from wadi2d.demstore import chunks
from wadi2d.demstore.chunks import ChunkStore, store_for
from wadi2d.demstore.scratch import Scratch
from wadi2d.terrain.dem import HUGE_ELEVATION, GridWindow, RasterBed


def cache_folder(cfg: RunConfig, run: str | Path | None = None) -> Path | None:
    """Where a job keeps its caches: its own folder, else 'cache' in the run folder, else nowhere."""
    if cfg.grid.cache_dir:
        return Path(cfg.grid.cache_dir)
    return None if run is None else Path(run) / "cache"


class StoredBed(RasterBed):
    """A ``RasterBed`` whose windows come from a ``ChunkStore``; without one it reads as its parent does."""

    def __init__(self, path: str | Path, pixel_stride: int = 1, store: ChunkStore | None = None) -> None:
        super().__init__(path, pixel_stride)
        self.store = store
        self._wanted: np.ndarray | None = None
        self._scratch = Scratch()
        self.whole_pixels = not self.src.overviews(1)
        """A decimated read picks pixels of the full raster: GDAL reads a raster with overviews from those instead,
        whatever they were averaged from, so there every decimated read stays GDAL's."""

    def reopen(self) -> StoredBed:
        other = StoredBed(self.path, self.stride, self.store)
        other.row_origin, other.col_origin = self.row_origin, self.col_origin
        return other

    def _window(self, row: int, col: int, nrows: int, ncols: int) -> tuple[np.ndarray, np.ndarray]:
        """As ``RasterBed._window``: the same clipping, the same pixels, the same mask. At a stride the parent's
        decimated read takes the pixel at ``stride // 2`` of every block of ``stride`` (W80); so does this."""
        if self.store is None or (self.stride > 1 and not self.whole_pixels):
            return super()._window(row, col, nrows, ncols)
        s = self.stride
        skip_r = max(-(row // s), 0)
        skip_c = max(-(col // s), 0)
        nr = min(nrows - skip_r, (self.src.height - (row + skip_r * s)) // s)
        nc = min(ncols - skip_c, (self.src.width - (col + skip_c * s)) // s)
        # the thread's last window again when its reader has let go of it, else fresh arrays (see ``Scratch``)
        z, mask, used = self._scratch.arrays(nrows, ncols)
        clipped = (nr, nc) != (nrows, ncols)
        if used and clipped:  # past the raster's edge a window holds what a fresh one holds there
            z[...] = 0.0
            mask[...] = True
        if nr <= 0 or nc <= 0:
            return z, mask
        inside = (slice(skip_r, skip_r + nr), slice(skip_c, skip_c + nc))
        self.store.take(
            row + skip_r * s + s // 2, col + skip_c * s + s // 2, s, z[inside], mask[inside], HUGE_ELEVATION
        )
        return z, mask

    def _sampled(self, window: Window, shape: tuple[int, int], step: int) -> np.ndarray:
        """A window that is a whole number of ``step`` pixels each way, from the store: the decimated read's pixel
        is the one at ``step // 2`` of every block. Any other window through GDAL, as before."""
        whole = int(window.height) == shape[0] * step and int(window.width) == shape[1] * step
        if self.store is None or not whole or (step > 1 and not self.whole_pixels):
            return super()._sampled(window, shape, step)
        row, col = int(window.row_off) + step // 2, int(window.col_off) + step // 2
        wanted = self._wanted if self._wanted is not None and self._wanted.shape == shape else None
        keys = self.store.keys(row, col, step, *shape)
        if wanted is not None:
            keys = [key for key in keys if _touches(wanted, key, row, col, step)]
        self.store.ensure(keys)
        z = np.zeros(shape, np.float64)
        mask = np.ones(shape, bool)
        self.store.take(row, col, step, z, mask, HUGE_ELEVATION, wanted)
        z[mask] = np.nan
        return z

    def active_cells(self, w: GridWindow, dx: float, wanted: np.ndarray) -> np.ndarray:
        """``active_mask`` on the cells of ``wanted``, False elsewhere: the ground under a cell nobody asks about
        (outside the domain's outline) is not read, so it is never decoded into the store."""
        self._wanted = np.asarray(wanted, bool)
        try:
            return self.active_mask(w, dx) & self._wanted
        finally:
            self._wanted = None


def _touches(wanted: np.ndarray, key: tuple[int, int], row: int, col: int, step: int) -> bool:
    """Whether a wanted sample of the lattice from (row, col) lies in chunk ``key``."""
    size = chunks.CHUNK
    i0, i1 = chunks.span(row, step, wanted.shape[0], key[0] * size, (key[0] + 1) * size)
    j0, j1 = chunks.span(col, step, wanted.shape[1], key[1] * size, (key[1] + 1) * size)
    return i1 > i0 and j1 > j0 and bool(wanted[i0:i1, j0:j1].any())


def open_bed(cfg: RunConfig, cache_dir: str | Path | None, stride: int | None = None) -> RasterBed:
    """The job's DEM as a bed at ``stride`` (the job's own when None), on the chunk store under ``cache_dir`` when
    there is one to use."""
    bed = StoredBed(cfg.terrain.dem, cfg.terrain.pixel_stride if stride is None else stride)
    bed.store = store_for(bed.path, bed.src, cache_dir, cfg.grid.content_hash_limit_mb)
    return bed
