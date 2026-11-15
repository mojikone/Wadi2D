# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A strip's pixel maxima a block of the map at a time (W86).

:mod:`wadi2d.strips.pixels` holds the rule and lays every pixel of the strip out at once, with eight weights and
eight 64-bit indices each. Block 2's aligned mesh at the 0.5 m pixel is 868 million strip pixels: 108 GB on the
host and 83 GB on the card, so its maps could not be made at all. Here the same rule runs on the cells whose pixels
a block of the rasters holds, with the rings of neighbours their surface reads, and the block's pixels stay on the
device for every saved map.

A cell's pixels read the fill offsets of the cells that share its nodes, which read theirs: ``edge_passes`` rings
out, and the levels one ring further. Those cells are worked with the block and their pixels thrown away, so the
block's own pixels read what the whole strip would give them. One thing only depends on the company a cell keeps:
the Newton fill of :class:`wadi2d.strips.pixels.StripMaxima` goes on until every cell of the lot has settled, so a
cell that still moves by less than the tolerance can take a step more in one lot than in another, a difference of
that tolerance at most, a tenth of a millimetre (Block 2 in 8 blocks against 23: 13,056 of 502 million wet pixels,
0.12 mm at most, no class changed). A strip that fits one block is the whole strip, to the digit.

The ground is read through the same pieces as :func:`wadi2d.strips.tables.owned_pixels`, whole, because a hole's
fill and a terrain object's edit see the window they are read in: each pixel is the pixel of the whole read.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.config.schema import Pixels as PixelRule
from wadi2d.config.schema import RunConfig
from wadi2d.products.ground import bed_stride
from wadi2d.products.strip_kernels import StripKernels, check_width
from wadi2d.products.surface import FILL_STEPS, FILL_TOLERANCE
from wadi2d.strips.pixels import MAX_NODES, WEIGHT_BLOCK, StripMaxima, _wachspress
from wadi2d.strips.tables import PIECE_PAD_PIXELS, BedPixels, _cell_pieces, _owners_of, _ring_ranges
from wadi2d.tables.parallel import ThreadBeds, run_all, table_workers

RINGS_MORE = 1
"""Rings of neighbours worked beyond those a cell's pixels read, for the links at the outer nodes."""
STRIP_HOST_BYTES = 72
"""Host bytes a strip pixel takes besides its weights while its block is gathered and written: its row, column,
cell and ground twice over as the pieces are joined and put in order, then its three maxima and its class."""
STRIP_FIXED_BYTES = 48
"""Device bytes a strip pixel takes while its block is worked, besides its weights: ground, cell, three maxima and
a map's work arrays."""


def rings(rule: PixelRule) -> int:
    """Rings of cells, through shared nodes, whose pixels are filled so a block's own pixels read true offsets."""
    return rule.edge_passes + RINGS_MORE


@dataclass
class StripBlock:
    """The cells of one block with their neighbours, renumbered in their own order, and the pixels of those that
    take pixels: what :class:`BlockStripMaxima` holds on the device."""

    ids: np.ndarray
    """The strip's own numbers of the block's cells, rising."""
    rows: np.ndarray
    """Pixel row from the grid's north edge."""
    cols: np.ndarray
    cell: np.ndarray
    """Each pixel's cell, in the block's numbers; pixels stand by cell, and in a cell in row order."""
    ground: np.ndarray
    weights: np.ndarray
    cell_inc: np.ndarray
    """(cells, width) the incidence of each node slot of a cell: every pixel of the cell reads these."""
    inc_cell: np.ndarray
    pair_a: np.ndarray
    pair_b: np.ndarray
    pair_face: np.ndarray
    zmin: np.ndarray
    sill: np.ndarray
    left: np.ndarray
    right: np.ndarray

    @property
    def count(self) -> int:
        return int(self.rows.size)


