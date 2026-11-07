# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The lattice as a polygon mesh: every active cell a square, every face between two active cells, the tile tables
copied face by face (W45, stage 1).

This is the first gate of the strip path: on squares the polygon kernel must give the tile kernel's numbers, and the
tables are the same objects, so any difference is the kernel's. It is also how a tile cell appears to a strip at the
join in stage 3.

Conventions carried over from :mod:`wadi2d.solver.layout`: an x face is the west face of cell (j, i), between (j, i-1)
on its left and (j, i) on its right, normal (1, 0), discharge positive eastward; a y face is the north face of (j, i),
between (j-1, i) and (j, i), normal (0, -1) in map coordinates (rows run south), discharge positive southward, as the
engine's ``qy``.
"""

from __future__ import annotations

import numpy as np

from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.tables.builder import GridTables


def lattice_mesh(tables: GridTables) -> tuple[PolyMesh, np.ndarray]:
    """The lattice as polygons, finished; and the cell index of each grid cell, -1 where inactive."""
    grid = tables.grid
    mask = grid.mask
    ny, nx = mask.shape
    index = np.full((ny, nx), -1, np.int64)
    jj, ii = np.nonzero(mask)
    index[jj, ii] = np.arange(jj.size)
    cx, cy = grid.xy_of(jj, ii)
    hc = grid.from_tiles(tables.hc)
    dtab = grid.from_tiles(tables.dtab)
    dx = float(grid.dx)
    # x faces: (j, i-1) | (j, i)
    xj, xi = np.nonzero(mask & np.roll(mask, 1, axis=1))
    xj, xi = xj[xi > 0], xi[xi > 0]
    # y faces: (j-1, i) over (j, i)
    yj, yi = np.nonzero(mask & np.roll(mask, 1, axis=0))
    yj, yi = yj[yj > 0], yi[yj > 0]
    fields = {}
    for name in ("fl", "gl", "ef", "cw", "ftab"):
        fields[name + "x"] = grid.from_tiles(getattr(tables, name + "x"))[xj, xi]
        fields[name + "y"] = grid.from_tiles(getattr(tables, name + "y"))[yj, yi]
    zf = np.concatenate((fields["flx"] + tables.zmin[xj, xi - 1], fields["fly"] + tables.zmin[yj - 1, yi]))
    left = np.concatenate((index[xj, xi - 1], index[yj - 1, yi]))
    right = np.concatenate((index[xj, xi], index[yj, yi]))
    nf_x = xj.size
    nfx = np.concatenate((np.ones(nf_x), np.zeros(yj.size)))
    nfy = np.concatenate((np.zeros(nf_x), -np.ones(yj.size)))
    xf = np.concatenate((cx[index[xj, xi]] - 0.5 * dx, cx[index[yj, yi]]))
    yf = np.concatenate((cy[index[xj, xi]], cy[index[yj, yi]] + 0.5 * dx))
    mesh = PolyMesh(
        area=np.full(jj.size, dx * dx), cx=cx.astype(np.float64), cy=cy.astype(np.float64),
        zmin=tables.zmin[jj, ii].astype(np.float64), zbar=tables.zbar[jj, ii].astype(np.float64),
        hc=hc[jj, ii].astype(np.float64), dtab=dtab[jj, ii].astype(np.float64),
        left=left, right=right, length=np.full(left.size, dx), nx=nfx, ny=nfy, xf=xf, yf=yf, zf=zf,
        ef=np.concatenate((fields["efx"], fields["efy"])).astype(np.float64),
        ftab=np.concatenate((fields["ftabx"], fields["ftaby"])).astype(np.float64),
        cw=np.concatenate((fields["cwx"], fields["cwy"])).astype(np.float64), dx=dx,
    )  # fmt: skip
    # the tile tables already carry the natural crests: no new ones here
    return mesh.finish(np.inf, given_cw=mesh.cw.copy()), index


def to_grid(index: np.ndarray, values: np.ndarray, fill: float = 0.0) -> np.ndarray:
    """A per-cell array back on the (ny, nx) grid."""
    out = np.full(index.shape, fill, dtype=np.float64)
    on = index >= 0
    out[on] = values[index[on]]
    return out
