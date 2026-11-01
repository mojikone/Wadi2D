"""The face lattice: polylines as 4-connected staircases of grid edges.

Corners are ``(cj, ci)`` with corner (0, 0) at the grid origin, rows south. A horizontal lattice edge between
corners (cj, ci) and (cj, ci + 1) is the north face of cell (cj, ci); a vertical edge between (cj, ci) and
(cj + 1, ci) is the west face of cell (cj, ci). A 4-connected staircase is watertight: flow crosses faces only,
so it cannot slip through a corner. A staircase at 45 degrees is sqrt(2) longer than its line, hence the length
factor every edge carries.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from wadi2d.grid.tiles import TileGrid

NORTH = 0
"""Axis of a horizontal lattice edge: a north face of a cell."""
WEST = 1
"""Axis of a vertical lattice edge: a west face of a cell."""


@dataclass
class Staircase:
    """The edges of one polyline, in walking order. Edges off the grid are dropped."""

    axis: np.ndarray
    j: np.ndarray
    i: np.ndarray
    side: np.ndarray
    """+1 where the face's positive normal (east or south) points to the right of the line, else -1."""
    s: np.ndarray
    """Distance along the true line at the edge, m."""
    factor: np.ndarray
    """True length of its segment over lattice length of its segment."""

    @property
    def size(self) -> int:
        return int(self.axis.size)


def snap_corner(grid: TileGrid, x: float, y: float) -> tuple[int, int]:
    """The nearest lattice corner (cj, ci) of a point."""
    return round((grid.y0 - y) / grid.dx), round((x - grid.x0) / grid.dx)


def _walk(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    """Lattice edges from corner ``a`` to corner ``b``, nearest the straight line: (axis, j, i, side)."""
    cj, ci = a
    dj, di = b[0] - a[0], b[1] - a[1]
    nj, ni = abs(dj), abs(di)
    sj, si = int(np.sign(dj)), int(np.sign(di))
    ix = iy = 0
    out: list[tuple[int, int, int, int]] = []
    while ix < ni or iy < nj:
        if (1 + 2 * ix) * nj < (1 + 2 * iy) * ni:
            # east: its right is south, the face's positive normal; west: the reverse
            out.append((NORTH, cj, ci if si > 0 else ci - 1, si))
            ci += si
            ix += 1
        else:
            # south: its right is west, against the face's positive normal; north: the reverse
            out.append((WEST, cj if sj > 0 else cj - 1, ci, -sj))
            cj += sj
            iy += 1
    return out


def staircase(grid: TileGrid, coordinates: Sequence[tuple[float, float]]) -> Staircase:
    """Rasterise a polyline onto the lattice; every vertex snaps to its nearest corner."""
    axis: list[int] = []
    jj: list[int] = []
    ii: list[int] = []
    side: list[int] = []
    along: list[float] = []
    factor: list[float] = []
    ny, nx = grid.shape
    start = 0.0
    points = np.asarray(coordinates, dtype=np.float64)
    for p, q in itertools.pairwise(points):
        length = float(np.hypot(*(q - p)))
        edges = _walk(snap_corner(grid, *p), snap_corner(grid, *q))
        for n, (ax, j, i, sd) in enumerate(edges):
            if 0 <= j < ny and 0 <= i < nx:
                axis.append(ax)
                jj.append(j)
                ii.append(i)
                side.append(sd)
                along.append(start + length * (n + 0.5) / len(edges))
                factor.append(length / (len(edges) * grid.dx))
        start += length
    return Staircase(
        np.array(axis, np.int32),
        np.array(jj, np.int32),
        np.array(ii, np.int32),
        np.array(side, np.int32),
        np.array(along, np.float64),
        np.array(factor, np.float64),
    )


def line_lengths(coordinates: Sequence[tuple[float, float]]) -> np.ndarray:
    """Distance along a polyline at each vertex, m."""
    points = np.asarray(coordinates, dtype=np.float64)
    return np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(points, axis=0).T))))


def elevations_along(
    coordinates: Sequence[tuple[float, float]],
    z: Sequence[float] | None,
    z_constant: float | None,
    s: np.ndarray,
) -> np.ndarray:
    """Elevation at distances ``s`` along a polyline, from per-vertex values or a constant."""
    if z is None:
        return np.full(s.shape, float(z_constant))
    return np.interp(s, line_lengths(coordinates), np.asarray(z, dtype=np.float64))
