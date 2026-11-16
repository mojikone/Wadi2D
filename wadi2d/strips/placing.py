# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows of a line's centres, compiled (W92).

``centres.place_centres`` walks every centre beyond a line's pair in Python: a tree query against the higher lines'
centres, the active squares, the line's own centres. On Block 2 that walk was 21 s for 190,000 centres. Here it runs
in the same order with the same tests, against centres binned on a lattice of ``clearance``-sized squares, by the
distance a tree gives (the square root of the sum of the squared differences), so every centre it places, and every
row it stops, is the walk's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit, types
from numba.typed import Dict
from scipy.spatial import cKDTree

OFFSET = 1 << 20
"""Bin indices are shifted by this before they are packed into one key: a lattice of 40 m bins reaches 40,000 km."""


@dataclass
class ActiveSquares:
    """Whether points stand in active squares of the lattice, clear (over ``radius``) of the squares kept for the
    boundaries: callable on an (n, 2) array, as the generator's ``inside`` was, and readable by the kernel."""

    mask: np.ndarray
    x0: float
    y0: float
    dx: float
    kept: np.ndarray | None
    """(m, 2) centres of the kept squares, or None."""
    radius: float

    def __post_init__(self) -> None:
        self.tree = cKDTree(self.kept) if self.kept is not None and self.kept.shape[0] else None

    def __call__(self, xy: np.ndarray) -> np.ndarray:
        ny, nx = self.mask.shape
        j = np.floor((self.y0 - xy[:, 1]) / self.dx).astype(np.int64)
        i = np.floor((xy[:, 0] - self.x0) / self.dx).astype(np.int64)
        ok = (j >= 0) & (j < ny) & (i >= 0) & (i < nx)
        ok[ok] = self.mask[j[ok], i[ok]]
        if self.tree is not None and ok.any():
            d, _ = self.tree.query(xy[ok])
            ok[np.nonzero(ok)[0][d <= self.radius]] = False
        return ok


def new_bins():
    return Dict.empty(key_type=types.int64, value_type=types.int64)


@njit(cache=True)
def _key(gx, gy):
    return ((gx + OFFSET) << 21) | (gy + OFFSET)


@njit(cache=True)
def _add(heads, size, px, py, nxt, n, x, y):
    gx = np.int64(np.floor(x / size))
    gy = np.int64(np.floor(y / size))
    key = _key(gx, gy)
    nxt[n] = heads[key] if key in heads else -1  # noqa: SIM401 (get with a default types as Optional in numba)
    heads[key] = n
    px[n] = x
    py[n] = y


@njit(cache=True)
def _any_within(heads, size, px, py, nxt, tag, want, same, x, y, radius, closed):
    """Whether a binned point lies within ``radius`` of (x, y) (``closed``: at or within), among the points whose
    ``tag`` equals ``want`` (``same``) or differs from it."""
    gx = np.int64(np.floor(x / size))
    gy = np.int64(np.floor(y / size))
    reach = np.int64(np.ceil(radius / size)) + 1
    for ax in range(gx - reach, gx + reach + 1):
        for ay in range(gy - reach, gy + reach + 1):
            key = _key(ax, ay)
            q = heads[key] if key in heads else -1  # noqa: SIM401
            while q >= 0:
                if (tag[q] == want) == same:
                    ddx = x - px[q]
                    ddy = y - py[q]
                    d = np.sqrt(ddx * ddx + ddy * ddy)
                    if d < radius or (closed and d == radius):
                        return True
                q = nxt[q]
    return False


@njit(cache=True)
def _inside(mask, x0, y0, dx, kheads, ksize, kx, ky, knxt, ktag, kradius, has_kept, x, y):
    ny, nx = mask.shape
    j = np.int64(np.floor((y0 - y) / dx))
    i = np.int64(np.floor((x - x0) / dx))
    if j < 0 or j >= ny or i < 0 or i >= nx or not mask[j, i]:
        return False
    return not (has_kept and _any_within(kheads, ksize, kx, ky, knxt, ktag, 0, True, x, y, kradius, True))


