# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The polygon mesh contract: cells of any shape and the faces between them, with their sub-grid tables (W45).

A cell is a list of faces; the kernel never sees its vertices. Per cell: plan area, centroid, the sub-grid cell table
(``zmin``, ``zbar``, ``hc``, ``dtab``) as the lattice builds it. Per face: the two cells ``L`` and ``R``, length, unit
normal from L to R, midpoint, the centre-to-centre distance along the normal ``dn``, the skew vector ``s`` (the rest of
the centre-to-centre vector), the invert ``zf``, the table top ``ef`` and the face table ``ftab`` as the lattice builds
them, and the crest coefficient ``cw`` (0 none; positive the depth cap of a natural crest or a crest line; negative the
energy-head cap). ``finish`` derives what the kernel reads: inverts over the cells' minima and mean beds, ``dn`` floored,
the skew, and the natural crests.

Every array is structure-of-arrays, cells and faces each in one order, so the same contract serves the CPU twin, the
CUDA kernels and the file the mesher writes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wadi2d.config.constants import CRITICAL_WEIR_COEFF

DN_MIN = 0.15
"""Floor of the centre-to-centre distance along the face normal, as a share of the reference cell size: a badly skewed
face keeps a finite pressure drive (W3's choice)."""


@dataclass
class PolyMesh:
    """Cells and faces with their tables; built once, read by the kernels."""

    # cells
    area: np.ndarray
    cx: np.ndarray
    cy: np.ndarray
    zmin: np.ndarray
    zbar: np.ndarray
    hc: np.ndarray
    dtab: np.ndarray
    """(ncells, rows)."""
    # faces
    left: np.ndarray
    right: np.ndarray
    length: np.ndarray
    nx: np.ndarray
    ny: np.ndarray
    xf: np.ndarray
    yf: np.ndarray
    zf: np.ndarray
    ef: np.ndarray
    ftab: np.ndarray
    """(nfaces, rows, 2): area, and conveyance to the power 3/5."""
    cw: np.ndarray
    dx: float
    """The reference cell size: the lattice's, for the floors the kernel shares with it."""
    # derived by finish
    dn: np.ndarray | None = None
    sx: np.ndarray | None = None
    sy: np.ndarray | None = None
    fl: np.ndarray | None = None
    fr: np.ndarray | None = None
    gl: np.ndarray | None = None
    gr: np.ndarray | None = None
    nreal: int = -1
    """Cells stepped here; the rest are ghosts, tile cells a hybrid mirrors each step. -1: every cell."""
    ghost_state: np.ndarray | None = None
    """The tile state index of each ghost, in order."""
    dzl: np.ndarray | None = None
    """Half the bed's drop from the left cell's centre to each face, the face's invert below the invert of the left
    cell's opposite face, over two; given (the lattice) or derived by finish (W47). Ghost sides are zero."""
    dzr: np.ndarray | None = None
    """The same from the right cell."""

    @property
    def ncells(self) -> int:
        return int(self.area.size)

    @property
    def real(self) -> int:
        return self.ncells if self.nreal < 0 else int(self.nreal)

    @property
    def nfaces(self) -> int:
        return int(self.left.size)

    @property
    def rows(self) -> int:
        return int(self.dtab.shape[1])

    def finish(self, crest_tolerance: float, given_cw: np.ndarray | None = None) -> PolyMesh:
        """Derive what the kernel reads. ``given_cw`` holds the coefficients objects gave (crest lines, the cap);
        where it is 0 a face that stands above both cells' mean beds by more than ``crest_tolerance`` is a natural crest."""
        L, R = self.left, self.right
        # the lattice's rule: every invert at or above both cells' minima, or a dry cell shows a wet face
        self.zf = np.maximum(np.maximum(self.zf, self.zmin[L]), self.zmin[R])
        dcx, dcy = self.cx[R] - self.cx[L], self.cy[R] - self.cy[L]
        dn = dcx * self.nx + dcy * self.ny
        self.dn = np.maximum(dn, DN_MIN * self.dx)
        self.sx = dcx - self.dn * self.nx
        self.sy = dcy - self.dn * self.ny
        self.fl = self.zf - self.zmin[L]
        self.fr = self.zf - self.zmin[R]
        self.gl = self.zf - self.zbar[L]
        self.gr = self.zf - self.zbar[R]
        natural = (self.gl > crest_tolerance) & (self.gr > crest_tolerance)
        given = np.zeros(self.nfaces) if given_cw is None else np.asarray(given_cw, dtype=np.float64)
        self.cw = np.where(given != 0.0, given, np.where(natural, CRITICAL_WEIR_COEFF, 0.0))
        if self.dzl is None or self.dzr is None:
            self.dzl, self.dzr = opposite_drops(L.astype(np.int64), R.astype(np.int64), self.nx, self.ny, self.zf, self.ncells, self.real)
        return self

    def skew_degrees(self) -> np.ndarray:
        """The angle between each face's normal and its centre-to-centre line: 0 on an orthogonal mesh."""
        return np.degrees(np.arctan2(np.hypot(self.sx, self.sy), self.dn))

    def faces_of(self) -> list[np.ndarray]:
        """The faces of each cell, by index, for the readers that need a cell's ring."""
        found: list[list[int]] = [[] for _ in range(self.ncells)]
        for f, (a, b) in enumerate(zip(self.left.tolist(), self.right.tolist(), strict=True)):
            found[a].append(f)
            found[b].append(f)
        return [np.array(v, np.int64) for v in found]


