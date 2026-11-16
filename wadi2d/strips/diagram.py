# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ring work of the centre generator's Voronoi diagram, on whole arrays (W92).

``centres._rings_of``, ``_areas_centroids`` and ``_contract_short_faces`` walked the rings one at a time in Python:
on Block 2's mesh (about 700,000 rings, five diagrams) 230 s of its 615. The same arithmetic runs here on all the
rings of one length at once (numpy's sum of a row is its sum of that row as a 1-D array, so every area, centroid and
orientation is the one the loop gave, to the bit), and the merge of short faces, whose every step depends on the one
before, runs in the same order compiled. The rings come out as before: a list of int64 arrays.
"""

from __future__ import annotations

from itertools import chain

import numpy as np
from numba import njit


def flatten(rings: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """The rings as one int64 array and their offsets (n + 1)."""
    lengths = np.fromiter(map(len, rings), np.int64, len(rings))
    start = np.zeros(len(rings) + 1, np.int64)
    np.cumsum(lengths, out=start[1:])
    flat = np.concatenate(rings).astype(np.int64, copy=False) if rings else np.zeros(0, np.int64)
    return flat, start


def split(flat: np.ndarray, start: np.ndarray) -> list[np.ndarray]:
    """The rings as views of ``flat`` (np.split is ten times slower on 700,000 rings)."""
    bounds = start.tolist()
    return [flat[a:b] for a, b in zip(bounds[:-1], bounds[1:], strict=True)]


def _by_length(start: np.ndarray, at_least: int = 1):
    """Per ring length L (at least ``at_least``): the rings of that length and the (m, L) positions of their nodes."""
    lengths = np.diff(start)
    for length in np.unique(lengths):
        if length < at_least:
            continue
        which = np.nonzero(lengths == length)[0]
        yield int(length), which, start[which][:, None] + np.arange(length)[None, :]


def _shoelace(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Twice the signed area of every row, as ``np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)`` of each row."""
    return np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1)


def regions_to_rings(vor, nreal: int, inverse: np.ndarray, nodes: np.ndarray, points: np.ndarray) -> list[np.ndarray]:
    """One counter-clockwise ring of node indices per real point: its Voronoi region mapped to the merged nodes, a
    node repeated in a row once, the closing repeat dropped. A region open to infinity is refused, the first one."""
    regions = [vor.regions[r] for r in vor.point_region[:nreal].tolist()]
    lengths = np.fromiter(map(len, regions), np.int64, nreal)
    raw = np.fromiter(chain.from_iterable(regions), np.int64, int(lengths.sum()))
    start = np.zeros(nreal + 1, np.int64)
    np.cumsum(lengths, out=start[1:])
    open_ = lengths == 0
    if raw.size:
        neg = np.zeros(nreal, np.int64)
        has = lengths > 0
        neg[has] = np.add.reduceat((raw < 0).astype(np.int64), start[:-1][has])
        open_ |= neg > 0
    if open_.any():
        p = int(np.argmax(open_))
        raise ValueError(f"the diagram is unbounded at ({points[p, 0]:.0f}, {points[p, 1]:.0f}): a line centre too near the edge of the lattice")
    ids = inverse[raw]
    keep = np.ones(ids.size, bool)
    keep[1:] = ids[1:] != ids[:-1]
    keep[start[:-1]] = True  # each ring's first node starts afresh
    ring_of = np.repeat(np.arange(nreal), lengths)
    ids, ring_of = ids[keep], ring_of[keep]
    lengths = np.bincount(ring_of, minlength=nreal).astype(np.int64)
    start = np.zeros(nreal + 1, np.int64)
    np.cumsum(lengths, out=start[1:])
    # the closing repeat: a ring of more than one node whose last is its first
    closing = (lengths > 1) & (ids[start[:-1]] == ids[np.maximum(start[1:] - 1, 0)])
    if closing.any():
        drop = np.zeros(ids.size, bool)
        drop[start[1:][closing] - 1] = True
        ids = ids[~drop]
        lengths = lengths - closing
        start = np.zeros(nreal + 1, np.int64)
        np.cumsum(lengths, out=start[1:])
    for _length, _which, at in _by_length(start, 3):
        rows = ids[at]
        cw = 0.5 * _shoelace(nodes[rows, 0], nodes[rows, 1]) < 0.0
        if cw.any():
            ids[at[cw]] = rows[cw][:, ::-1]
    return split(ids, start)


