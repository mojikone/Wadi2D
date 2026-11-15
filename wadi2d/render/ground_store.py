"""The ground under the views drawn so far, a tile of cells at a time, at the terrain pixel or one pixel in every few.

It is the ground the pixel maps of record stand on: the same ``RasterBed``, the same pixel edits of the terrain objects,
the same datum (:mod:`wadi2d.products.ground`). A view further out takes one pixel in every ``m``, where ``m`` divides
the pixels of a cell, so a cell always holds whole pixels. Tiles are read on threads, each with its own handle of the
raster, and kept until memory runs short, so a pan reads only the tiles that came into view and a move of the time
slider reads nothing.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.demstore import open_bed
from wadi2d.grid.tiles import TileGrid
from wadi2d.products.ground import bed_stride
from wadi2d.solver.layout import TILE
from wadi2d.terrain import Ground, RasterBed, apply_objects
from wadi2d.terrain.sections import with_tables

BYTES_PER_MB = 1024.0 * 1024.0
Key = tuple[int, int, int]
"""(pixel step, tile row, tile column)."""


class GroundStore:
    def __init__(self, cfg: RunConfig, grid: TileGrid, datum: float, cache=None) -> None:
        self.cfg = with_tables(cfg)
        self.cache = cache
        """The run's cache folder: its tables left the DEM's chunks there, so a tile is read without decoding (W84)."""
        self.grid, self.datum = grid, datum
        rule = cfg.outputs.slider
        with RasterBed(cfg.terrain.dem) as probe:
            self.stride = bed_stride(cfg, probe.native)
        with RasterBed(cfg.terrain.dem, self.stride) as bed:
            self.per_cell = bed.pixels_per_cell(grid.dx)
            self.pixel = bed.pixel
        self.steps = [m for m in range(1, self.per_cell + 1) if self.per_cell % m == 0]
        """Pixel steps a view may take, finest first."""
        self.budget = rule.ground_cache_mb * BYTES_PER_MB
        workers = rule.ground_workers or max(1, (os.cpu_count() or 2) // 2)
        self.pool = ThreadPoolExecutor(workers, thread_name_prefix="ground")
        self.local = threading.local()
        self.lock = threading.RLock()
        self.edit_lock = threading.Lock()
        self.edits: dict[int, object] = {}
        self.tiles: OrderedDict[Key, np.ndarray] = OrderedDict()
        self.pending: dict[Key, Future] = {}
        self.wanted: set[Key] = set()
        self.held = 0
        self.failed: BaseException | None = None
        self.read_count = 0

    def close(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)

    def pixels(self, m: int) -> int:
        """Pixels along a cell at pixel step ``m``."""
        return self.per_cell // m

    def pixel_m(self, m: int) -> float:
        return self.pixel * m

    def step_for(self, screen_m: float) -> int:
        """The coarsest pixel step no coarser than a screen pixel; the terrain pixel itself when the view is closer."""
        fits = [m for m in self.steps if self.pixel_m(m) <= screen_m * (1.0 + 1e-9)]
        return max(fits) if fits else 1

    # Reading, on the pool's threads.

    def _bed(self, m: int) -> RasterBed:
        beds = self.local.__dict__.setdefault("beds", {})
        if m not in beds:
            bed = open_bed(self.cfg, self.cache, self.stride * m)
            bed.bind(self.grid.x0, self.grid.y0)
            beds[m] = bed
        return beds[m]

    def _edit(self, m: int):
        """The pixel edit of the terrain objects at this pixel, or None; built once, by whoever needs it first."""
        objects = self.cfg.terrain.objects
        if not objects:
            return None
        with self.edit_lock:
            if m not in self.edits:
                bed = open_bed(self.cfg, self.cache, self.stride * m)  # left open: the edit may read through it
                bed.bind(self.grid.x0, self.grid.y0)
                ground = Ground(bed, self.grid.x0, self.grid.y0)
                self.edits[m] = apply_objects(self.grid, objects, bed.pixel, self.cfg.terrain, ground).edit
            return self.edits[m]

    def _read(self, key: Key) -> np.ndarray:
        m, tile_row, tile_col = key
        side = TILE * self.pixels(m)
        row0, col0 = tile_row * side, tile_col * side
        bed = self._bed(m)
        z = bed.read(row0, col0, side, side, fill=False)
        if np.isnan(z).any():
            z = bed.read(row0, col0, side, side)
        edit = self._edit(m)
        if edit is not None:
            with self.edit_lock:  # the edits share their own tables and one handle of the raster
                edit(z, row0, col0)
        return (z - self.datum).astype(np.float32)

    def _done(self, key: Key, future: Future) -> None:
        with self.lock:
            self.pending.pop(key, None)
            if future.cancelled():
                return
            error = future.exception()
            if error is not None:
                self.failed = error
                return
            tile = future.result()
            self.tiles[key] = tile
            self.held += tile.nbytes
            self.read_count += 1
            for old in list(self.tiles):
                if self.held <= self.budget:
                    break
                if old not in self.wanted:
                    self.held -= self.tiles.pop(old).nbytes

    # Asking, on the caller's thread.

    def want(self, keys: list[Key], also: bool = False) -> None:
        """Start reading the tiles that are not here yet, and drop the reads nobody waits for any more.

        ``also`` adds these to what is wanted already, and drops nothing."""
        with self.lock:
            self.wanted = self.wanted | set(keys) if also else set(keys)
            stale = [future for key, future in self.pending.items() if key not in self.wanted]
            missing = [key for key in keys if key not in self.tiles and key not in self.pending]
        for future in stale:
            future.cancel()  # one already running finishes and is kept
        for key in missing:
            with self.lock:  # re-entrant: a read that is already over calls back at once, on this thread
                future = self.pool.submit(self._read, key)
                self.pending[key] = future
                future.add_done_callback(lambda done, key=key: self._done(key, done))

    def missing(self, keys: list[Key]) -> int:
        if self.failed is not None:
            error, self.failed = self.failed, None
            raise error
        with self.lock:
            return sum(key not in self.tiles for key in keys)

    def wait(self, keys: list[Key], seconds: float | None) -> int:
        """Wait for these tiles, at most ``seconds`` (None: until they are here); how many are still missing."""
        with self.lock:
            running = [self.pending[key] for key in keys if key in self.pending]
        if running:
            wait_for(running, timeout=seconds)
        return self.missing(keys)

    def cells(self, m: int, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
        """(cells, k * k) ground over the datum of the given cells, pixel rows first, as the pixel maps hold it."""
        k = self.pixels(m)
        out = np.empty((rows.size, k * k), np.float32)
        tile_rows, tile_cols = rows // TILE, cols // TILE
        marks = tile_rows.astype(np.int64) * (1 << 32) + tile_cols
        for mark in np.unique(marks):
            on = np.nonzero(marks == mark)[0]
            key = (m, int(tile_rows[on[0]]), int(tile_cols[on[0]]))
            with self.lock:
                tile = self.tiles[key]
                self.tiles.move_to_end(key)
            blocks = tile.reshape(TILE, k, TILE, k)
            out[on] = blocks[rows[on] % TILE, :, cols[on] % TILE, :].reshape(on.size, k * k)
        return out