class StripReader:
    """A strip's pixels on demand: the ground, the node weights and the neighbours of any set of its cells."""

    def __init__(self, cfg: RunConfig, tables, strip, datum: float, cache=None) -> None:
        """``cache`` is the run's cache folder: the bed reads the DEM's chunk store there when it holds one (W84)."""
        from wadi2d.demstore import cache_folder, open_bed
        from wadi2d.terrain import Ground, RasterBed, apply_objects
        from wadi2d.terrain.sections import with_tables

        grid, geo, mesh = tables.grid, strip.strip.geometry, strip.mesh
        self.geo, self.mesh, self.datum = geo, mesh, datum
        self.n = mesh.real
        with RasterBed(cfg.terrain.dem) as probe:
            native = probe.native
        self.bed = bed = open_bed(cfg, cache if cache is not None else cache_folder(cfg), bed_stride(cfg, native))
        self.beds = ThreadBeds(bed)
        try:
            p = self.pixel = bed.pixel
            bed.bind(grid.x0, grid.y0)
            # the window of wadi2d.strips.pixels.strip_ground: pixel (0, 0) of the strip's own frame on the grid's
            self.col0 = int(np.floor((float(geo.x.min()) - grid.x0) / p)) - 1
            self.row0 = int(np.floor((grid.y0 - float(geo.y.max())) / p)) - 1
            ncols = int(np.ceil((float(geo.x.max()) - grid.x0) / p)) + 2 - self.col0
            nrows = int(np.ceil((grid.y0 - float(geo.y.min())) / p)) + 2 - self.row0
            objects = with_tables(cfg).terrain.objects
            edits = apply_objects(grid, objects, bed.pixel, cfg.terrain, Ground(bed, grid.x0, grid.y0))
            self.pix = BedPixels(
                bed, edits.edit, self.row0, self.col0, nrows, ncols, grid.x0 + self.col0 * p, grid.y0 - self.row0 * p, p, self.beds
            )  # fmt: skip
            self._lists(strip.kept)
        except BaseException:
            self.close()
            raise

    def _lists(self, kept: np.ndarray) -> None:
        """Pieces, ring boxes, incidences and face pairs of the whole strip: small, per cell and per face."""
        geo, mesh, n = self.geo, self.mesh, self.n
        _area, cx, cy = geo.areas_centroids()
        self.area = np.abs(_area[:n])
        self.centre = (cx[:n], cy[:n])
        self.box = _ring_ranges(geo, n, self.pix) if n else (np.zeros(0, np.int64),) * 4
        self.pieces = _cell_pieces(cx[:n], cy[:n], self.pix, mesh.dx) if n else []
        self.piece_of = np.zeros(n, np.int64)
        for q, own in enumerate(self.pieces):
            self.piece_of[own] = q
        self.ring_start, self.ring_node = np.asarray(geo.ring_start[: n + 1]), np.asarray(geo.ring_node)
        self.length = length = np.diff(self.ring_start)
        self.inc_cell = np.repeat(np.arange(n), length)
        self.inc_node = self.ring_node[self.ring_start[0] : self.ring_start[n]] if n else np.zeros(0, np.int64)
        self.nnodes = nnodes = geo.x.size
        keys = self.inc_cell.astype(np.int64) * nnodes + self.inc_node
        key_order = np.argsort(keys)
        sorted_keys = keys[key_order]

        def incidence_of(cells: np.ndarray, nodes: np.ndarray) -> np.ndarray:
            found = np.searchsorted(sorted_keys, cells.astype(np.int64) * nnodes + nodes)
            return key_order[np.minimum(found, sorted_keys.size - 1)]

        # the slots of each cell, padded to the widest ring with its first node, as each of its pixels had them
        self.width = width = max(MAX_NODES, int(length.max()) if length.size else MAX_NODES)
        self.cell_inc = np.zeros((n, width), np.int64)
        self.cell_node = np.zeros((n, width), np.int64)
        for m in np.unique(length):
            on = np.flatnonzero(length == m)
            nodes = np.stack([self.ring_node[self.ring_start[on] + k] for k in range(m)], axis=1)
            self.cell_node[on, :m] = nodes
            self.cell_inc[on, :m] = incidence_of(np.repeat(on, m), nodes.ravel()).reshape(-1, m)
            if m < width:
                self.cell_inc[on, m:] = self.cell_inc[on, :1]
        inner = np.nonzero(mesh.right < n)[0]
        left, right = mesh.left[inner], mesh.right[inner]
        u, v = geo.face_node[kept[inner], 0], geo.face_node[kept[inner], 1]
        self.pair_a = np.concatenate((incidence_of(left, u), incidence_of(left, v)))
        self.pair_b = np.concatenate((incidence_of(right, u), incidence_of(right, v)))
        self.pair_face = np.concatenate((inner, inner))

    def close(self) -> None:
        self.beds.close()
        self.bed.close()

    @property
    def pixel_bytes(self) -> int:
        """Device bytes one of the strip's pixels takes while its block is worked."""
        return STRIP_FIXED_BYTES + 4 * self.width

    @property
    def host_bytes(self) -> int:
        """Host bytes one of the strip's pixels takes while its block is gathered, worked and written."""
        return STRIP_HOST_BYTES + 4 * self.width

    # ---- where the strip's pixels are
    def _inside(self, c: int) -> np.ndarray:
        """Which pixels of one cell's box its ring holds, by the rule of the owners."""
        r0, r1, c0, c1 = (int(a[c]) for a in self.box)
        geo, pix = self.geo, self.pix
        one = np.array([c], np.int64)
        return _owners_of(
            geo.ring_start, geo.ring_node, geo.x, geo.y, one, pix.x0, pix.y0, pix.pixel, *pix.shape, r0, c0, r1 - r0 + 1, c1 - c0 + 1
        ) >= 0  # fmt: skip

    def extent(self) -> tuple[int, int, int, int] | None:
        """(first row, last row, first column, last column) of the strip's pixels on the grid's pixel frame, None
        when it has none: every pixel some ring holds is some cell's, so the cells that could reach an edge decide."""
        if self.n == 0:
            return None
        found = []
        # the first row, the last row, the first column, the last column: (the boxes' edge on that side, rows?)
        for side, along_rows in ((0, True), (1, True), (2, False), (3, False)):
            low = side % 2 == 0
            edges = self.box[side]
            origin = self.box[0 if along_rows else 2]
            best = None
            for c in np.argsort(edges if low else -edges, kind="stable"):
                edge = int(edges[c])
                if best is not None and (edge >= best if low else edge <= best):
                    break  # no later box reaches past the best pixel found
                held = np.flatnonzero(self._inside(int(c)).any(axis=1 if along_rows else 0))
                if held.size:
                    at = int(origin[c]) + int(held[0] if low else held[-1])
                    best = at if best is None else (min(best, at) if low else max(best, at))
            if best is None:
                return None
            found.append(best)
        return found[0] + self.row0, found[1] + self.row0, found[2] + self.col0, found[3] + self.col0

    def cells_in(self, row0: int, row1: int, col0: int, col1: int) -> np.ndarray:
        """The cells whose ring's box reaches pixel rows ``[row0, row1)`` and columns ``[col0, col1)`` of the grid's
        frame: every cell with a pixel there, and a few with none."""
        r0, r1, c0, c1 = self.box
        return (r1 + self.row0 >= row0) & (r0 + self.row0 < row1) & (c1 + self.col0 >= col0) & (c0 + self.col0 < col1)

    def grown(self, cells: np.ndarray, rings_out: int) -> np.ndarray:
        """``cells`` and ``rings_out`` rings of the cells that share a node with them."""
        out = cells.copy()
        for _ in range(rings_out):
            nodes = np.zeros(self.nnodes, bool)
            nodes[self.inc_node[out[self.inc_cell]]] = True
            out[self.inc_cell[nodes[self.inc_node]]] = True
        return out

    def window_pixels(self, size: int, top: int, left: int, shape: tuple[int, int]) -> np.ndarray:
        """About how many strip pixels each window of ``size`` pixels holds, on a lattice of ``shape`` windows from
        pixel (top, left) of the grid's frame: each cell's area at its centroid, for sizing the blocks."""
        cx, cy = self.centre
        r = np.floor((self.pix.y0 - cy) / self.pixel).astype(np.int64) + self.row0 - top
        c = np.floor((cx - self.pix.x0) / self.pixel).astype(np.int64) + self.col0 - left
        out = np.zeros(shape)
        np.add.at(out, (np.clip(r // size, 0, shape[0] - 1), np.clip(c // size, 0, shape[1] - 1)), self.area / self.pixel**2)
        return out

    # ---- a block
    def _pixels(self, take: np.ndarray) -> tuple[np.ndarray, ...]:
        """Rows, columns, cell and ground of the pixels of the cells in ``take``, as ``owned_pixels`` gives them:
        each piece's window read whole, a pixel two rings claim going to the later, by cell and in row order."""
        geo, pix, n = self.geo, self.pix, self.n
        nr, nc = pix.shape
        cr0, cr1, cc0, cc1 = self.box
        wanted = np.unique(self.piece_of[np.flatnonzero(take)])
        found: list = [None] * wanted.size
        pad = PIECE_PAD_PIXELS
        none = np.zeros(0, np.int32)

        def one(i: int) -> None:
            own = np.sort(self.pieces[wanted[i]])
            r_lo, r_hi = max(int(cr0[own].min()) - pad, 0), min(int(cr1[own].max()) + pad, nr - 1)
            c_lo, c_hi = max(int(cc0[own].min()) - pad, 0), min(int(cc1[own].max()) + pad, nc - 1)
            h, w = r_hi - r_lo + 1, c_hi - c_lo + 1
            near = np.flatnonzero((cr1 >= r_lo - 1) & (cr0 <= r_hi + 1) & (cc1 >= c_lo - 1) & (cc0 <= c_hi + 1))
            owner = _owners_of(geo.ring_start, geo.ring_node, geo.x, geo.y, near, pix.x0, pix.y0, pix.pixel, nr, nc, r_lo, c_lo, h, w)
            mine = np.zeros(n, bool)
            mine[own] = take[own]
            r, c = np.nonzero((owner >= 0) & mine[np.maximum(owner, 0)])
            if r.size == 0:
                found[i] = (none, none, none, np.zeros(0, np.float32))
                return
            z = np.asarray(pix.window(r_lo, c_lo, h, w), np.float64)
            small = np.int32  # a block holds tens of millions of pixels: their places as 32-bit numbers
            found[i] = ((r + r_lo).astype(small), (c + c_lo).astype(small), owner[r, c].astype(small), (z[r, c] - self.datum).astype(np.float32))

        run_all(range(wanted.size), one, table_workers(None))
        if not found:
            return none, none, none, np.zeros(0, np.float32)
        r, c, cell, ground = (np.concatenate([f[k] for f in found]) for k in range(4))
        order = np.argsort(cell, kind="stable")
        return r[order], c[order], cell[order], ground[order]

    def _weights(self, r: np.ndarray, c: np.ndarray, cell: np.ndarray) -> np.ndarray:
        """The Wachspress weights of each pixel's cell's nodes at the pixel, zero in a padded slot."""
        geo, pix = self.geo, self.pix
        weights = np.zeros((r.size, self.width), np.float32)
        for lo in range(0, r.size, WEIGHT_BLOCK):
            hi = min(lo + WEIGHT_BLOCK, r.size)
            rb, cb, cellb = r[lo:hi], c[lo:hi], cell[lo:hi]
            px = pix.x0 + (cb + 0.5) * pix.pixel
            py = pix.y0 - (rb + 0.5) * pix.pixel
            for m in np.unique(self.length[cellb]):
                on = np.flatnonzero(self.length[cellb] == m)
                nodes = self.cell_node[cellb[on], :m]
                weights[lo + on, :m] = _wachspress(px[on], py[on], geo.x[nodes], geo.y[nodes])
        return weights

    def sets(self, own: np.ndarray, rule: PixelRule) -> tuple[np.ndarray, np.ndarray]:
        """For a block whose own cells are ``own`` (a mask over the strip's cells): the cells whose pixels are
        filled, the rings their surface reads included, and those with one ring more, which gives its levels and
        takes no pixels."""
        take = self.grown(own, rings(rule))
        return take, self.grown(take, 1)

    def block(self, take: np.ndarray, every: np.ndarray) -> StripBlock | None:
        """The block of the cells of :meth:`sets`; None when none of them has a pixel."""
        n = self.n
        r, c, cell, ground = self._pixels(take)
        if r.size == 0:
            return None
        ids = np.flatnonzero(every)
        local = np.full(n, -1, np.int64)
        local[ids] = np.arange(ids.size)
        inc_ids = np.flatnonzero(every[self.inc_cell])
        inc_map = np.full(self.inc_cell.size, -1, np.int64)
        inc_map[inc_ids] = np.arange(inc_ids.size)
        mesh = self.mesh
        inner = mesh.right < n
        both = every[mesh.left] & inner & every[np.where(inner, mesh.right, 0)]
        face_ids = np.flatnonzero(both)
        face_map = np.full(mesh.left.size, -1, np.int64)
        face_map[face_ids] = np.arange(face_ids.size)
        pairs = both[self.pair_face]
        return StripBlock(
            ids=ids,
            rows=(r + self.row0).astype(np.int32),
            cols=(c + self.col0).astype(np.int32),
            cell=local[cell].astype(np.int32),
            ground=ground,
            weights=self._weights(r, c, cell),
            cell_inc=inc_map[self.cell_inc[ids]],
            inc_cell=local[self.inc_cell[inc_ids]].astype(np.int32),
            pair_a=inc_map[self.pair_a[pairs]],
            pair_b=inc_map[self.pair_b[pairs]],
            pair_face=face_map[self.pair_face[pairs]],
            zmin=(mesh.zmin[ids] - self.datum).astype(np.float32),
            sill=(mesh.zf[face_ids] - self.datum).astype(np.float32),
            left=local[mesh.left[face_ids]].astype(np.int32),
            right=local[mesh.right[face_ids]].astype(np.int32),
        )


class BlockStripMaxima(StripMaxima):
    """:class:`wadi2d.strips.pixels.StripMaxima` on a block: its steps on its numbers, with the sums of
    :mod:`wadi2d.products.strip_kernels` in place of scatter-adds and each pixel reading its cell's node slots in
    place of eight indices of its own."""

    def __init__(self, xp, block: StripBlock, rule: PixelRule) -> None:
        self.xp, self.rule, self.g = xp, rule, block
        self.n = n = int(block.ids.size)
        check_width(block.weights.shape[1])
        self.kernels = StripKernels(xp)
        a = xp.asarray
        self.ground = a(block.ground)
        self.cell = a(block.cell)
        self.weights = a(block.weights)
        self.cell_inc = a(block.cell_inc)
        self.inc_cell = a(block.inc_cell)
        self.ninc = int(block.inc_cell.size)
        self.pair_a, self.pair_b, self.pair_face = a(block.pair_a), a(block.pair_b), a(block.pair_face)
        self.zmin, self.sill = a(block.zmin), a(block.sill)
        self.face_l, self.face_r = a(block.left), a(block.right)
        ptr = np.zeros(n + 1, np.int64)  # the pixels stand by cell: cell c holds pixels ptr[c] to ptr[c + 1]
        np.cumsum(np.bincount(block.cell, minlength=n), out=ptr[1:])
        self.npix_cell = a(np.diff(ptr).astype(np.float32))
        self.ptr = a(ptr)
        self.depth = xp.zeros(block.count, xp.float32)
        self.speed = xp.zeros(block.count, xp.float32)
        self.dv = xp.zeros(block.count, xp.float32)
        self.cell_dv = xp.zeros(n, xp.float32)
        self._ordered: tuple = (None, None)

    def _at_pixels(self, node_value):
        return self.kernels.at_pixels(self.xp.ascontiguousarray(node_value[self.cell_inc]), self.cell, self.weights)

    def _node_means(self, label, value, weight):
        """The parent's means, a node's cells summed by rising number on the card as on the host."""
        xp = self.xp
        if self._ordered[0] is not label:  # one labelling a map: its order serves every mean of the map
            self._ordered = (label, self.kernels.label_order(label))
        own = value[self.inc_cell]
        w = weight[self.inc_cell].astype(xp.float32)
        total, count = self.kernels.label_sums(label, self._ordered[1], own, w)
        mean = total[label] / xp.maximum(count[label], 1.0)
        return xp.where(count[label] > 0.0, mean, own)

    def _fill_offset(self, relief, water):
        """The parent's Newton fill, a cell's pixels summed from first to last, and no step taken again by a cell
        whose offset has stopped moving: its next step would be the step it just took, to the bit."""
        xp = self.xp
        pixels = xp.maximum(self.npix_cell, 1.0)
        offset = self.kernels.cell_sums(self.ptr, relief) / pixels + water / pixels
        step = xp.zeros(self.n, xp.float32)
        moving = xp.ones(self.n, bool)
        for _ in range(FILL_STEPS):
            self.kernels.newton(self.ptr, relief, water, offset, step, moving)
            if not bool((xp.abs(step) > FILL_TOLERANCE).any()):
                break
        return offset

    def add(self, d, h, s, moment: bool = True) -> None:
        """The parent's map, operation for operation, with the pixels' arrays worked in place: a pixel then takes
        half the device memory, and a block holds twice the pixels."""
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
        relief = self._at_pixels(node_level)  # the surface, then the ground over it
        xp.subtract(self.ground, relief, out=relief)
        water = h * self.npix_cell
        offset = xp.zeros(self.n, xp.float32)
        around = xp.zeros(self.g.count, xp.float32)
        eased = xp.empty(self.g.count, xp.float32)
        for _ in range(rule.edge_passes):
            xp.subtract(relief, around, out=eased)
            offset = offset + self._fill_offset(eased, water)
            around = None  # freed before the next is made
            around = self._at_pixels(self._node_means(label, offset, wet))
        xp.subtract(relief, around, out=eased)
        final = self._fill_offset(eased, water)
        del eased
        pixel_depth = final[self.cell]
        pixel_depth += around
        pixel_depth -= relief
        del around, relief
        xp.maximum(pixel_depth, 0.0, out=pixel_depth)
        pixel_depth *= wet[self.cell]
        pixel_speed = self._at_pixels(node_speed)
        pixel_speed *= pixel_depth >= rule.depth_floor
        xp.maximum(self.depth, pixel_depth, out=self.depth)
        xp.maximum(self.speed, pixel_speed, out=self.speed)
        if moment:
            pixel_depth *= pixel_speed
            xp.maximum(self.dv, pixel_depth, out=self.dv)
            self.cell_dv = xp.maximum(self.cell_dv, d * s)
        self._ordered = (None, None)


__all__ = ["BlockStripMaxima", "StripBlock", "StripReader", "rings"]
