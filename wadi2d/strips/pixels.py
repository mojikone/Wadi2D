# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Depth, speed and depth x speed at the pixel over a strip's cells (W45, stage 7): W9's rule on polygons.

A strip cell holds one level and one mean depth. Here, as :mod:`wadi2d.products.surface` does for the squares, the
surface slopes through the cell's nodes: a node takes the mean level of the cells round it that are one body of
water there (joined across a face when both levels stand above the face's ground, or the higher does and the depths
are alike), the surface inside a cell is the Wachspress interpolation of its node values at the pixel centres, the
cell is then filled to its own water exactly (Newton on the offset, as W9), and the fill offsets are blended across
joined edges through the same node means so the surface does not step at an edge. The pixels of a cell are those
whose centre its ring holds, the ones its sub-grid table was built from.

One source for both backends: ``xp`` is CuPy or NumPy, scatters through :func:`_scatter_add` and :func:`_scatter_min`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import Pixels as PixelRule
from wadi2d.config.schema import RunConfig
from wadi2d.products.ground import bed_stride
from wadi2d.products.hazard import classify
from wadi2d.products.surface import FILL_STEPS, FILL_TOLERANCE
from wadi2d.strips.tables import BedPixels, Pixels, owned_pixels

WEIGHT_BLOCK = 1 << 22
"""Pixels whose node weights are taken at once: the weights' temporaries are some tens of bytes a pixel and node."""
MAX_NODES = 4
"""Corridor cells are quads, gap cells triangles."""
LABEL_PASSES = 8
"""Scatter-min passes that join a node's fan: a fan holds at most about eight cells."""
TINY = 1e-6
AREA_EPS = 1e-9


@dataclass
class StripGround:
    """The pixels of a strip's real cells, sorted by cell, with the weights of their cell's nodes at each pixel."""

    rows: np.ndarray
    """Pixel row from the grid's north edge, at ``pixel``."""
    cols: np.ndarray
    cell: np.ndarray
    ground: np.ndarray
    """z - datum, float32."""
    ptr: np.ndarray
    """CSR of pixels by cell, (ncells + 1)."""
    weights: np.ndarray
    """(npix, width) Wachspress weights, zero in a padded slot; width is the widest ring, 4 at least."""
    incidence: np.ndarray
    """(npix, width) index into the (cell, node) incidence list of each slot."""
    inc_cell: np.ndarray
    inc_node: np.ndarray
    pair_a: np.ndarray
    """Incidence pairs across each inner face at each of its two nodes, and the face of each pair."""
    pair_b: np.ndarray
    pair_face: np.ndarray
    pixel: float
    datum: float

    @property
    def count(self) -> int:
        return int(self.rows.size)


def _wachspress(px: np.ndarray, py: np.ndarray, vx: np.ndarray, vy: np.ndarray) -> np.ndarray:
    """Weights of a convex polygon's vertices (n, m, 2 as vx, vy) at points inside it; rings counter-clockwise."""
    m = vx.shape[1]
    prev, nxt = np.roll(np.arange(m), 1), np.roll(np.arange(m), -1)

    def area(ax, ay, bx, by, cx, cy):
        return 0.5 * ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))

    corner = area(vx[:, prev], vy[:, prev], vx, vy, vx[:, nxt], vy[:, nxt])
    left = area(px[:, None], py[:, None], vx[:, prev], vy[:, prev], vx, vy)
    right = area(px[:, None], py[:, None], vx, vy, vx[:, nxt], vy[:, nxt])
    scale = np.abs(corner).max(axis=1, keepdims=True) * AREA_EPS + 1e-12
    w = corner / (np.maximum(left, scale) * np.maximum(right, scale))
    return w / w.sum(axis=1, keepdims=True)


