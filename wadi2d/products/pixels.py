"""Depth, speed and depth x speed at the pixel, kept as maxima over the saved maps of a run.

One source for both backends: ``xp`` is CuPy on the GPU and NumPy on the CPU, and the steps below read the same in
either. Each map updates three maxima per pixel: depth from the surface of :mod:`wadi2d.products.surface`, speed
interpolated from the corners of the same connected water, and their product at that same moment. A map that is not
one moment (the run's own maxima, each taken when it peaked) updates depth and speed only.

How the surface is drawn is ``outputs.pixels.surface`` (W100). ``continuous``, the default: one surface through the
cell corners, a corner taking the mean, over the cells joined there, of each cell's level and of how far that cell's
surface must move to hold its water; the depth of a pixel is that surface over its ground, with no refill of the cell
afterwards, so the surface does not step at a cell edge. ``corners``: the levels alone, RAS Mapper's sloping mode, which
loses thin sheets on slopes. ``cell_fill``: every cell filled to its own water, eased across joined edges (W9), the
maps made before W100.
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
    capped_moves,
    corner_basis,
    corner_components,
    corner_groups,
    corner_means,
    corner_sills,
    edge_basis,
    face_joins,
    face_links,
    fill_cells,
    fill_offset,
    offsets_around,
    touched,
    weighted_corner_means,
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
CORNER_REACH = 2
"""Cells a corner's links read past the cell itself."""
CONTINUOUS, CORNERS, CELL_FILL = "continuous", "corners", "cell_fill"
"""The values of ``outputs.pixels.surface``."""


def halo(rule: Pixels) -> int:
    """Cells a window must hold round its own for those to equal the whole-domain answer: a cell reads its
    neighbours' levels and, through the refills that ease joined edges, their fill offsets, which read theirs. On
    the continuous surface a corner reads its cells' offsets once, and each offset its cell's corners."""
    if rule.surface == CELL_FILL:
        return rule.edge_passes + CORNER_REACH
    return CORNER_REACH + (1 if rule.surface == CONTINUOUS else 0)


def kept_cells(peak_mean_depth: np.ndarray, rule: Pixels) -> np.ndarray:
    """The cells that take pixels: every cell that was ever wet, or under ``cell_fill`` only those whose mean depth
    reached ``cell_depth`` (W100: that cut drew a cell of 6 cm beside one of 4 cm as a square block of water)."""
    if rule.surface == CELL_FILL:
        return peak_mean_depth > rule.cell_depth
    return peak_mean_depth > 0.0


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


def _rows(xp, batch, on):
    """The ground of a batch's cells ``on`` on the device: the batch's own array when every cell is in it, which is
    the same numbers without a copy of its pixels (W93)."""
    ground = xp.asarray(batch.ground)
    return ground if on.size == ground.shape[0] else ground[on]


@dataclass
class Batch:
    """A run of kept cells, ``first`` to ``last``. On the device the whole time, or only while a map is worked on."""

    first: int
    last: int
    ground: object
    maxima: list


