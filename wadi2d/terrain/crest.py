"""The face lattice: polylines as 4-connected staircases of grid edges.

Corners are ``(cj, ci)`` with corner (0, 0) at the grid origin, rows south. A horizontal lattice edge between
corners (cj, ci) and (cj, ci + 1) is the north face of cell (cj, ci); a vertical edge between (cj, ci) and
(cj + 1, ci) is the west face of cell (cj, ci). A 4-connected staircase is watertight: flow crosses faces only,
so it cannot slip through a corner. A staircase at 45 degrees is sqrt(2) longer than its line, hence the length
factor every edge carries.

Every corner of the walk carries its distance along the true line, and an edge's true length is the difference
between its two corners. The lengths therefore add up to the line exactly, however closely the vertices are
spaced: vertices that snap to one corner hand their length on to the next edge instead of losing it.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from wadi2d.grid.tiles import TileGrid

NORTH = 0
"""Axis of a horizontal lattice edge: a north face of a cell."""
WEST = 1
"""Axis of a vertical lattice edge: a west face of a cell."""

Corner = tuple[int, int]


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
    """True length of the edge over its lattice length."""
    corners: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), np.int64))
    """(n + 1, 2) every corner walked, on the grid or not."""
    length: float = 0.0
    """True length of the line, m."""

    @property
    def size(self) -> int:
        return int(self.axis.size)


def snap_corner(grid: TileGrid, x: float, y: float) -> Corner:
    """The nearest lattice corner (cj, ci) of a point."""
    return round((grid.y0 - y) / grid.dx), round((x - grid.x0) / grid.dx)


def _steps(a: Corner, b: Corner) -> list[Corner]:
    """The corners after ``a`` on the way to ``b``, nearest the straight line."""
    cj, ci = a
    dj, di = b[0] - a[0], b[1] - a[1]
    nj, ni = abs(dj), abs(di)
    sj, si = int(np.sign(dj)), int(np.sign(di))
    ix = iy = 0
    out: list[Corner] = []
    while ix < ni or iy < nj:
        if (1 + 2 * ix) * nj < (1 + 2 * iy) * ni:
            ci += si
            ix += 1
        else:
            cj += sj
            iy += 1
        out.append((cj, ci))
    return out


def _edge(a: Corner, b: Corner) -> tuple[int, int, int, int]:
    """(axis, j, i, side) of the edge from corner ``a`` to the next corner ``b``."""
    dj, di = b[0] - a[0], b[1] - a[1]
    if dj == 0:
        # east: its right is south, the face's positive normal; west: the reverse
        return NORTH, a[0], a[1] if di > 0 else a[1] - 1, di
    # south: its right is west, against the face's positive normal; north: the reverse
    return WEST, a[0] if dj > 0 else a[0] - 1, a[1], -dj


def _walk(grid: TileGrid, coordinates: Sequence[tuple[float, float]]) -> tuple[list[Corner], list[float]]:
    """Corners of a polyline with their distance along it; a step straight back cancels the step before."""
    points = np.asarray(coordinates, dtype=np.float64)
    corners = [snap_corner(grid, *points[0])]
    along = [0.0]
    total = 0.0

    def move_last(value: float) -> None:
        if len(along) > 1:
            along[-1] = value

    for p, q in itertools.pairwise(points):
        total += float(np.hypot(*(q - p)))
        steps = _steps(corners[-1], snap_corner(grid, *q))
        if not steps:
            move_last(total)
            continue
        start = along[-1]
        for n, corner in enumerate(steps, start=1):
            value = start + (total - start) * n / len(steps)
            if len(corners) > 1 and corner == corners[-2]:
                corners.pop()
                along.pop()
                move_last(value)
            else:
                corners.append(corner)
                along.append(value)
    move_last(total)
    return corners, along


def staircase(grid: TileGrid, coordinates: Sequence[tuple[float, float]]) -> Staircase:
    """Rasterise a polyline onto the lattice; every vertex snaps to its nearest corner."""
    corners, along = _walk(grid, coordinates)
    ny, nx = grid.shape
    rows: list[tuple[int, int, int, int, float, float]] = []
    for (a, b), (s0, s1) in zip(itertools.pairwise(corners), itertools.pairwise(along), strict=True):
        axis, j, i, side = _edge(a, b)
        if 0 <= j < ny and 0 <= i < nx:
            rows.append((axis, j, i, side, 0.5 * (s0 + s1), (s1 - s0) / grid.dx))
    table = np.array(rows, np.float64).reshape(-1, 6)
    return Staircase(
        table[:, 0].astype(np.int32),
        table[:, 1].astype(np.int32),
        table[:, 2].astype(np.int32),
        table[:, 3].astype(np.int32),
        table[:, 4],
        table[:, 5],
        np.array(corners, np.int64),
        float(along[-1]),
    )


def _extend(st: Staircase, start: Corner, end: Corner, s: float, grid: TileGrid) -> None:
    """Append the edges from ``start`` to ``end``; they close a gap and add no length to the line."""
    ny, nx = grid.shape
    path = [start, *_steps(start, end)]
    edges = [_edge(a, b) for a, b in itertools.pairwise(path)]
    edges = [e for e in edges if 0 <= e[1] < ny and 0 <= e[2] < nx]
    if not edges:
        return
    table = np.array(edges, np.int32)
    st.axis = np.concatenate((st.axis, table[:, 0]))
    st.j = np.concatenate((st.j, table[:, 1]))
    st.i = np.concatenate((st.i, table[:, 2]))
    st.side = np.concatenate((st.side, table[:, 3]))
    st.s = np.concatenate((st.s, np.full(len(edges), s)))
    st.factor = np.concatenate((st.factor, np.zeros(len(edges))))


def join_ends(lines: list[Staircase], reach_cells: float, grid: TileGrid) -> None:
    """Lines that end beside another line meet it on a shared corner.

    Two lines that touch on paper can snap to corners a cell apart, and water finds that gap. Each end not already
    on another line walks to the nearest corner of one within ``reach_cells``, whichever line was drawn first.
    """
    for n, st in enumerate(lines):
        others = [o.corners for m, o in enumerate(lines) if m != n and o.corners.size]
        if not others or st.corners.size == 0:
            continue
        pool = np.concatenate(others)
        for corner, s in ((st.corners[0], 0.0), (st.corners[-1], st.length)):
            gaps = np.hypot(*(pool - corner).T)
            nearest = int(np.argmin(gaps))
            if 0.0 < gaps[nearest] <= reach_cells:
                _extend(st, tuple(int(v) for v in corner), tuple(int(v) for v in pool[nearest]), s, grid)


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
