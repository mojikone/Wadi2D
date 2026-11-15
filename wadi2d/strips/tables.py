# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sub-grid tables for a polygon mesh from the DEM pixels (W45, stage 2), with the lattice's own table kernels.

A cell's table comes from the pixels whose centres lie inside its ring (the crossing rule), through ``_cell_table`` as
a square cell's does; a face's table from the ground sampled along its segment at the pixel spacing, the higher of the
two pixels either side of the segment, through ``_face_table``, as a lattice face reads the higher of its two pixel
columns. On a square lattice described as polygons the tables are the lattice's to the digit (the test). A face that
lies on a breakline samples the line's own ground: there is nothing to lift.

Boundary faces (no right cell) are left out: a missing face is a wall. Stage 3 gives the faces between a strip and the
tiles their tile cell instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

from wadi2d.config.schema import Tables
from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.tables.core import _cell_table, _face_table, _local_radius_conveyance, window_top
from wadi2d.tables.parallel import run_all, table_workers


@dataclass
class Ghosts:
    """The tile cells a strip touches (W45, stage 3): per geometry face the ghost slot it opens onto, -1 none; per
    ghost its tile state index, centre, lowest and mean bed, cell table and area, from the tile tables."""

    face_slot: np.ndarray
    state: np.ndarray
    cx: np.ndarray
    cy: np.ndarray
    zmin: np.ndarray
    zbar: np.ndarray
    hc: np.ndarray
    dtab: np.ndarray
    area: np.ndarray

    @property
    def count(self) -> int:
        return int(self.state.size)


@dataclass
class PieceTables:
    """The strip's own cells' and kept faces' tables as the pieces wrote them, before the ghosts join and the mesh is
    finished (W91): what a partial build takes for the pieces it does not build again."""

    zmin: np.ndarray
    zbar: np.ndarray
    hc: np.ndarray
    dtab: np.ndarray
    zf: np.ndarray
    ef: np.ndarray
    ftab: np.ndarray
    faces: tuple | None = None
    """What the job's crests, spillways and walls give the geometry's faces (``faces_from_objects``): a pit fill
    changes none of it, and it is a minute of Block 2's strip build."""


PIECE_CELLS = 32
"""The strip's tables are built a piece at a time (W81): the cells whose centroids share a square of this many lattice
cells a side, and their faces, with the DEM read under that piece alone. One window under the whole strip asked for
66.5 GiB on Block 2 at 0.5 m pixels."""
PIECE_PAD_PIXELS = 4
"""Pixels a piece's window reaches past its cells and faces, besides a face line's own reach: a face samples half a
pixel either side of its segment, its samples run up to one spacing past its ends."""


@dataclass
class Pixels:
    """A window of DEM pixels: ``z`` rows south, the west edge ``x0`` and north edge ``y0`` of pixel (0, 0)."""

    z: np.ndarray
    x0: float
    y0: float
    pixel: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.z.shape

    def window(self, row: int, col: int, nrows: int, ncols: int) -> np.ndarray:
        """Pixels ``[row, row + nrows)`` x ``[col, col + ncols)`` of the window, inside it."""
        return self.z[row : row + nrows, col : col + ncols]


@dataclass
class BedPixels:
    """The same window as ``Pixels`` without holding it: pieces of it read from a bed, the terrain edit applied to each
    as the square tiles have it (W81). ``row0`` and ``col0`` are the window's pixel (0, 0) on the bed. ``beds`` gives
    the bed of the calling thread when pieces are read on several; None reads ``bed`` itself."""

    bed: object
    edit: object
    row0: int
    col0: int
    nrows: int
    ncols: int
    x0: float
    y0: float
    pixel: float
    beds: object = None

    @property
    def shape(self) -> tuple[int, int]:
        return self.nrows, self.ncols

    def window(self, row: int, col: int, nrows: int, ncols: int) -> np.ndarray:
        bed = self.bed if self.beds is None else self.beds.get()
        z = np.asarray(bed.read(self.row0 + row, self.col0 + col, nrows, ncols), np.float64)
        if self.edit is not None:  # burn lines and shaped objects rebuild the strip's ground as they do the squares'
            self.edit(z, self.row0 + row, self.col0 + col)
        return z


