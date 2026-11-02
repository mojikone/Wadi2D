"""Depth, speed and depth x speed at the pixel, kept as maxima over the saved maps of a run.

One source for both backends: ``xp`` is CuPy on the GPU and NumPy on the CPU, and the steps below read the same in
either. Each map updates three maxima per pixel: depth from the surface of :mod:`wadi2d.products.surface`, speed
interpolated from the corners of the same connected water, and their product at that same moment. A map that is not
one moment (the run's own maxima, each taken when it peaked) updates depth and speed only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import Pixels
from wadi2d.products.ground import CellPixels
from wadi2d.products.surface import (
    at_pixels,
    corner_basis,
    corner_groups,
    corner_means,
    face_links,
    fill_cells,
)

GPU_SHARE = 0.8
"""Share of the card's free memory the maxima may fill before they go back to the host between maps."""
GRID_ARRAYS = 16
"""Grids held on the device while a map is worked on."""
PIXEL_ARRAYS = 4
"""Ground and the three maxima, per pixel."""
WORK_SCALE = 3
"""The work arrays of the worst batch, against one array of that batch."""
BYTES = 4
TINY = 1e-6
"""Depth x speed below this reads as none, m2/s."""


def array_module(backend: str):
    """CuPy for ``gpu`` and for ``auto`` with a device, NumPy otherwise."""
    if backend in ("auto", "gpu"):
        try:
            import cupy as cp

            if cp.cuda.runtime.getDeviceCount() > 0:
                return cp
        except Exception:
            if backend == "gpu":
                raise
        if backend == "gpu":
            raise RuntimeError("no CUDA device available")
    return np


def to_host(a) -> np.ndarray:
    return a.get() if hasattr(a, "get") and not isinstance(a, np.ndarray) else a


def device_room(xp) -> float:
    """Free bytes on the device; the host's arrays need no such count."""
    if xp is np:
        return float("inf")
    return float(xp.cuda.Device().mem_info[0])


@dataclass
class Batch:
    """A run of kept cells. On the device the whole time, or only while a map is worked on."""

    rows: object
    cols: object
    ground: object
    maxima: list


class PixelMaxima:
    """Owns the maxima of one product step."""

    def __init__(self, xp, cells: CellPixels, zmin, sill_x, sill_y, keep, rule: Pixels, flat: bool = False) -> None:
        self.xp, self.rule, self.k, self.flat = xp, rule, cells.k, flat
        self.zmin, self.sill_x, self.sill_y = (xp.asarray(a) for a in (zmin, sill_x, sill_y))
        self.keep = xp.asarray(keep)
        self.cell_dv = xp.zeros(keep.shape, xp.float32)
        self.basis_t = corner_basis(xp, cells.k).T
        n = cells.rows.size
        per_cell = cells.k**2
        step = max(rule.batch_pixels // per_cell, 1)
        grids = GRID_ARRAYS * float(np.prod(keep.shape)) * BYTES
        need = PIXEL_ARRAYS * n * per_cell * BYTES + WORK_SCALE * rule.batch_pixels * BYTES
        self.resident = need + grids < GPU_SHARE * device_room(xp)
        self.batches = []
        for a in range(0, n, step):
            b = min(a + step, n)
            shape = (b - a, per_cell)
            self.batches.append(
                Batch(
                    xp.asarray(cells.rows[a:b]),
                    xp.asarray(cells.cols[a:b]),
                    self._rest(xp.asarray(cells.ground[a:b])),
                    [self._rest(xp.zeros(shape, xp.float32)) for _ in range(3)],
                )
            )

    def _rest(self, a):
        """Where an array waits between maps."""
        return a if self.resident else to_host(a)

    def add(self, depth, mean_depth, speed, moment: bool = True) -> None:
        """One map. ``moment`` says depth and speed are of the same instant."""
        xp, rule = self.xp, self.rule
        d = xp.asarray(depth)
        h = xp.asarray(mean_depth)
        wet = (d > 0.0) & self.keep
        level = self.zmin + d
        if self.flat:
            nothing = xp.zeros_like(wet)
            groups = corner_groups(xp, nothing, nothing)
        else:
            lx = face_links(xp, level, d, wet, self.sill_x, 1, rule.link_margin, rule.link_ratio)
            ly = face_links(xp, level, d, wet, self.sill_y, 0, rule.link_margin, rule.link_ratio)
            groups = corner_groups(xp, lx, ly)
        s = xp.asarray(speed) * self.keep * (d > rule.depth_floor)
        levels = corner_means(xp, level, wet, groups)
        speeds = corner_means(xp, s, s > 0.0, groups)
        for batch in self.batches:
            on = xp.nonzero(wet[batch.rows, batch.cols])[0]
            if on.size == 0:
                continue
            rows, cols = batch.rows[on], batch.cols[on]
            surface = at_pixels(xp, levels, rows, cols, self.basis_t)
            pixel_depth = fill_cells(xp, surface, xp.asarray(batch.ground)[on], h[rows, cols])
            pixel_speed = at_pixels(xp, speeds, rows, cols, self.basis_t) * (pixel_depth >= rule.depth_floor)
            store = [xp.asarray(a) for a in batch.maxima]
            new = [pixel_depth, pixel_speed, pixel_depth * pixel_speed]
            for held, value in zip(store[: 3 if moment else 2], new, strict=False):
                held[on] = xp.maximum(held[on], value)
            batch.maxima = [self._rest(a) for a in store]
        if moment:
            self.cell_dv = xp.maximum(self.cell_dv, d * s)

    def lift_dv(self, run_hazard) -> None:
        """Depth x speed peaks between saved maps. The run watched every cell's peak: scale each cell up to it."""
        xp = self.xp
        run = xp.asarray(run_hazard)
        missed = xp.clip(run / xp.maximum(self.cell_dv, TINY), 1.0, self.rule.peak_lift)
        for batch in self.batches:
            held = xp.asarray(batch.maxima[2])
            batch.maxima[2] = self._rest(held * missed[batch.rows, batch.cols][:, None])

    def result(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(cells, k * k) depth, speed and depth x speed on the host."""
        held = [np.concatenate([to_host(b.maxima[i]) for b in self.batches]) for i in range(3)]
        return held[0], held[1], held[2]
