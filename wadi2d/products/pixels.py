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
    Neighbours,
    around_links,
    at_pixels,
    corner_basis,
    corner_groups,
    corner_means,
    edge_basis,
    face_links,
    fill_cells,
    fill_offset,
    offsets_around,
)

GPU_SHARE = 0.8
"""Share of the card's free memory the maxima may fill before they go back to the host between maps."""
LIST_ARRAYS = 60
"""Arrays over the kept cells held on the device while a map is worked on, neighbour tables included."""
PIXEL_ARRAYS = 4
"""Ground and the three maxima, per pixel."""
WORK_SCALE = 5
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
    """A run of kept cells, ``first`` to ``last``. On the device the whole time, or only while a map is worked on."""

    first: int
    last: int
    ground: object
    maxima: list


class PixelMaxima:
    """Owns the maxima of one product step. Maps arrive as grids and are reduced to the kept cells at once."""

    def __init__(
        self, xp, cells: CellPixels, zmin, sill_x, sill_y, keep, rule: Pixels, flat: bool = False, ghosts=None
    ) -> None:
        """``ghosts`` are (rows, columns) of cells that shape the surface and take no pixels: another size on a mesh."""
        self.xp, self.rule, self.k, self.flat = xp, rule, cells.k, flat
        self.rows, self.cols = cells.rows, cells.cols
        order = None
        if ghosts is not None:
            self.rows = np.concatenate((cells.rows, ghosts[0]))
            self.cols = np.concatenate((cells.cols, ghosts[1]))
            order = (self.rows, self.cols)
        self.near = Neighbours(xp, keep, order)
        self.zmin = self._cells(zmin)
        self.sill_x, self.sill_y = self._cells(sill_x, np.inf), self._cells(sill_y, np.inf)
        self.basis_t = corner_basis(xp, cells.k).T
        self.edge_t = edge_basis(xp, cells.k, rule.edge_band).T
        n = cells.rows.size
        self.pixels_of = n
        self.cell_dv = xp.zeros(self.rows.size + 1, xp.float32)
        self.corners: tuple = ()
        self.offset = xp.zeros(self.rows.size + 1, xp.float32)
        per_cell = cells.k**2
        step = max(rule.batch_pixels // per_cell, 1)
        lists = LIST_ARRAYS * float(n) * BYTES
        need = PIXEL_ARRAYS * n * per_cell * BYTES + WORK_SCALE * rule.batch_pixels * BYTES
        self.resident = need + lists < GPU_SHARE * device_room(xp)
        self.batches = []
        for a in range(0, n, step):
            b = min(a + step, n)
            shape = (b - a, per_cell)
            self.batches.append(
                Batch(
                    a,
                    b,
                    self._rest(xp.asarray(cells.ground[a:b])),
                    [self._rest(xp.zeros(shape, xp.float32)) for _ in range(3)],
                )
            )

    def _cells(self, grid, left_out: float = 0.0):
        """A grid reduced to the kept cells, on the host, where the map already is, and then moved."""
        return self.xp.asarray(np.append(grid[self.rows, self.cols], left_out).astype(np.float32))

    def _rest(self, a):
        """Where an array waits between maps."""
        return a if self.resident else to_host(a)

    def _shape(self, levels, around, cells):
        """The surface over the given cells, before the fill; ``around`` is None until an offset exists."""
        surface = at_pixels(self.xp, levels, cells, self.basis_t)
        return surface if around is None else surface + at_pixels(self.xp, around, cells, self.edge_t)

    def _join_edges(self, levels, h, wet, groups, offset, known):
        """The nine offsets each cell reads, so that the surface does not step at a joined edge, and the offsets."""
        xp = self.xp
        passes = 0 if self.flat else self.rule.edge_passes
        if passes == 0:
            return None, offset
        links = around_links(groups)
        if known is not None:
            links = {key: link & self.near.at(known, *key) for key, link in links.items()}
        around = None
        for _ in range(passes):
            change = xp.zeros_like(offset)
            for batch in self.batches:
                on = xp.nonzero(wet[batch.first : batch.last])[0]
                if on.size:
                    cells = on + batch.first
                    shape = self._shape(levels, around, cells)
                    change[cells] = fill_offset(xp, shape, xp.asarray(batch.ground)[on], h[cells])
            offset = offset + change
            around = offsets_around(self.near, offset, links)
        return around, offset

    def add(self, depth, mean_depth, speed, moment: bool = True, level=None, offsets=None) -> None:
        """One map, as grids. ``moment`` says depth and speed are of the same instant. ``level`` replaces ground + depth.

        ``offsets`` holds the fill offsets of cells that take no pixels here, NaN where none is known yet.
        """
        xp, rule, near = self.xp, self.rule, self.near
        d, h, s = self._cells(depth), self._cells(mean_depth), self._cells(speed)
        wet = d > 0.0
        level = self.zmin + d if level is None else self._cells(level)
        if self.flat:
            nothing = xp.zeros_like(wet)
            groups = corner_groups(near, nothing, nothing)
        else:
            lx = face_links(near, level, d, wet, self.sill_x, 1, rule.link_margin, rule.link_ratio)
            ly = face_links(near, level, d, wet, self.sill_y, 0, rule.link_margin, rule.link_ratio)
            groups = corner_groups(near, lx, ly)
        s = s * (d > rule.depth_floor)
        levels = corner_means(near, level, wet, groups)
        speeds = corner_means(near, s, s > 0.0, groups)
        self.corners = (levels, speeds)
        seed, known = xp.zeros_like(h), None
        if offsets is not None:
            given = self._cells(offsets, np.nan)
            known = ~xp.isnan(given)
            known[: self.pixels_of] = True
            seed = xp.where(known, xp.nan_to_num(given), 0.0)
        around, self.offset = self._join_edges(levels, h, wet, groups, seed, known)
        for batch in self.batches:
            on = xp.nonzero(wet[batch.first : batch.last])[0]
            if on.size == 0:
                continue
            cells = on + batch.first
            pixel_depth = fill_cells(xp, self._shape(levels, around, cells), xp.asarray(batch.ground)[on], h[cells])
            pixel_speed = at_pixels(xp, speeds, cells, self.basis_t) * (pixel_depth >= rule.depth_floor)
            store = [xp.asarray(a) for a in batch.maxima]
            new = [pixel_depth, pixel_speed, pixel_depth * pixel_speed]
            for held, value in zip(store[: 3 if moment else 2], new, strict=False):
                held[on] = xp.maximum(held[on], value)
            batch.maxima = [self._rest(a) for a in store]
        if moment:
            self.cell_dv = xp.maximum(self.cell_dv, d * s)
        if xp is not np:  # the wet set changes with every map: left alone, the pool fills the card, and Windows pages it
            xp.get_default_memory_pool().free_all_blocks()

    def lift_dv(self, run_hazard) -> None:
        """Depth x speed peaks between saved maps. The run watched every cell's peak: scale each cell up to it."""
        xp = self.xp
        run = self._cells(run_hazard)
        missed = xp.clip(run / xp.maximum(self.cell_dv, TINY), 1.0, self.rule.peak_lift)
        for batch in self.batches:
            held = xp.asarray(batch.maxima[2])
            batch.maxima[2] = self._rest(held * missed[batch.first : batch.last][:, None])

    def result(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(cells, k * k) depth, speed and depth x speed on the host."""
        held = [np.concatenate([to_host(b.maxima[i]) for b in self.batches]) for i in range(3)]
        return held[0], held[1], held[2]