@njit(cache=True, nogil=True)
def _sample_at(z, r_off, c_off, nr_all, nc_all, p, x0, y0, xs, ys):
    """The nearest pixel to each point, clipped to a window of ``nr_all`` x ``nc_all`` pixels of which ``z`` holds the
    piece from (``r_off``, ``c_off``) on; the point's pixel is found on the whole window, as ``_sample`` finds it."""
    nr, nc = z.shape
    out = np.empty(xs.size)
    for m in range(xs.size):
        c = int(np.floor((xs[m] - x0) / p))
        r = int(np.floor((y0 - ys[m]) / p))
        r = min(max(r, 0), nr_all - 1) - r_off
        c = min(max(c, 0), nc_all - 1) - c_off
        out[m] = z[min(max(r, 0), nr - 1), min(max(c, 0), nc - 1)]
    return out


@njit(cache=True, nogil=True)
def _sample(z, p, x0, y0, xs, ys):
    """The nearest pixel to each point, clipped to the window."""
    return _sample_at(z, 0, 0, z.shape[0], z.shape[1], p, x0, y0, xs, ys)


@njit(cache=True, nogil=True)
def _owners_of(ring_start, ring_node, x, y, cells, x0, y0, p, nr_all, nc_all, r_off, c_off, nr, nc):
    """``_owners`` on the piece of the window from (``r_off``, ``c_off``), ``nr`` x ``nc`` pixels, for ``cells`` in
    rising order: every cell whose pixels reach the piece must be among them, so a pixel two rings claim goes to the
    later one, as on the whole window."""
    owner = -np.ones((nr, nc), np.int64)
    for c in cells:
        a, b = ring_start[c], ring_start[c + 1]
        n = b - a
        xa = x[ring_node[a]]
        xb = xa
        ya = y[ring_node[a]]
        yb = ya
        for k in range(a, b):
            xa = min(xa, x[ring_node[k]])
            xb = max(xb, x[ring_node[k]])
            ya = min(ya, y[ring_node[k]])
            yb = max(yb, y[ring_node[k]])
        c0 = max(max(int(np.floor((xa - x0) / p)), 0), c_off)
        c1 = min(min(int(np.ceil((xb - x0) / p)), nc_all - 1), c_off + nc - 1)
        r0 = max(max(int(np.floor((y0 - yb) / p)), 0), r_off)
        r1 = min(min(int(np.ceil((y0 - ya) / p)), nr_all - 1), r_off + nr - 1)
        for r in range(r0, r1 + 1):
            py = y0 - (r + 0.5) * p
            for cc in range(c0, c1 + 1):
                px = x0 + (cc + 0.5) * p
                inside = False
                for m in range(n):
                    i1 = ring_node[a + m]
                    i2 = ring_node[a + (m + 1) % n]
                    x1, y1 = x[i1], y[i1]
                    x2, y2 = x[i2], y[i2]
                    if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                        inside = not inside
                if inside:
                    owner[r - r_off, cc - c_off] = c
    return owner


@njit(cache=True, nogil=True)
def _owners(ring_start, ring_node, x, y, x0, y0, p, nr, nc):
    """The cell whose ring holds each pixel's centre, -1 where none, by the crossing rule."""
    cells = np.arange(ring_start.size - 1)
    return _owners_of(ring_start, ring_node, x, y, cells, x0, y0, p, nr, nc, 0, 0, nr, nc)


@njit(cache=True, nogil=True)
def _along(z, r_off, c_off, nr_all, nc_all, p, x0, y0, ax, ay, bx, by, length, extra, m):
    """``face_line``'s ground on a piece: ``m`` samples of the segment plus ``extra`` past each end, the higher of the
    pixels half a pixel either side; ``length`` is the segment's, taken by numpy's hypot as ``face_line`` takes it."""
    count = m + 2 * extra
    xs = np.empty(count)
    ys = np.empty(count)
    for q in range(count):
        t = (q - extra + 0.5) / m
        xs[q] = ax + (bx - ax) * t
        ys[q] = ay + (by - ay) * t
    nx, ny = (by - ay) / max(length, 1e-12), -(bx - ax) / max(length, 1e-12)
    off = 0.5 * p
    z1 = _sample_at(z, r_off, c_off, nr_all, nc_all, p, x0, y0, xs - off * nx, ys - off * ny)
    z2 = _sample_at(z, r_off, c_off, nr_all, nc_all, p, x0, y0, xs + off * nx, ys + off * ny)
    return np.maximum(z1, z2)