@njit(cache=True)
def rows_of_line(
    pts, normals, n_left, n_right, pieces, k, dx, clearance,
    heads, size, px, py, nxt, line, station, side_of, row, n,
    has_inside, mask, x0, y0, kheads, ksize, kx, ky, knxt, ktag, kradius, has_kept,
):  # fmt: skip
    """The centres of line ``k``'s ``pieces`` (start, end) of stations, appended from ``n`` on: per piece the left
    side then the right, per station the rows outward, the first row (the pair) always, a row beyond it only while
    it stands clear of the higher lines' centres, inside the active squares and over half a cell from the line's
    own. Returns the new count."""
    own = 0
    for pi in range(pieces.shape[0]):
        a, b = pieces[pi, 0], pieces[pi, 1]
        for side_index in range(2):
            side = 1 if side_index == 0 else -1
            sign = 1.0 if side_index == 0 else -1.0
            for i in range(a, b):
                count = n_left[i] if side_index == 0 else n_right[i]
                for j in range(count):
                    f = sign * (j + 0.5) * dx
                    x = pts[i, 0] + f * normals[i, 0]
                    y = pts[i, 1] + f * normals[i, 1]
                    if j > 0:
                        if _any_within(heads, size, px, py, nxt, line, k, False, x, y, clearance, False):
                            break  # this row and the rows beyond it on this side give way
                        if has_inside and not _inside(mask, x0, y0, dx, kheads, ksize, kx, ky, knxt, ktag, kradius, has_kept, x, y):
                            break  # the rows stop at the domain's edge
                        if own and _any_within(heads, size, px, py, nxt, line, k, True, x, y, 0.5 * dx, False):
                            break  # the line's own rows meeting inside a bend
                    _add(heads, size, px, py, nxt, n, x, y)
                    line[n] = k
                    station[n] = i
                    side_of[n] = side
                    row[n] = j
                    n += 1
                    own += 1
    return n


class Store:
    """The placed centres, binned, with room to grow."""

    def __init__(self, size: float) -> None:
        self.size = size
        self.heads = new_bins()
        self.n = 0
        self._arrays(1024)

    def _arrays(self, capacity: int) -> None:
        old = getattr(self, "px", None)
        fresh = {"px": np.empty(capacity), "py": np.empty(capacity), "nxt": np.empty(capacity, np.int64),
                 "line": np.empty(capacity, np.int64), "station": np.empty(capacity, np.int64),
                 "side": np.empty(capacity, np.int64), "row": np.empty(capacity, np.int64)}  # fmt: skip
        if old is not None:
            for name, arr in fresh.items():
                arr[: self.n] = getattr(self, name)[: self.n]
        for name, arr in fresh.items():
            setattr(self, name, arr)

    def room(self, more: int) -> None:
        if self.n + more > self.px.size:
            self._arrays(max(2 * self.px.size, self.n + more))

    def xy(self) -> np.ndarray:
        return np.column_stack((self.px[: self.n], self.py[: self.n]))


def kept_bins(squares: ActiveSquares | None):
    """The kept squares binned for the kernel, or empty stand-ins."""
    heads = new_bins()
    if squares is None or squares.kept is None or not squares.kept.shape[0]:
        return heads, 1.0, np.zeros(1), np.zeros(1), np.zeros(1, np.int64), np.zeros(1, np.int64), False
    m = squares.kept.shape[0]
    kx, ky, knxt = np.empty(m), np.empty(m), np.empty(m, np.int64)
    size = max(squares.radius, squares.dx)
    for q in range(m):
        _add(heads, size, kx, ky, knxt, q, float(squares.kept[q, 0]), float(squares.kept[q, 1]))
    return heads, size, kx, ky, knxt, np.zeros(m, np.int64), True


__all__ = ["ActiveSquares", "Store", "kept_bins", "rows_of_line"]