def shared_faces(vor, nreal: int, inverse: np.ndarray) -> dict[tuple[int, int], tuple[int, int]]:
    """Per pair of real points sharing a finite face of the diagram, the two merged nodes of that face, in the
    diagram's ridge order (a dict, as the loop built it)."""
    rp = np.asarray(vor.ridge_points, np.int64)
    rv = np.asarray(vor.ridge_vertices, np.int64).reshape(-1, 2)
    a, b = rp[:, 0], rp[:, 1]
    ok = (a < nreal) & (b < nreal) & (rv[:, 0] >= 0) & (rv[:, 1] >= 0)
    a, b, va, vb = a[ok], b[ok], rv[ok, 0], rv[ok, 1]
    na, nb = inverse[va], inverse[vb]
    ok = na != nb
    a, b, na, nb = a[ok], b[ok], na[ok], nb[ok]
    keys = zip(np.minimum(a, b).tolist(), np.maximum(a, b).tolist(), strict=True)
    values = zip(np.minimum(na, nb).tolist(), np.maximum(na, nb).tolist(), strict=True)
    return dict(zip(keys, values, strict=True))


def areas_centroids(nodes: np.ndarray, rings: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """``centres._areas_centroids``: the signed area and centroid of every ring from its first node, row by row."""
    n = len(rings)
    area = np.zeros(n)
    cen = np.zeros((n, 2))
    if n == 0:
        return area, cen
    flat, start = flatten(rings)
    for _length, which, at in _by_length(start, 3):
        rows = flat[at]
        ox, oy = nodes[rows[:, 0], 0], nodes[rows[:, 0], 1]
        x, y = nodes[rows, 0] - ox[:, None], nodes[rows, 1] - oy[:, None]
        x1, y1 = np.roll(x, -1, axis=1), np.roll(y, -1, axis=1)
        cross = x * y1 - x1 * y
        a = 0.5 * cross.sum(axis=1)
        area[which] = a
        big = np.abs(a) > 1e-12
        cx = np.where(big, ox + ((x + x1) * cross).sum(axis=1) / np.where(big, 6.0 * a, 1.0), ox + x.mean(axis=1))
        cy = np.where(big, oy + ((y + y1) * cross).sum(axis=1) / np.where(big, 6.0 * a, 1.0), oy + y.mean(axis=1))
        cen[which, 0], cen[which, 1] = cx, cy
    return area, cen


@njit(cache=True)
def _find(parent, a):
    while parent[a] != a:
        parent[a] = parent[parent[a]]
        a = parent[a]
    return a


@njit(cache=True)
def _contract(nodes, flat, start, corner, limit, rounds):
    """The loop of ``centres._contract_short_faces``, in its order: returns the nodes and the re-threaded rings."""
    nn = nodes.shape[0]
    parent = np.arange(nn)
    nrings = start.size - 1
    for _round in range(rounds):
        merged = 0
        seen = {np.int64(0)}
        seen.clear()
        for c in range(nrings):
            s0, s1 = start[c], start[c + 1]
            size = s1 - s0
            for k in range(size):
                a = _find(parent, flat[s0 + k])
                b = _find(parent, flat[s0 + (k + 1) % size])
                if a == b:
                    continue
                lo, hi = (a, b) if a < b else (b, a)
                key = np.int64(lo) * nn + hi
                if key in seen:
                    continue
                seen.add(key)
                if np.hypot(nodes[a, 0] - nodes[b, 0], nodes[a, 1] - nodes[b, 1]) < limit:
                    if corner[a] and corner[b]:
                        continue
                    if corner[a]:
                        keep, gone = a, b
                    elif corner[b]:
                        keep, gone = b, a
                    else:
                        keep, gone = a, b
                    if not corner[keep]:
                        x = 0.5 * (nodes[a, 0] + nodes[b, 0])
                        y = 0.5 * (nodes[a, 1] + nodes[b, 1])
                        nodes[keep, 0] = x
                        nodes[keep, 1] = y
                    parent[gone] = keep
                    merged += 1
        if merged == 0:
            break
        out = np.empty(flat.size, np.int64)
        new_start = np.zeros(nrings + 1, np.int64)
        m = 0
        for c in range(nrings):
            s0, s1 = start[c], start[c + 1]
            first = m
            for k in range(s0, s1):
                v = _find(parent, flat[k])
                if m == first or out[m - 1] != v:
                    out[m] = v
                    m += 1
            if m - first > 1 and out[first] == out[m - 1]:
                m -= 1
            new_start[c + 1] = m
        flat = out[:m].copy()
        start = new_start
    return nodes, flat, start


def contract_short_faces(nodes: np.ndarray, rings: list[np.ndarray], corner: np.ndarray, limit: float, rounds: int = 6) -> tuple[np.ndarray, list[np.ndarray]]:
    """``centres._contract_short_faces``'s merge, given the nodes at lattice corners: (nodes, rings)."""
    flat, start = flatten(rings)
    out_nodes, flat, start = _contract(np.array(nodes, np.float64), flat, start, np.asarray(corner, np.bool_), float(limit), rounds)
    return out_nodes, split(flat, start)


__all__ = ["areas_centroids", "contract_short_faces", "flatten", "regions_to_rings", "shared_faces", "split"]