class PixelMaxima:
    """Owns the maxima of one product step. Maps arrive as grids and are reduced to the kept cells at once."""

    skip = True
    """On the card, leave a map's cell unfilled where the map cannot raise any of its pixels' maxima (W93)."""

    def __init__(
        self, xp, cells: CellPixels, zmin, sill_x, sill_y, keep, rule: Pixels, flat: bool = False, ghosts=None
    ) -> None:
        """``ghosts`` are (rows, columns) of cells that shape the surface and take no pixels: another size on a mesh."""
        self.xp, self.rule, self.k, self.flat = xp, rule, cells.k, flat
        self.tidy = True
        """Hand the device's unused memory back after every map. A block of a large run sets this off: its pool is
        capped by the block's own budget, and giving it back 193 times a block costs more than the maps (W86)."""
        self.filled = self.offered = 0
        """Cells of the maps filled, and offered for filling, while ``skip`` holds."""
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
                    change[cells] = fill_offset(xp, shape, _rows(xp, batch, on), h[cells])
            offset = offset + change
            around = offsets_around(self.near, offset, links)
        return around, offset

    def add(self, depth, mean_depth, speed, moment: bool = True, level=None, offsets=None) -> None:
        """One map, as grids. ``moment`` says depth and speed are of the same instant. ``level`` replaces ground + depth.

        ``offsets`` holds the fill offsets of cells that take no pixels here, NaN where none is known yet.
        """
        self._add(
            self._cells(depth),
            self._cells(mean_depth),
            self._cells(speed),
            moment,
            None if level is None else self._cells(level),
            None if offsets is None else self._cells(offsets, np.nan),
        )

    def _listed(self, values, left_out: float = 0.0):
        """Values that already stand per kept cell, in the cells' order, moved to the device with the last entry."""
        return self.xp.asarray(np.append(values, left_out).astype(np.float32))

    def add_listed(self, depth, mean_depth, speed, moment: bool = True, offsets=None) -> None:
        """:meth:`add` for a map already reduced to the kept cells, in their order (W86): a block of a large run
        takes its cells from the maps held once, not from grids. ``offsets`` as :meth:`add`'s, in the same order."""
        given = None if offsets is None else self._listed(offsets, np.nan)
        self._add(self._listed(depth), self._listed(mean_depth), self._listed(speed), moment, None, given)

    def watch(self, cells: np.ndarray) -> None:
        """Keep, map by map, the surface at the four corners of ``cells`` (places in the cells' order), their level
        and depth: what a strip beside them takes at the nodes it shares with them (W100)."""
        self.watched = self.xp.asarray(np.asarray(cells, np.int64))
        self.record: list = []

    def _keep_record(self, corners, speeds, level, d) -> None:
        if getattr(self, "watched", None) is None or self.watched.size == 0:
            return
        xp, at = self.xp, self.watched
        held = xp.stack([*(c[at] for c in corners), *(c[at] for c in speeds), level[at], d[at]])
        self.record.append(to_host(held))

    def _add(self, d, h, s, moment: bool, level, given) -> None:
        if self.rule.surface == CELL_FILL:
            self._add_filled(d, h, s, moment, level, given)
        else:
            self._add_continuous(d, h, s, moment, level, given)

    def _joins(self, level, d, wet) -> tuple[list, list]:
        """The corner groups of the continuous surface (:func:`face_joins`, every path round a corner) and each
        corner's lowest face its cells do not share (:func:`corner_sills`)."""
        near, rule = self.near, self.rule
        if self.flat:
            lx = ly = self.xp.zeros_like(wet)
        else:
            lx = face_joins(near, level, d, wet, self.sill_x, 1, rule.link_margin, rule.link_ratio)
            ly = face_joins(near, level, d, wet, self.sill_y, 0, rule.link_margin, rule.link_ratio)
        return corner_components(near, lx, ly), corner_sills(near, lx, ly, self.sill_x, self.sill_y)

    def _add_continuous(self, d, h, s, moment: bool, level, given) -> None:
        """One map on the continuous surface (W100). Cells share a corner where :func:`face_joins` joins them; a
        corner first takes the mean level of its wet cells; each wet cell's surface of that shape is moved, by one
        Newton fill, until it holds the cell's water; the corners then also take the mean of those moves, kept from
        lifting the surface over a face its cells do not share (:func:`capped_moves`), and a pixel's depth is the
        surface through its cell's corners over its ground. Cells sharing a corner read the same value there, so the
        surface is one sheet across their edge; a dry cell that water spills into takes pixels too, so that water ends
        on its ground. On ``corners`` the moves are left out."""
        xp, rule, near = self.xp, self.rule, self.near
        wet = d > 0.0
        level = self.zmin + d if level is None else level
        groups, sills = self._joins(level, d, wet)
        s = s * (d > rule.depth_floor)
        weight = wet.astype(xp.float32)  # a dry cell's level, its lowest ground, is no water surface
        levels = weighted_corner_means(near, level, weight, groups)
        speeds = corner_means(near, s, s > 0.0, groups)
        self.corners = (levels, speeds)
        corners = levels
        drawn = wet | touched(near, groups)
        if rule.surface == CONTINUOUS:
            offset = xp.zeros_like(h)
            if given is not None:  # a coarser neighbour's move as it stands, NaN for a finer one not yet worked
                known = ~xp.isnan(given)
                known[: self.pixels_of] = True
                offset = xp.where(known, xp.nan_to_num(given), 0.0).astype(xp.float32)
                weight = weight * known
            for batch in self.batches:
                on = xp.nonzero(wet[batch.first : batch.last])[0]
                if on.size:
                    cells = on + batch.first
                    shape = at_pixels(xp, levels, cells, self.basis_t)
                    offset[cells] = fill_offset(xp, shape, _rows(xp, batch, on), h[cells])
            self.offset = offset
            moves = weighted_corner_means(near, offset, weight, groups)
            corners = capped_moves(levels, moves, sills, xp)
        self._keep_record(corners, speeds, level, d)
        for batch in self.batches:
            on = xp.nonzero(drawn[batch.first : batch.last])[0]
            if on.size == 0:
                continue
            cells = on + batch.first
            store = [xp.asarray(a) for a in batch.maxima]
            pixel_depth = at_pixels(xp, corners, cells, self.basis_t)
            pixel_depth -= _rows(xp, batch, on)
            xp.maximum(pixel_depth, 0.0, out=pixel_depth)
            pixel_speed = at_pixels(xp, speeds, cells, self.basis_t) * (pixel_depth >= rule.depth_floor)
            new = [pixel_depth, pixel_speed, pixel_depth * pixel_speed] if moment else [pixel_depth, pixel_speed]
            whole = on.size == batch.last - batch.first
            for held, value in zip(store, new, strict=False):
                if whole:
                    xp.maximum(held, value, out=held)
                else:
                    held[on] = xp.maximum(held[on], value)
            batch.maxima = [self._rest(a) for a in store]
        if moment:
            self.cell_dv = xp.maximum(self.cell_dv, d * s)
        if xp is not np and self.tidy:  # the wet set changes with every map: left alone, the pool fills the card
            xp.get_default_memory_pool().free_all_blocks()  # and Windows pages it

    def _add_filled(self, d, h, s, moment: bool, level, given) -> None:
        """One map by W9's rule: each cell filled to its own water, its fill offset eased across joined edges."""
        xp, rule, near = self.xp, self.rule, self.near
        wet = d > 0.0
        level = self.zmin + d if level is None else level
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
        if given is not None:
            known = ~xp.isnan(given)
            known[: self.pixels_of] = True
            seed = xp.where(known, xp.nan_to_num(given), 0.0)
        around, self.offset = self._join_edges(levels, h, wet, groups, seed, known)
        for batch in self.batches:
            on = xp.nonzero(wet[batch.first : batch.last])[0]
            if on.size == 0:
                continue
            cells = on + batch.first
            surface = self._shape(levels, around, cells)
            store = [xp.asarray(a) for a in batch.maxima]
            whole = on.size == batch.last - batch.first  # every cell of the batch wet: no gather, no scatter (W93)
            if xp is not np and moment and self.skip:
                # a cell this map cannot raise anywhere is not filled (W93); the speed's product over every wet cell
                # of the batch stays one product, as before, so its numbers do not move with the cells filled
                from wadi2d.products.fill_kernels import may_raise

                relief = _rows(xp, batch, on) - surface
                top = xp.maximum(xp.maximum(speeds[0][cells], speeds[1][cells]), xp.maximum(speeds[2][cells], speeds[3][cells]))
                need = xp.nonzero(may_raise(xp, relief, h[cells], top, on, store, rule.depth_floor))[0]
                self.filled += int(need.size)
                self.offered += int(on.size)
                if need.size < on.size:
                    if need.size:
                        pixel_depth = fill_cells(xp, surface[need], _rows(xp, batch, on)[need], h[cells][need])
                        speed_all = at_pixels(xp, speeds, cells, self.basis_t)
                        pixel_speed = speed_all[need] * (pixel_depth >= rule.depth_floor)
                        rows = on[need]
                        for held, value in zip(store, [pixel_depth, pixel_speed, pixel_depth * pixel_speed], strict=True):
                            held[rows] = xp.maximum(held[rows], value)
                    batch.maxima = [self._rest(a) for a in store]
                    continue
            pixel_depth = fill_cells(xp, surface, _rows(xp, batch, on), h[cells])
            pixel_speed = at_pixels(xp, speeds, cells, self.basis_t) * (pixel_depth >= rule.depth_floor)
            new = [pixel_depth, pixel_speed, pixel_depth * pixel_speed]
            for held, value in zip(store[: 3 if moment else 2], new, strict=False):
                if whole:
                    xp.maximum(held, value, out=held)
                else:
                    held[on] = xp.maximum(held[on], value)
            batch.maxima = [self._rest(a) for a in store]
        if moment:
            self.cell_dv = xp.maximum(self.cell_dv, d * s)
        if xp is not np and self.tidy:  # the wet set changes with every map: left alone, the pool fills the card
            xp.get_default_memory_pool().free_all_blocks()  # and Windows pages it

    def lift_dv(self, run_hazard) -> None:
        """Depth x speed peaks between saved maps. The run watched every cell's peak: scale each cell up to it."""
        self._lift(self._cells(run_hazard))

    def lift_listed(self, run_hazard) -> None:
        """:meth:`lift_dv` for peaks already reduced to the kept cells."""
        self._lift(self._listed(run_hazard))

    def _lift(self, run) -> None:
        xp = self.xp
        missed = xp.clip(run / xp.maximum(self.cell_dv, TINY), 1.0, self.rule.peak_lift)
        if self.rule.surface != CELL_FILL:
            self._lift_smooth(missed)
            return
        for batch in self.batches:
            held = xp.asarray(batch.maxima[2])
            batch.maxima[2] = self._rest(held * missed[batch.first : batch.last][:, None])

    def _lift_smooth(self, missed) -> None:
        """The lift through the corners (W100): each corner takes the mean of the lifts of the cells round it, and a
        pixel the lift of the surface through them, so the hazard classes do not step at a cell edge where one cell
        peaked between saved maps and its neighbour did not."""
        xp, near = self.xp, self.near
        kept = xp.arange(missed.size) < self.pixels_of  # not the ghosts of another size, nor the left-out entry
        lx = kept & near.at(kept, 0, -1)
        ly = kept & near.at(kept, -1, 0)
        corners = corner_means(near, missed, kept, corner_components(near, lx, ly))
        for batch in self.batches:
            cells = xp.arange(batch.first, batch.last)
            held = xp.asarray(batch.maxima[2])
            batch.maxima[2] = self._rest(held * at_pixels(xp, corners, cells, self.basis_t))

    def result(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(cells, k * k) depth, speed and depth x speed on the host."""
        held = [np.concatenate([to_host(b.maxima[i]) for b in self.batches]) for i in range(3)]
        return held[0], held[1], held[2]
