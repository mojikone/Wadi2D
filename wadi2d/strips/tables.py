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
class Pixels:
    """A window of DEM pixels: ``z`` rows south, the west edge ``x0`` and north edge ``y0`` of pixel (0, 0)."""

    z: np.ndarray
    x0: float
    y0: float
    pixel: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.z.shape


@njit(cache=True)
def _sample(z, p, x0, y0, xs, ys):
    """The nearest pixel to each point, clipped to the window."""
    nr, nc = z.shape
    out = np.empty(xs.size)
    for m in range(xs.size):
        c = int(np.floor((xs[m] - x0) / p))
        r = int(np.floor((y0 - ys[m]) / p))
        out[m] = z[min(max(r, 0), nr - 1), min(max(c, 0), nc - 1)]
    return out


@njit(cache=True)
def _owners(ring_start, ring_node, x, y, x0, y0, p, nr, nc):
    """The cell whose ring holds each pixel's centre, -1 where none, by the crossing rule."""
    owner = -np.ones((nr, nc), np.int64)
    ncells = ring_start.size - 1
    for c in range(ncells):
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
        c0 = max(int(np.floor((xa - x0) / p)), 0)
        c1 = min(int(np.ceil((xb - x0) / p)), nc - 1)
        r0 = max(int(np.floor((y0 - yb) / p)), 0)
        r1 = min(int(np.ceil((y0 - ya) / p)), nr - 1)
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
                    owner[r, cc] = c
    return owner


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
) -> tuple[PolyMesh, np.ndarray]:
    """The mesh's tables; and the index of each kept face in the geometry (boundary faces and walls are left out).

    ``manning`` is one value or one per cell; a face takes the mean of its two cells', an interface face the strip
    cell's. ``wall`` marks faces that are closed; ``given_cw`` the crest coefficients objects gave the geometry's
    faces and ``crest`` the elevation they lift each face to, NaN where none (stage 6); ``ghosts`` the tile cells
    boundary faces open onto, kept as ghost cells after the real ones.
    """
    area, cx, cy = geo.areas_centroids()
    if (area <= 0.0).any():
        raise ValueError("every ring must be counter-clockwise and have an area")
    nr, nc = pix.shape
    owner = _owners(geo.ring_start, geo.ring_node, geo.x, geo.y, pix.x0, pix.y0, pix.pixel, nr, nc)
    order = np.argsort(owner, axis=None, kind="stable")
    sorted_owner = owner.ravel()[order]
    sorted_z = pix.z.ravel()[order]
    n = geo.ncells
    starts = np.searchsorted(sorted_owner, np.arange(n), side="left")
    ends = np.searchsorted(sorted_owner, np.arange(n), side="right")
    rows = cfg.rows
    zmin, zbar, hc = np.zeros(n), np.zeros(n), np.zeros(n)
    dtab = np.zeros((n, rows))
    tab = np.zeros(rows)
    for c in range(n):
        pixels = sorted_z[starts[c] : ends[c]]
        if pixels.size == 0:  # a sliver thinner than a pixel: its centroid's ground
            pixels = _sample(pix.z, pix.pixel, pix.x0, pix.y0, np.array([cx[c]]), np.array([cy[c]]))
        zm, rel, h = _cell_table(np.ascontiguousarray(pixels, dtype=np.float64), rows, tab)
        zmin[c], zbar[c], hc[c] = zm, zm + rel, h
        dtab[c] = tab
    nman = np.full(n, float(manning)) if np.isscalar(manning) else np.asarray(manning, dtype=np.float64)
    length, nfx, nfy, xf, yf = geo.faces(cx, cy)
    left, right = geo.face_cell[:, 0], geo.face_cell[:, 1]
    slot = np.full(right.size, -1, np.int64) if ghosts is None else np.asarray(ghosts.face_slot, np.int64)
    right = np.where(slot >= 0, n + slot, right)
    keep = right >= 0
    if wall is not None:
        keep &= ~np.asarray(wall, bool)
    kept = np.nonzero(keep)[0]
    if ghosts is not None:
        g = ghosts
        area = np.concatenate((area, g.area))
        cx, cy = np.concatenate((cx, g.cx)), np.concatenate((cy, g.cy))
        zmin, zbar, hc = np.concatenate((zmin, g.zmin)), np.concatenate((zbar, g.zbar)), np.concatenate((hc, g.hc))
        dtab = np.concatenate((dtab, g.dtab))
        nman = np.concatenate((nman, nman[left[slot >= 0]] if (slot >= 0).any() else np.zeros(0)))[: n + g.count]
        nman = np.concatenate((nman[:n], np.full(g.count, float(np.mean(nman[:n])))))
    m = kept.size
    zf, ef = np.zeros(m), np.zeros(m)
    ftab = np.zeros((m, rows, 2))
    ftab_one = np.zeros((rows, 2))
    for k, f in enumerate(kept):
        a, b = geo.face_node[f]
        prof, spacing = face_profile(pix, geo.x[a], geo.y[a], geo.x[b], geo.y[b])
        n_face = nman[left[f]] if right[f] >= n else 0.5 * (nman[left[f]] + nman[right[f]])
        lift = np.nan if crest is None else float(crest[f])
        zf[k], ef[k] = _face_table(
            prof, lift, spacing, 1.0 / n_face, np.ones(prof.size), 1.0, cfg.face_depth_min, cfg.face_depth_max, ftab_one
        )
        if cfg.face_conveyance == "local_radius" and np.isnan(lift):
            line, i0, i1, step = face_line(pix, geo.x[a], geo.y[a], geo.x[b], geo.y[b], cfg.local_radius_beta * cfg.face_depth_max)
            top = window_top(line, zf[k], ef[k], cfg.face_depth_max)
            if top > ef[k]:  # the table reaches the window's relief, as on the lattice (W49)
                zf[k], ef[k] = _face_table(prof, lift, spacing, 1.0 / n_face, np.ones(prof.size), 1.0, top, cfg.face_depth_max, ftab_one)
            e = min(i0, int(np.ceil(cfg.local_radius_beta * ef[k] / step)))
            line = line[i0 - e : i1 + e]
            _local_radius_conveyance(line, e, e + (i1 - i0), zf[k], ef[k], step, 1.0 / n_face, np.ones(i1 - i0), 1.0, cfg.local_radius_beta, ftab_one)
        ftab[k] = ftab_one
    cw = np.zeros(m) if given_cw is None else np.asarray(given_cw, dtype=np.float64)[kept]
    mesh = PolyMesh(
        area=area, cx=cx, cy=cy, zmin=zmin, zbar=zbar, hc=hc, dtab=dtab,
        left=left[kept].astype(np.int64), right=right[kept].astype(np.int64), length=length[kept],
        nx=nfx[kept], ny=nfy[kept], xf=xf[kept], yf=yf[kept], zf=zf, ef=ef, ftab=ftab, cw=cw, dx=float(dx),
        nreal=n if ghosts is not None else -1, ghost_state=None if ghosts is None else np.asarray(ghosts.state, np.int64),
    )  # fmt: skip
    return mesh.finish(cfg.crest_tolerance, given_cw=cw.copy()), kept