@njit(cache=True, nogil=True)
def _piece_tables(
    z, r_off, c_off, nr_all, nc_all, p, x0, y0,
    own, starts, ends, sorted_z, cx, cy, zmin, zbar, hc, dtab,
    faces, ax, ay, bx, by, length, n_face, lift, e_lo, e_hi, local, beta, zf, ef, ftab,
):  # fmt: skip
    """The cell and face tables of one piece, as ``build_poly_tables`` built them on the whole window: ``own`` the
    piece's cells, their pixels ``sorted_z[starts:ends]`` in the window's row order; ``faces`` the slots of its faces
    in the outputs, with their segments, lengths, roughness and crest lift (NaN where none)."""
    rows = dtab.shape[1]
    tab = np.zeros(rows)
    for m in range(own.size):
        c = own[m]
        if ends[m] > starts[m]:
            pixels = np.ascontiguousarray(sorted_z[starts[m] : ends[m]])
        else:  # a sliver thinner than a pixel: its centroid's ground
            pixels = _sample_at(z, r_off, c_off, nr_all, nc_all, p, x0, y0, cx[c : c + 1], cy[c : c + 1])
        zm, rel, h = _cell_table(pixels, rows, tab)
        zmin[c], zbar[c], hc[c] = zm, zm + rel, h
        dtab[c, :] = tab
    reach = beta * e_hi
    for q in range(faces.size):
        k = faces[q]
        L = length[k]
        mm = max(int(np.ceil(L / p - 1e-9)), 1)
        spacing = L / mm
        prof = _along(z, r_off, c_off, nr_all, nc_all, p, x0, y0, ax[k], ay[k], bx[k], by[k], L, 0, mm)
        n_inv = 1.0 / n_face[k]
        zf[k], ef[k] = _face_table(prof, lift[k], spacing, n_inv, np.ones(prof.size), 1.0, e_lo, e_hi, ftab[k])
        if local and np.isnan(lift[k]):
            extra = int(np.ceil(reach / max(spacing, 1e-9)))
            line = _along(z, r_off, c_off, nr_all, nc_all, p, x0, y0, ax[k], ay[k], bx[k], by[k], L, extra, mm)
            i0, i1 = extra, extra + mm
            top = window_top(line, zf[k], ef[k], e_hi)
            if top > ef[k]:  # the table reaches the window's relief, as on the lattice (W49)
                zf[k], ef[k] = _face_table(prof, lift[k], spacing, n_inv, np.ones(prof.size), 1.0, top, e_hi, ftab[k])
            e = min(i0, int(np.ceil(beta * ef[k] / spacing)))
            part = line[i0 - e : i1 + e]
            _local_radius_conveyance(part, e, e + (i1 - i0), zf[k], ef[k], spacing, n_inv, np.ones(i1 - i0), 1.0, beta, ftab[k])


def face_line(pix: Pixels, ax: float, ay: float, bx: float, by: float, reach: float) -> tuple[np.ndarray, int, int, float]:
    """The ground along a face's line at the face's own sample spacing, reaching ``reach`` metres past both ends
    (W49, the local hydraulic radius's window); the face's own samples are ``[i0, i1)``, the same as ``face_profile``."""
    length = float(np.hypot(bx - ax, by - ay))
    m = max(int(np.ceil(length / pix.pixel - 1e-9)), 1)
    spacing = length / m
    extra = int(np.ceil(reach / max(spacing, 1e-9)))
    t = (np.arange(-extra, m + extra) + 0.5) / m
    xs, ys = ax + (bx - ax) * t, ay + (by - ay) * t
    nx, ny = (by - ay) / max(length, 1e-12), -(bx - ax) / max(length, 1e-12)
    off = 0.5 * pix.pixel
    z1 = _sample(pix.z, pix.pixel, pix.x0, pix.y0, xs - off * nx, ys - off * ny)
    z2 = _sample(pix.z, pix.pixel, pix.x0, pix.y0, xs + off * nx, ys + off * ny)
    return np.maximum(z1, z2), extra, extra + m, spacing


