# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where a strip of aligned cells meets the squares, on the continuous surface (W100).

The squares the strip replaced are out of the lattice's mask, so a square beside the strip saw no neighbour there and
a strip cell saw only strip cells round its outer nodes: the surface stepped along the whole join, a staircase of
lattice edges that runs diagonally beside every oblique wadi. Here each side sees the other:

- the squares take each replaced square as a cell that shapes their surface and takes no pixels, holding the water of
  the strip cell whose ring holds its centre (:func:`wadi2d.products.cell_maps.strip_on_lattice`), across a face
  whose ground is the lowest ground of the square's own join faces;
- the squares' surface at the corners on the join is recorded map by map, and a strip cell takes it at a node of a
  join face that water passes, so both sides meet in one value there.

Every join face is a lattice edge (W46), so a join face's nodes are corners of the square it opens onto.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class StripJoin:
    """The join of a run's strip and its squares."""

    rows: np.ndarray
    """Lattice row and column of each replaced square that a strip cell's ring holds the centre of, and that cell."""
    cols: np.ndarray
    cells: np.ndarray
    sill: np.ndarray
    """The lowest ground of each square's join faces over the run's own datum; infinite off the join (grid shape)."""
    face_cell: np.ndarray
    """Per join face: the strip cell, the square's row and column, the face's ground, its two nodes, and the corner of
    the square each node is."""
    face_row: np.ndarray
    face_col: np.ndarray
    face_ground: np.ndarray
    face_node: np.ndarray
    face_corner: np.ndarray

    def ghosts_in(self, rows: tuple[int, int], cols: tuple[int, int], keep: np.ndarray):
        """The replaced squares inside rows ``[a, b)`` and columns ``[a, b)`` that touch a kept square there, with
        their strip cells: the cells the squares of that window take as neighbours."""
        inside = (self.rows >= rows[0]) & (self.rows < rows[1]) & (self.cols >= cols[0]) & (self.cols < cols[1])
        r, c, cell = self.rows[inside], self.cols[inside], self.cells[inside]
        near = np.zeros(r.size, bool)
        ny, nx = keep.shape
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                if dj or di:
                    rr, cc = r - rows[0] + dj, c - cols[0] + di
                    ok = (rr >= 0) & (rr < ny) & (cc >= 0) & (cc < nx)
                    near[ok] |= keep[rr[ok], cc[ok]]
        return r[near], c[near], cell[near]


def strip_join(tables, datum: float) -> StripJoin | None:
    """The join of the run's strip and squares, or None on a run without a strip."""
    from wadi2d.products.cell_maps import strip_on_lattice

    found = strip_on_lattice(tables)
    if found is None:
        return None
    rows, cols, cells = found
    strip, grid = tables.strip, tables.grid
    mesh, geo = strip.mesh, strip.strip.geometry
    n = mesh.real
    join = np.nonzero(mesh.right >= n)[0]
    dx = grid.dx
    xf, yf = np.asarray(mesh.xf)[join], np.asarray(mesh.yf)[join]
    nx_, ny_ = np.asarray(mesh.nx)[join], np.asarray(mesh.ny)[join]
    face_col = np.floor((xf + 0.5 * dx * nx_ - grid.x0) / dx).astype(np.int64)
    face_row = np.floor((grid.y0 - (yf + 0.5 * dx * ny_)) / dx).astype(np.int64)
    ground = (np.asarray(mesh.zf)[join] - datum).astype(np.float32)
    nodes = np.asarray(geo.face_node)[np.asarray(strip.kept)[join]]
    corner = np.zeros(nodes.shape, np.int8)
    for k in range(2):
        x, y = np.asarray(geo.x)[nodes[:, k]], np.asarray(geo.y)[nodes[:, k]]
        south = np.rint((grid.y0 - y) / dx).astype(np.int64) - face_row  # 0 on the square's north edge, 1 its south
        east = np.rint((x - grid.x0) / dx).astype(np.int64) - face_col
        corner[:, k] = np.clip(south, 0, 1) * 2 + np.clip(east, 0, 1)
    sill = np.full(grid.shape, np.inf, np.float32)
    inside = (face_row >= 0) & (face_row < grid.shape[0]) & (face_col >= 0) & (face_col < grid.shape[1])
    np.minimum.at(sill, (face_row[inside], face_col[inside]), ground[inside])
    return StripJoin(
        rows, cols, cells, sill, np.asarray(mesh.left)[join].astype(np.int64), face_row, face_col, ground, nodes, corner
    )


__all__ = ["StripJoin", "strip_join"]
