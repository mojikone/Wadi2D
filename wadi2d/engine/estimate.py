"""--dry-run: cells, memory and time, from a cost measured on this machine, before any table is built."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import numpy as np

from wadi2d.config.constants import G
from wadi2d.config.schema import Numerics, RunConfig, Tables
from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.layout import STATE_ARRAYS, STRIDE2, TILE2, WORK_ARRAYS
from wadi2d.solver.model import Model
from wadi2d.tables import ArrayBed, build_tables
from wadi2d.terrain import RasterBed

PROBE_CELLS = 512
"""Side of the square the cost is measured on."""
PROBE_DX = 10.0
PROBE_DEPTH = 2.0
PROBE_WARM_STEPS = 50
PROBE_STEPS = 400
BYTES = 4
"""Every array is float32."""
FACE_STATIC = 6
"""Scalars per face direction: two inverts, two heights over the mean bed, table top, crest coefficient."""
FACE_DIRECTIONS = 2
FACE_COLUMNS = 2
MAXIMA_ARRAYS = 5


@dataclass(frozen=True)
class Estimate:
    cells: int
    tiles: int
    device_gb: float
    ns_per_cell_step: float
    step_s: float
    steps: int
    wall_s: float
    backend: str


def measure_cost(backend: str, num: Numerics, cfg: Tables) -> tuple[float, str]:
    """Nanoseconds per cell-step on a flat wet square, on the real kernels, and the backend's name."""
    n = PROBE_CELLS
    grid = TileGrid.from_mask(np.ones((n, n), bool), 0.0, 0.0, PROBE_DX)
    ny, nx = grid.shape
    tables = build_tables(grid, ArrayBed(np.zeros((ny, nx)), PROBE_DX), cfg, 0.03)
    model = Model(tables, num, backend)
    model.set_depth(np.full(grid.shape, PROBE_DEPTH))
    model.advance(num.dt_max * PROBE_WARM_STEPS)
    model.stepper.t = 0.0
    done = model.stepper.nsteps
    t0 = time.perf_counter()
    while model.stepper.nsteps - done < PROBE_STEPS:
        model.advance(model.stepper.t + 10.0 * model.stepper.dt)
    model.backend.synchronize()
    wall = time.perf_counter() - t0
    steps = model.stepper.nsteps - done
    return wall / steps / float(grid.mask.sum()) * 1e9, model.backend.name


def estimate(cfg: RunConfig, backend: str | None = None) -> Estimate:
    """What the job will cost; the cell count comes from the DEM, the cost from a short probe."""
    from wadi2d.run import domain_mask, grid_window, preflight

    with RasterBed(cfg.terrain.dem, cfg.terrain.pixel_stride) as bed:
        preflight(cfg, bed.crs.to_wkt() if bed.crs is not None else "")
        window = grid_window(cfg, bed)
        mask = domain_mask(cfg, bed, window)
    grid = TileGrid.from_mask(mask, window.x0, window.y0, cfg.grid.dx)
    cells = int(mask.sum())
    tiles = grid.ntiles - 1
    rows = cfg.tables.rows
    state = (len(STATE_ARRAYS) + len(WORK_ARRAYS) + MAXIMA_ARRAYS) * STRIDE2
    static = (2 + rows + FACE_DIRECTIONS * (FACE_STATIC + rows * FACE_COLUMNS)) * TILE2
    gb = (tiles + 1) * (state + static) * BYTES / 1e9
    ns, name = measure_cost(backend or cfg.run.backend, cfg.numerics, cfg.tables)
    r = cfg.run
    ns *= r.estimate_overhead
    wave = r.estimate_wave * (r.estimate_speed + np.sqrt(G * r.estimate_depth))
    step = float(min(cfg.numerics.cfl * cfg.grid.dx / wave, cfg.numerics.dt_max))
    steps = int(np.ceil(r.duration_s / step))
    return Estimate(cells, tiles, round(gb, 3), round(ns, 3), step, steps, ns * 1e-9 * cells * steps, name)


def as_dict(e: Estimate) -> dict[str, object]:
    return asdict(e)