def face_profile(pix: Pixels, ax: float, ay: float, bx: float, by: float) -> tuple[np.ndarray, float]:
    """Ground along a segment at the pixel spacing: the higher of the pixels either side of it; and the spacing."""
    length = float(np.hypot(bx - ax, by - ay))
    m = max(int(np.ceil(length / pix.pixel - 1e-9)), 1)
    t = (np.arange(m) + 0.5) / m
    xs, ys = ax + (bx - ax) * t, ay + (by - ay) * t
    nx, ny = (by - ay) / max(length, 1e-12), -(bx - ax) / max(length, 1e-12)
    off = 0.5 * pix.pixel
    z1 = _sample(pix.z, pix.pixel, pix.x0, pix.y0, xs - off * nx, ys - off * ny)
    z2 = _sample(pix.z, pix.pixel, pix.x0, pix.y0, xs + off * nx, ys + off * ny)
    return np.maximum(z1, z2), length / m


def _pixel_ranges(xmin, ymin, xmax, ymax, pix) -> tuple[np.ndarray, ...]:
    """The pixel rows and columns a box reaches on the window, as ``_owners`` takes them, clipped to the window."""
    nr, nc = pix.shape
    p = pix.pixel
    c0 = np.clip(np.floor((xmin - pix.x0) / p).astype(np.int64), 0, nc - 1)
    c1 = np.clip(np.ceil((xmax - pix.x0) / p).astype(np.int64), 0, nc - 1)
    r0 = np.clip(np.floor((pix.y0 - ymax) / p).astype(np.int64), 0, nr - 1)
    r1 = np.clip(np.ceil((pix.y0 - ymin) / p).astype(np.int64), 0, nr - 1)
    return r0, r1, c0, c1


def _cell_pieces(cx: np.ndarray, cy: np.ndarray, pix, dx: float) -> list[np.ndarray]:
    """The cells by piece: those whose centroids share a square of ``PIECE_CELLS`` cells a side on the window."""
    side = PIECE_CELLS * dx
    key = np.floor((pix.y0 - cy) / side).astype(np.int64) * (1 << 31) + np.floor((cx - pix.x0) / side).astype(np.int64)
    order = np.argsort(key, kind="stable")
    return np.split(order, np.flatnonzero(np.diff(key[order])) + 1)


def _ring_ranges(geo, n: int, pix) -> tuple[np.ndarray, ...]:
    """The pixel box of each of the first ``n`` rings on the window."""
    first = geo.ring_start[:n]
    stop = geo.ring_start[n]
    xs, ys = geo.x[geo.ring_node[:stop]], geo.y[geo.ring_node[:stop]]
    return _pixel_ranges(
        np.minimum.reduceat(xs, first), np.minimum.reduceat(ys, first), np.maximum.reduceat(xs, first), np.maximum.reduceat(ys, first), pix
    )  # fmt: skip