def opposite_drops(L, R, nx, ny, zf, ncells, nreal):
    """Per face, half the bed's drop from each side's cell centre to the face (W47): for the cell on that side, the
    face whose outward normal is the most nearly opposite to this face's, at least 120 degrees away, gives the inflow
    edge; the drop is that face's invert less this face's, over two. Ghost cells and cells with no opposite face give
    zero. On the lattice it is half the drop between a cell's west and east (north and south) face inverts."""
    from numba import njit

    @njit(cache=False)
    def _drops(L, R, nx, ny, zf, ncells, nreal, dzl, dzr):
        nf = L.size
        count = np.zeros(ncells + 1, np.int64)
        for f in range(nf):
            count[L[f] + 1] += 1
            count[R[f] + 1] += 1
        for c in range(ncells):
            count[c + 1] += count[c]
        fill = count[:-1].copy()
        face = np.empty(2 * nf, np.int64)
        sign = np.empty(2 * nf, np.float64)
        for f in range(nf):
            a, b = L[f], R[f]
            face[fill[a]] = f
            sign[fill[a]] = 1.0
            fill[a] += 1
            face[fill[b]] = f
            sign[fill[b]] = -1.0
            fill[b] += 1
        for f in range(nf):
            for side in range(2):
                c = L[f] if side == 0 else R[f]
                if c >= nreal:
                    continue
                s_f = 1.0 if side == 0 else -1.0
                ox, oy = s_f * nx[f], s_f * ny[f]
                best, best_dot = -1, -0.5
                for p in range(count[c], count[c + 1]):
                    g = face[p]
                    if g == f:
                        continue
                    dot = sign[p] * (nx[g] * ox + ny[g] * oy)
                    if dot < best_dot:
                        best, best_dot = g, dot
                if best >= 0:
                    value = 0.5 * (zf[best] - zf[f])
                    if np.isfinite(value):
                        if side == 0:
                            dzl[f] = value
                        else:
                            dzr[f] = value

    dzl = np.zeros(L.size)
    dzr = np.zeros(L.size)
    _drops(L, R, np.asarray(nx, np.float64), np.asarray(ny, np.float64), np.asarray(zf, np.float64), int(ncells), int(nreal), dzl, dzr)
    return dzl, dzr