def ground_from_pixels(geo, mesh, kept: np.ndarray, pix: Pixels, grid_x0: float, grid_y0: float, datum: float) -> StripGround:
    """The strip's pixel ground from a DEM window, with everything the surface needs, built once per product step."""
    n = mesh.real
    ring_start, ring_node = np.asarray(geo.ring_start[: n + 1]), np.asarray(geo.ring_node)
    # the owners a piece of the window at a time (W81): one window over Block 2's strip at 1 m held tens of GB
    r, c, cell, zpix = owned_pixels(geo, n, pix, mesh.dx)
    ptr = np.zeros(n + 1, np.int64)
    np.add.at(ptr, cell + 1, 1)
    ptr = np.cumsum(ptr)
    # incidences (cell, node), one per ring entry
    length = np.diff(ring_start)
    inc_cell = np.repeat(np.arange(n), length)
    inc_node = ring_node[ring_start[0] : ring_start[n]]
    nnodes = geo.x.size
    keys = inc_cell.astype(np.int64) * nnodes + inc_node
    key_order = np.argsort(keys)
    sorted_keys = keys[key_order]

    def incidence_of(cells: np.ndarray, nodes: np.ndarray) -> np.ndarray:
        found = np.searchsorted(sorted_keys, cells.astype(np.int64) * nnodes + nodes)
        return key_order[np.minimum(found, sorted_keys.size - 1)]

    # the nodes of each pixel's cell, padded to the widest ring (MAX_NODES at least) with the first node and zero
    # weight: the ring corridors have quads and triangles, the centre mesh (W46) cells of up to max_faces sides
    npix = r.size
    width = max(MAX_NODES, int(length.max()) if length.size else MAX_NODES)
    weights = np.zeros((npix, width), np.float32)
    incidence = np.zeros((npix, width), np.int64)
    # the weights a block of pixels at a time: each pixel's own arithmetic, the temporaries bounded (W81)
    for lo in range(0, npix, WEIGHT_BLOCK):
        hi = min(lo + WEIGHT_BLOCK, npix)
        rb, cb, cellb = r[lo:hi], c[lo:hi], cell[lo:hi]
        px = pix.x0 + (cb + 0.5) * pix.pixel
        py = pix.y0 - (rb + 0.5) * pix.pixel
        for m in np.unique(length[cellb]):
            on = np.flatnonzero(length[cellb] == m)
            starts = ring_start[cellb[on]]
            nodes = np.stack([ring_node[starts + k] for k in range(m)], axis=1)
            w = _wachspress(px[on], py[on], geo.x[nodes], geo.y[nodes])
            weights[lo + on, :m] = w
            incidence[lo + on, :m] = incidence_of(np.repeat(cellb[on], m), nodes.ravel()).reshape(-1, m)
            if m < width:
                incidence[lo + on, m:] = incidence[lo + on, :1]
    # pairs across inner faces at both of their nodes
    inner = np.nonzero(mesh.right < n)[0]
    L, R = mesh.left[inner], mesh.right[inner]
    u, v = geo.face_node[kept[inner], 0], geo.face_node[kept[inner], 1]
    pair_a = np.concatenate((incidence_of(L, u), incidence_of(L, v)))
    pair_b = np.concatenate((incidence_of(R, u), incidence_of(R, v)))
    pair_face = np.concatenate((inner, inner))
    ground = (zpix - datum).astype(np.float32)
    return StripGround(r, c, cell, ground, ptr, weights, incidence, inc_cell, inc_node, pair_a, pair_b, pair_face, pix.pixel, datum)


def strip_ground(cfg: RunConfig, tables, strip, datum: float) -> StripGround:
    """The strip's pixel ground from the job's DEM at the pixel maps' stride, placed on the grid's pixel frame."""
    from wadi2d.tables.parallel import ThreadBeds
    from wadi2d.terrain import Ground, RasterBed, apply_objects
    from wadi2d.terrain.sections import with_tables

    grid, geo = tables.grid, strip.strip.geometry
    with RasterBed(cfg.terrain.dem) as probe:
        native = probe.native
    with RasterBed(cfg.terrain.dem, bed_stride(cfg, native)) as bed:
        p = bed.pixel
        bed.bind(grid.x0, grid.y0)
        col0 = int(np.floor((float(geo.x.min()) - grid.x0) / p)) - 1
        row0 = int(np.floor((grid.y0 - float(geo.y.max())) / p)) - 1
        ncols = int(np.ceil((float(geo.x.max()) - grid.x0) / p)) + 2 - col0
        nrows = int(np.ceil((grid.y0 - float(geo.y.min())) / p)) + 2 - row0
        objects = with_tables(cfg).terrain.objects
        edits = apply_objects(grid, objects, bed.pixel, cfg.terrain, Ground(bed, grid.x0, grid.y0))
        # the window read a piece at a time, the same edit on each: the ground the strip's tables stand on (W81)
        beds = ThreadBeds(bed)
        try:
            pix = BedPixels(bed, edits.edit, row0, col0, nrows, ncols, grid.x0 + col0 * p, grid.y0 - row0 * p, p, beds)
            found = ground_from_pixels(geo, strip.mesh, strip.kept, pix, grid.x0, grid.y0, datum)
        finally:
            beds.close()
    found.rows = found.rows + row0
    found.cols = found.cols + col0
    return found