def owned_pixels(geo, n: int, pix, dx: float, workers: int | None = None) -> tuple[np.ndarray, ...]:
    """The pixels of the first ``n`` cells, as ``_owners`` on the whole window gives them, read a piece at a time
    (W81): their rows and columns on the window, their cell and their ground, by cell and within a cell in the window's
    row order. A pixel two rings claim goes to the later of the first ``n``, as on the whole window."""
    empty = np.zeros(0, np.int64)
    if n == 0:
        return empty, empty, empty, np.zeros(0)
    area, cx, cy = geo.areas_centroids()
    nr, nc = pix.shape
    cr0, cr1, cc0, cc1 = _ring_ranges(geo, n, pix)
    pieces = _cell_pieces(cx[:n], cy[:n], pix, dx)
    found: list = [None] * len(pieces)
    pad = PIECE_PAD_PIXELS

    def one(q: int) -> None:
        own = np.sort(pieces[q])
        r_lo, r_hi = max(int(cr0[own].min()) - pad, 0), min(int(cr1[own].max()) + pad, nr - 1)
        c_lo, c_hi = max(int(cc0[own].min()) - pad, 0), min(int(cc1[own].max()) + pad, nc - 1)
        h, w = r_hi - r_lo + 1, c_hi - c_lo + 1
        near = np.flatnonzero((cr1 >= r_lo - 1) & (cr0 <= r_hi + 1) & (cc1 >= c_lo - 1) & (cc0 <= c_hi + 1))
        owner = _owners_of(geo.ring_start, geo.ring_node, geo.x, geo.y, near, pix.x0, pix.y0, pix.pixel, nr, nc, r_lo, c_lo, h, w)
        mine = np.zeros(n, bool)
        mine[own] = True
        r, c = np.nonzero((owner >= 0) & mine[np.maximum(owner, 0)])
        if r.size == 0:
            found[q] = (empty, empty, empty, np.zeros(0))
            return
        z = np.asarray(pix.window(r_lo, c_lo, h, w), np.float64)
        found[q] = (r + r_lo, c + c_lo, owner[r, c], z[r, c])

    run_all(range(len(pieces)), one, table_workers(workers))
    r, c, cell, z = (np.concatenate([f[k] for f in found]) for k in range(4))
    order = np.argsort(cell, kind="stable")  # a cell's pixels all come from its own piece, in the window's row order
    return r[order], c[order], cell[order], z[order]


def _build_in_pieces(
    geo, pix, cfg: Tables, dx, cx, cy, kept, n_face, lift, zmin, zbar, hc, dtab, zf, ef, ftab, workers=None, boxes=None
) -> None:
    """Every cell and kept face table, a piece at a time (W81): a piece is the cells whose centroids share a square of
    ``PIECE_CELLS`` cells a side, with the faces whose left cell it holds; its window covers their rings and their
    faces' sampling reach, and its owners are found among every cell that reaches the window, so each table is the
    one the whole window gave.

    ``boxes``, (n, 4) rows of (row0, col0, row1, col1) on the window, ends exclusive, builds only the pieces whose
    window holds a pixel of one (W91: the pieces a pit fill reaches); the others keep what the arrays hold."""
    n = geo.ncells
    if n == 0:
        return
    nr, nc = pix.shape
    p = pix.pixel
    local = cfg.face_conveyance == "local_radius"
    reach = cfg.local_radius_beta * cfg.face_depth_max if local else 0.0
    pad = int(np.ceil(reach / p)) + PIECE_PAD_PIXELS
    xs, ys = geo.x[geo.ring_node], geo.y[geo.ring_node]
    first = geo.ring_start[:-1]
    cr0, cr1, cc0, cc1 = _pixel_ranges(
        np.minimum.reduceat(xs, first), np.minimum.reduceat(ys, first), np.maximum.reduceat(xs, first), np.maximum.reduceat(ys, first), pix
    )  # fmt: skip
    a, b = geo.face_node[kept, 0], geo.face_node[kept, 1]
    ax, ay, bx, by = geo.x[a], geo.y[a], geo.x[b], geo.y[b]
    length = np.hypot(bx - ax, by - ay)  # numpy's hypot, as face_profile takes it
    fr0, fr1, fc0, fc1 = _pixel_ranges(np.minimum(ax, bx), np.minimum(ay, by), np.maximum(ax, bx), np.maximum(ay, by), pix)
    pieces = _cell_pieces(cx, cy, pix, dx)
    piece_of = np.empty(n, np.int64)
    for q, own in enumerate(pieces):
        piece_of[own] = q
    face_piece = piece_of[geo.face_cell[kept, 0]]
    face_order = np.argsort(face_piece, kind="stable")
    face_cuts = np.searchsorted(face_piece[face_order], np.arange(len(pieces) + 1))

    def window_of(q: int) -> tuple[np.ndarray, np.ndarray, int, int, int, int]:
        own = np.sort(pieces[q])
        faces = face_order[face_cuts[q] : face_cuts[q + 1]]
        r_lo = min(cr0[own].min(), fr0[faces].min(initial=nr)) - pad
        r_hi = max(cr1[own].max(), fr1[faces].max(initial=-1)) + pad
        c_lo = min(cc0[own].min(), fc0[faces].min(initial=nc)) - pad
        c_hi = max(cc1[own].max(), fc1[faces].max(initial=-1)) + pad
        r_lo, c_lo = max(int(r_lo), 0), max(int(c_lo), 0)
        r_hi, c_hi = min(int(r_hi), nr - 1), min(int(c_hi), nc - 1)
        return own, faces, r_lo, r_hi, c_lo, c_hi

    def one(q: int) -> None:
        own, faces, r_lo, r_hi, c_lo, c_hi = window_of(q)
        h, w = r_hi - r_lo + 1, c_hi - c_lo + 1
        z = np.ascontiguousarray(pix.window(r_lo, c_lo, h, w), dtype=np.float64)
        near = np.flatnonzero((cr1 >= r_lo - 1) & (cr0 <= r_hi + 1) & (cc1 >= c_lo - 1) & (cc0 <= c_hi + 1))
        owner = _owners_of(geo.ring_start, geo.ring_node, geo.x, geo.y, near, pix.x0, pix.y0, p, nr, nc, r_lo, c_lo, h, w)
        flat = owner.ravel()
        pick = np.argsort(flat, kind="stable")
        sorted_owner = flat[pick]
        sorted_z = z.ravel()[pick]
        starts = np.searchsorted(sorted_owner, own, side="left")
        ends = np.searchsorted(sorted_owner, own, side="right")
        _piece_tables(
            z, r_lo, c_lo, nr, nc, p, pix.x0, pix.y0, own, starts, ends, sorted_z, cx, cy, zmin, zbar, hc, dtab,
            np.ascontiguousarray(faces), ax, ay, bx, by, length, n_face, lift, cfg.face_depth_min, cfg.face_depth_max,
            local, cfg.local_radius_beta, zf, ef, ftab,
        )  # fmt: skip

    todo = range(len(pieces))
    if boxes is not None:
        b = np.asarray(boxes, np.int64).reshape(-1, 4)
        todo = []
        for q in range(len(pieces)):
            _own, _faces, r_lo, r_hi, c_lo, c_hi = window_of(q)
            if ((b[:, 0] <= r_hi) & (b[:, 2] > r_lo) & (b[:, 1] <= c_hi) & (b[:, 3] > c_lo)).any():
                todo.append(q)
    run_all(todo, one, table_workers(workers))  # pieces write their own cells and faces (W81)


