"""The ground of every kept cell, pixel by pixel, and the ground of every face, from what built the tables.

Pixels come through the same ``RasterBed`` and the same pixel edits as the tables, so a burned line is burned here
too. Elevations are held over the lowest cell of the domain, so float32 keeps its resolution at any datum.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import RunConfig
from wadi2d.solver.layout import CLOSED, TILE
from wadi2d.tables.builder import GridTables
from wadi2d.terrain import RasterBed, apply_objects


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
    cfg: RunConfig, tables: GridTables, keep: np.ndarray, tick: Callable[[int, int], None] = lambda _a, _b: None
) -> CellPixels:
    """The pixels of the cells in ``keep``, a strip of tiles at a time. ``tick`` may raise to stop the read."""
    grid = tables.grid
    with RasterBed(cfg.terrain.dem) as probe:
        native = probe.native
    with RasterBed(cfg.terrain.dem, bed_stride(cfg, native)) as bed:
        k = bed.pixels_per_cell(grid.dx)
        bed.bind(grid.x0, grid.y0)
        edit = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain).edit
        rows, cols = np.nonzero(keep)
        datum = float(tables.zmin[keep].min()) if rows.size else 0.0
        ground = np.empty((rows.size, k * k), np.float32)
        strips = rows // TILE
        first = np.searchsorted(strips, np.arange(strips.max() + 2 if rows.size else 1))
        count = len(first) - 1
        for strip in range(count):
            a, b = int(first[strip]), int(first[strip + 1])
            tick(strip, count)
            if a == b:
                continue
            row0, col0 = strip * TILE * k, int(cols[a:b].min()) * k
            ncols = (int(cols[a:b].max()) + 1) * k - col0
            z = bed.read(row0, col0, TILE * k, ncols)
            if edit is not None:
                edit(z, row0, col0)
            z = (z - datum).astype(np.float32)
            top = (rows[a:b] * k - row0)[:, None, None] + np.arange(k)[None, :, None]
            left = (cols[a:b] * k - col0)[:, None, None] + np.arange(k)[None, None, :]
            ground[a:b] = z[top, left].reshape(b - a, -1)
    return CellPixels(rows, cols, k, bed.pixel, datum, ground)