def _scatter_add(xp, out, idx, val) -> None:
    if xp is np:
        np.add.at(out, idx, val)
    else:
        import cupyx

        cupyx.scatter_add(out, idx, val)


def _scatter_min(xp, out, idx, val) -> None:
    if xp is np:
        np.minimum.at(out, idx, val)
    else:
        import cupyx

        cupyx.scatter_min(out, idx, val)


class StripMaxima:
    """The three maxima per strip pixel over the saved maps, as :class:`wadi2d.products.pixels.PixelMaxima`."""

    def __init__(self, xp, ground: StripGround, mesh, rule: PixelRule) -> None:
        self.xp, self.rule, self.g = xp, rule, ground
        n = mesh.real
        self.n = n
        a = xp.asarray
        self.ground = a(ground.ground)
        self.cell = a(ground.cell.astype(np.int32))
        self.weights = a(ground.weights)
        self.incidence = a(ground.incidence)
        self.inc_cell = a(ground.inc_cell.astype(np.int32))
        self.ninc = int(ground.inc_cell.size)
        self.pair_a, self.pair_b = a(ground.pair_a), a(ground.pair_b)
        inner = ground.pair_face
        self.pair_face = a(inner)
        self.zmin = a((mesh.zmin[:n] - ground.datum).astype(np.float32))
        self.sill = a((mesh.zf - ground.datum).astype(np.float32))
        self.face_l, self.face_r = a(mesh.left.astype(np.int32)), a(mesh.right.astype(np.int32))
        self.npix_cell = xp.zeros(n, xp.float32)
        _scatter_add(xp, self.npix_cell, self.cell, xp.ones(ground.count, xp.float32))
        self.depth = xp.zeros(ground.count, xp.float32)
        self.speed = xp.zeros(ground.count, xp.float32)
        self.dv = xp.zeros(ground.count, xp.float32)
        self.cell_dv = xp.zeros(n, xp.float32)

    # ---- the surface
    def _labels(self, joined):
        """One label per incidence: the connected part of each node's fan the incidence belongs to."""
        xp = self.xp
        label = xp.arange(self.ninc, dtype=xp.int64)
        on = joined[self.pair_face]
        pa, pb = self.pair_a[on], self.pair_b[on]
        for _ in range(LABEL_PASSES):
            low = xp.minimum(label[pa], label[pb])
            _scatter_min(xp, label, pa, low)
            _scatter_min(xp, label, pb, low)
        return label

    def _node_means(self, label, value, weight):
        """Each incidence's mean of ``value`` over its label, weighted; its own value where the weight is zero."""
        xp = self.xp
        own = value[self.inc_cell]
        w = weight[self.inc_cell].astype(xp.float32)
        total = xp.zeros(self.ninc, xp.float32)
        count = xp.zeros(self.ninc, xp.float32)
        _scatter_add(xp, total, label, own * w)
        _scatter_add(xp, count, label, w)
        mean = total[label] / xp.maximum(count[label], 1.0)
        return xp.where(count[label] > 0.0, mean, own)

    def _at_pixels(self, node_value):
        return (node_value[self.incidence] * self.weights).sum(axis=1)

    def _fill_offset(self, relief, water):
        """The offset per cell that holds the cell's water under a surface of this shape (W9's Newton, ragged)."""
        xp = self.xp
        n, cell = self.n, self.cell
        mean_relief = xp.zeros(n, xp.float32)
        _scatter_add(xp, mean_relief, cell, relief)
        offset = mean_relief / xp.maximum(self.npix_cell, 1.0) + water / xp.maximum(self.npix_cell, 1.0)
        for _ in range(FILL_STEPS):
            gap = offset[cell] - relief
            under = gap > 0.0
            held = xp.zeros(n, xp.float32)
            count = xp.zeros(n, xp.float32)
            _scatter_add(xp, held, cell, gap * under)
            _scatter_add(xp, count, cell, under.astype(xp.float32))
            step = (held - water) / xp.maximum(count, 1.0)
            offset = offset - step
            if not bool((xp.abs(step) > FILL_TOLERANCE).any()):
                break
        return offset

    def add(self, d, h, s, moment: bool = True) -> None:
        """One map of the strip: level above zmin, mean depth and cell speed of every real cell."""
        xp, rule = self.xp, self.rule
        d, h, s = (xp.asarray(np.asarray(a, np.float32)) for a in (d, h, s))
        wet = d > 0.0
        level = self.zmin + d
        L, R = self.face_l, self.face_r
        inner = self.n > R
        Rs = xp.where(inner, R, 0)
        face = self.sill + rule.link_margin
        lo, hi = xp.minimum(level[L], level[Rs]), xp.maximum(level[L], level[Rs])
        alike = xp.minimum(d[L], d[Rs]) >= rule.link_ratio * xp.maximum(d[L], d[Rs])
        joined = inner & wet[L] & wet[Rs] & ((lo > face) | ((hi > face) & alike))
        label = self._labels(joined)
        s = s * (d > rule.depth_floor)
        node_level = self._node_means(label, level, wet)
        node_speed = self._node_means(label, s, s > 0.0)
        surface = self._at_pixels(node_level)
        relief = self.ground - surface
        water = h * self.npix_cell
        offset = xp.zeros(self.n, xp.float32)
        around = xp.zeros(self.g.count, xp.float32)
        for _ in range(rule.edge_passes):
            offset = offset + self._fill_offset(relief - around, water)
            around = self._at_pixels(self._node_means(label, offset, wet))
        final = self._fill_offset(relief - around, water)
        pixel_depth = xp.maximum(final[self.cell] + around - relief, 0.0) * wet[self.cell]
        pixel_speed = self._at_pixels(node_speed) * (pixel_depth >= rule.depth_floor)
        self.depth = xp.maximum(self.depth, pixel_depth)
        self.speed = xp.maximum(self.speed, pixel_speed)
        if moment:
            self.dv = xp.maximum(self.dv, pixel_depth * pixel_speed)
            self.cell_dv = xp.maximum(self.cell_dv, d * s)

    def lift_dv(self, run_hazard) -> None:
        xp = self.xp
        run = xp.asarray(np.asarray(run_hazard, np.float32))
        missed = xp.clip(run / xp.maximum(self.cell_dv, TINY), 1.0, self.rule.peak_lift)
        self.dv = self.dv * missed[self.cell]

    def result(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        host = (lambda a: a) if self.xp is np else self.xp.asnumpy
        return host(self.depth), host(self.speed), host(self.dv)


@dataclass
class StripPixelResult:
    rows: np.ndarray
    cols: np.ndarray
    classes: np.ndarray
    depth: np.ndarray
    speed: np.ndarray
    dv: np.ndarray


def strip_pixel_maxima(cfg: RunConfig, tables, strip, out, watch, xp, datum: float) -> StripPixelResult | None:
    """The strip's pixel maxima over the saved maps and the run's own peaks; None when the run saved no strip maps."""
    from wadi2d.products.frames import frame_names, read_strip_frames, strip_run_maxima

    results = out / "results.h5"
    peak = strip_run_maxima(results)
    if peak is None:
        return None
    ground = strip_ground(cfg, tables, strip, datum)
    if ground.count == 0:
        return None
    rule = cfg.outputs.pixels
    maxima = StripMaxima(xp, ground, strip.mesh, rule)
    for d, h, s in read_strip_frames(results, frame_names(results)):
        watch.check()
        maxima.add(d, h, s)
    maxima.add(peak["depth"], peak["mean_depth"], peak["speed"], moment=False)
    maxima.lift_dv(peak["hazard"])
    depth, speed, dv = maxima.result()
    return StripPixelResult(ground.rows, ground.cols, classify(depth, speed, dv, rule), depth, speed, dv)


__all__ = ["StripGround", "StripMaxima", "StripPixelResult", "ground_from_pixels", "strip_ground", "strip_pixel_maxima"]