def build_poly_tables(
    geo: MeshGeometry,
    pix: Pixels,
    cfg: Tables,
    dx: float,
    manning: float | np.ndarray = 0.035,
    wall: np.ndarray | None = None,
    given_cw: np.ndarray | None = None,
    ghosts: Ghosts | None = None,
    crest: np.ndarray | None = None,
    dn_floor: np.ndarray | None = None,
    workers: int | None = None,
    base: PieceTables | None = None,
    boxes: np.ndarray | None = None,
    keep_raw: bool = False,
) -> tuple[PolyMesh, np.ndarray]:
    """The mesh's tables; and the index of each kept face in the geometry (boundary faces and walls are left out).

    ``manning`` is one value or one per cell; a face takes the mean of its two cells', an interface face the strip
    cell's. ``wall`` marks faces that are closed; ``given_cw`` the crest coefficients objects gave the geometry's
    faces and ``crest`` the elevation they lift each face to, NaN where none (stage 6); ``ghosts`` the tile cells
    boundary faces open onto, kept as ghost cells after the real ones; ``dn_floor`` the least centre distance of
    each of the geometry's faces, m, where the mesher knows better than the mesh's own floor (the gorge rows, W52).

    ``base`` and ``boxes`` build only the pieces whose window holds a pixel of ``boxes`` (pixel boxes on ``pix``, see
    ``_build_in_pieces``) and take every other cell's and face's table from ``base``, the :class:`PieceTables` of a
    build of the same geometry on the same window that ``keep_raw`` kept (W91: a pit fill's pixels); the ghosts and
    the finish are done whole, so the result is the whole build's to the digit. ``keep_raw`` puts those tables on the
    mesh as ``raw``; without it the mesh has no ``raw``.
    """
    area, cx, cy = geo.areas_centroids()
    if (area <= 0.0).any():
        raise ValueError("every ring must be counter-clockwise and have an area")
    n = geo.ncells
    rows = cfg.rows
    zmin, zbar, hc = np.zeros(n), np.zeros(n), np.zeros(n)
    dtab = np.zeros((n, rows))
    nman = np.full(n, float(manning)) if np.isscalar(manning) else np.asarray(manning, dtype=np.float64)
    length, nfx, nfy, xf, yf = geo.faces(cx, cy)
    left, right = geo.face_cell[:, 0], geo.face_cell[:, 1]
    slot = np.full(right.size, -1, np.int64) if ghosts is None else np.asarray(ghosts.face_slot, np.int64)
    right = np.where(slot >= 0, n + slot, right)
    keep = right >= 0
    if wall is not None:
        keep &= ~np.asarray(wall, bool)
    kept = np.nonzero(keep)[0]
    m = kept.size
    zf, ef = np.zeros(m), np.zeros(m)
    ftab = np.zeros((m, rows, 2))
    lk, rk = left[kept], right[kept]
    n_face = np.where(rk >= n, nman[lk], 0.5 * (nman[lk] + nman[np.minimum(rk, n - 1)]))  # an interface face: the strip cell's
    lift = np.full(m, np.nan) if crest is None else np.asarray(crest, np.float64)[kept]
    if base is not None:
        if base.zmin.shape != zmin.shape or base.zf.shape != zf.shape or base.dtab.shape != dtab.shape:
            raise ValueError("a partial strip build needs the base tables of the same geometry and table rows")
        zmin, zbar, hc, dtab, zf, ef, ftab = (
            a.copy() for a in (base.zmin, base.zbar, base.hc, base.dtab, base.zf, base.ef, base.ftab)
        )
    _build_in_pieces(
        geo, pix, cfg, dx, cx, cy, kept, n_face, lift, zmin, zbar, hc, dtab, zf, ef, ftab, workers,
        boxes if base is not None else None,
    )  # fmt: skip
    # the arrays themselves: the ghosts join into new arrays and the finish makes a new zf, so these stay as written
    raw = PieceTables(zmin, zbar, hc, dtab, zf, ef, ftab) if keep_raw else None
    if ghosts is not None:
        g = ghosts
        area = np.concatenate((area, g.area))
        cx, cy = np.concatenate((cx, g.cx)), np.concatenate((cy, g.cy))
        zmin, zbar, hc = np.concatenate((zmin, g.zmin)), np.concatenate((zbar, g.zbar)), np.concatenate((hc, g.hc))
        dtab = np.concatenate((dtab, g.dtab))
        nman = np.concatenate((nman, nman[left[slot >= 0]] if (slot >= 0).any() else np.zeros(0)))[: n + g.count]
        nman = np.concatenate((nman[:n], np.full(g.count, float(np.mean(nman[:n])))))
    cw = np.zeros(m) if given_cw is None else np.asarray(given_cw, dtype=np.float64)[kept]
    mesh = PolyMesh(
        area=area, cx=cx, cy=cy, zmin=zmin, zbar=zbar, hc=hc, dtab=dtab,
        left=left[kept].astype(np.int64), right=right[kept].astype(np.int64), length=length[kept],
        nx=nfx[kept], ny=nfy[kept], xf=xf[kept], yf=yf[kept], zf=zf, ef=ef, ftab=ftab, cw=cw, dx=float(dx),
        nreal=n if ghosts is not None else -1, ghost_state=None if ghosts is None else np.asarray(ghosts.state, np.int64),
        dn_floor=None if dn_floor is None else np.asarray(dn_floor, np.float64)[kept], cut_faces=dn_floor is not None,
    )  # fmt: skip
    done = mesh.finish(cfg.crest_tolerance, given_cw=cw.copy())
    if raw is not None:
        done.raw = raw  # not a field of the mesh, and taken off it before the strip is cached (W91)
    return done, kept
