# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A strip pixel's Wachspress weights in one compiled loop, the same numbers as NumPy's (W93).

:func:`wadi2d.strips.pixels._wachspress` takes the weights as a dozen NumPy array operations over a run of pixels,
each a temporary of the run's size: on Block 2's 2D run about 12 s of host work a block of the pixel maps, more
than the card's work on the block once the card's sums were mended. Here each pixel is one pass, on every core,
operation for operation in float64 as NumPy takes them, the row's sum as NumPy's pairwise sum adds a row of up to
eight values, then rounded to float32 as the weights are stored. ``strips/pixels.py`` is not edited: every file of
``strips/`` is hashed into the strip cache key (W86).
"""

from __future__ import annotations

import numpy as np
from numba import njit, prange

from wadi2d.strips.pixels import AREA_EPS

ROW_SUM_SEQUENTIAL = 8
"""NumPy adds a row of fewer values one after another, and eight at a time from here."""


@njit(cache=True, nogil=True, inline="always")
def _area(ax, ay, bx, by, cx, cy):
    return 0.5 * ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))


@njit(cache=True, nogil=True, inline="always")
def _row_sum(w, m):
    """``w[:m].sum()`` as NumPy's pairwise sum adds a row: in turn from zero below eight values, else eight partial
    sums joined in pairs and the rest in turn."""
    if m < ROW_SUM_SEQUENTIAL:
        res = 0.0
        for k in range(m):
            res += w[k]
        return res
    r0, r1, r2, r3 = w[0], w[1], w[2], w[3]
    r4, r5, r6, r7 = w[4], w[5], w[6], w[7]
    k = 8
    while k < m - m % 8:
        r0 += w[k]
        r1 += w[k + 1]
        r2 += w[k + 2]
        r3 += w[k + 3]
        r4 += w[k + 4]
        r5 += w[k + 5]
        r6 += w[k + 6]
        r7 += w[k + 7]
        k += 8
    res = ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7))
    while k < m:
        res += w[k]
        k += 1
    return res


@njit(cache=True, nogil=True, inline="always")
def _one(pxi, pyi, nodes, m, x, y, out, i, vx, vy, corner, w):
    """Pixel ``i``'s weights at (``pxi``, ``pyi``) of the ring ``nodes[:m]`` into ``out[i, :m]``."""
    for k in range(m):
        vx[k] = x[nodes[k]]
        vy[k] = y[nodes[k]]
    top = 0.0
    for k in range(m):
        p = (k - 1) % m
        q = (k + 1) % m
        corner[k] = _area(vx[p], vy[p], vx[k], vy[k], vx[q], vy[q])
        a = abs(corner[k])
        if k == 0 or a > top:
            top = a
    scale = top * AREA_EPS + 1e-12
    for k in range(m):
        p = (k - 1) % m
        q = (k + 1) % m
        left = _area(pxi, pyi, vx[p], vy[p], vx[k], vy[k])
        right = _area(pxi, pyi, vx[k], vy[k], vx[q], vy[q])
        w[k] = corner[k] / (max(left, scale) * max(right, scale))
    total = _row_sum(w, m)
    for k in range(m):
        out[i, k] = np.float32(w[k] / total)


CHUNK = 4096
"""Pixels a thread takes at once, with one set of scratch arrays."""


@njit(cache=True, nogil=True, parallel=True)
def wachspress_into(px, py, nodes, length, x, y, out):
    """``out[i, :length[i]]`` the weights at pixel ``i`` (``px``, ``py``) of the ring ``nodes[i, :length[i]]`` of
    node coordinates ``x``, ``y``; the slots past a ring's length are left as they are."""
    width, n = nodes.shape[1], px.size
    for b in prange((n + CHUNK - 1) // CHUNK):
        vx, vy, corner, w = np.empty(width), np.empty(width), np.empty(width), np.empty(width)
        for i in range(b * CHUNK, min((b + 1) * CHUNK, n)):
            _one(px[i], py[i], nodes[i], length[i], x, y, out, i, vx, vy, corner, w)


@njit(cache=True, nogil=True, parallel=True)
def pixel_weights(r, c, cell, cell_node, length, x0, y0, pixel, x, y, out):
    """:func:`wachspress_into` for the pixels at rows ``r`` and columns ``c`` of a window from (``x0``, ``y0``), each
    of its cell's ring (``cell_node[cell]``, ``length[cell]`` nodes), the pixel's centre taken as the NumPy steps take
    it: ``x0 + (c + 0.5) * pixel``."""
    width, n = cell_node.shape[1], r.size
    for b in prange((n + CHUNK - 1) // CHUNK):
        vx, vy, corner, w = np.empty(width), np.empty(width), np.empty(width), np.empty(width)
        for i in range(b * CHUNK, min((b + 1) * CHUNK, n)):
            pxi = x0 + (c[i] + 0.5) * pixel
            pyi = y0 - (r[i] + 0.5) * pixel
            _one(pxi, pyi, cell_node[cell[i]], length[cell[i]], x, y, out, i, vx, vy, corner, w)


__all__ = ["pixel_weights", "wachspress_into"]
