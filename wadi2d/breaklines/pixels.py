"""Lines out of pixels: thinning a mask to one pixel, walking a pixel graph into polylines, then smoothing.

No image library beyond NumPy and SciPy: the thinning is Zhang and Suen's, vectorised, and the walk is a plain
graph walk over 8-connected pixels. Objects here are at most a few pixels wide, so the thinning takes a few passes.
"""

from __future__ import annotations

import numpy as np
import shapely

NEIGHBOURS = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))
"""P2 to P9 of Zhang-Suen, clockwise from north."""
EIGHT = np.ones((3, 3), np.int32)


def _shifted(a: np.ndarray, dj: int, di: int) -> np.ndarray:
    """``a`` moved so that out[j, i] = a[j + dj, i + di], zero beyond the edge."""
    out = np.zeros_like(a)
    ny, nx = a.shape
    src_j = slice(max(dj, 0), ny + min(dj, 0))
    src_i = slice(max(di, 0), nx + min(di, 0))
    dst_j = slice(max(-dj, 0), ny + min(-dj, 0))
    dst_i = slice(max(-di, 0), nx + min(-di, 0))
    out[dst_j, dst_i] = a[src_j, src_i]
    return out


def thin(mask: np.ndarray) -> np.ndarray:
    """One-pixel-wide skeleton of a boolean mask, 8-connected, by Zhang-Suen thinning."""
    a = mask.astype(np.uint8)
    while True:
        changed = False
        for pass_two in (False, True):
            p = [_shifted(a, dj, di) for dj, di in NEIGHBOURS]
            count = sum(p)
            ring = np.stack([*p, p[0]])
            transitions = ((ring[:-1] == 0) & (ring[1:] == 1)).sum(axis=0)
            if pass_two:
                first, second = p[0] * p[2] * p[6], p[0] * p[4] * p[6]
            else:
                first, second = p[0] * p[2] * p[4], p[2] * p[4] * p[6]
            remove = (
                (a == 1) & (count >= 2) & (count <= 6) & (transitions == 1) & (first == 0) & (second == 0)
            )
            if remove.any():
                a[remove] = 0
                changed = True
        if not changed:
            return a.astype(bool)


def branches(skeleton: np.ndarray) -> np.ndarray:
    """Branches leaving each skeleton pixel: runs of set pixels around its 8-ring; 0 elsewhere.

    A corner pixel of a staircase has three neighbours but two branches, because two of them touch each other.
    """
    p = [_shifted(skeleton.astype(np.uint8), dj, di) for dj, di in NEIGHBOURS]
    ring = np.stack([*p, p[0]])
    runs = ((ring[:-1] == 0) & (ring[1:] == 1)).sum(axis=0)
    alone = (ring[:-1] == 1).all(axis=0)
    return np.where(skeleton, np.where(alone, 1, runs), 0)


def _runs(p: tuple[int, int], on: set) -> list[list[tuple[int, int]]]:
    """The branches at ``p``: neighbours on the skeleton grouped into runs around the ring, orthogonal first."""
    ring = [(p[0] + dj, p[1] + di) for dj, di in NEIGHBOURS]
    flags = [q in on for q in ring]
    if all(flags):
        return [[q for k, q in enumerate(ring) if k % 2 == 0] + [q for k, q in enumerate(ring) if k % 2 == 1]]
    start = flags.index(False)
    runs: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    for step in range(1, 9):
        k = (start + step) % 8
        if flags[k]:
            current.append(ring[k]) if k % 2 else current.insert(0, ring[k])
        elif current:
            runs.append(current)
            current = []
    return runs


def walk(skeleton: np.ndarray) -> list[np.ndarray]:
    """Polylines of (row, col) between the nodes of a skeleton; a node is a pixel with other than two branches.

    The walk steps by branch, taking the orthogonal pixel of a run before its diagonal, so a staircase is one
    line. Loops with no node are walked from any of their pixels.
    """
    count = branches(skeleton)
    on = {(int(j), int(i)) for j, i in zip(*np.nonzero(skeleton), strict=True)}
    nodes = {p for p in on if count[p] != 2}
    used: set[tuple[int, int]] = set()
    lines: list[np.ndarray] = []

    def follow(start, run):
        path = [start]
        prev, here = start, run[0]
        while True:
            if here not in nodes:
                if here in used and here != start:
                    break
                used.add(here)
            path.append(here)
            if here in nodes or here == start:
                break
            onward = [r for r in _runs(here, on) if prev not in r]
            if not onward:
                break
            prev, here = here, onward[0][0]
        return np.array(path, np.int64)

    for node in sorted(nodes):
        for run in _runs(node, on):
            first = run[0]
            if first in nodes:
                if first > node:
                    lines.append(np.array([node, first], np.int64))
            elif first not in used:
                lines.append(follow(node, run))
    for p in sorted(on - nodes):
        if p not in used:
            runs = _runs(p, on)
            if runs:
                lines.append(follow(p, runs[0]))
    return [ln for ln in lines if len(ln) >= 2]


def smooth(xy: np.ndarray, vertices: int) -> np.ndarray:
    """Moving average over ``vertices`` points, the ends kept where they are."""
    if len(xy) < 3 or vertices < 2:
        return xy
    half = vertices // 2
    pad = np.concatenate((np.repeat(xy[:1], half, axis=0), xy, np.repeat(xy[-1:], half, axis=0)))
    kernel = np.ones(2 * half + 1) / (2 * half + 1)
    out = np.column_stack([np.convolve(pad[:, k], kernel, mode="valid") for k in range(xy.shape[1])])
    out[0], out[-1] = xy[0], xy[-1]
    return out


def simplify(xy: np.ndarray, tolerance: float) -> np.ndarray:
    """Douglas-Peucker on the plan view; the line keeps its two ends."""
    if len(xy) < 3:
        return xy
    line = shapely.LineString(xy[:, :2]).simplify(tolerance, preserve_topology=False)
    return np.asarray(line.coords, np.float64)


def length_of(xy: np.ndarray) -> float:
    return float(np.hypot(*np.diff(np.asarray(xy, np.float64)[:, :2], axis=0).T).sum())


def straightness(xy: np.ndarray) -> float:
    """Chord over length; 1 for a straight line."""
    length = length_of(xy)
    return float(np.hypot(*(xy[-1, :2] - xy[0, :2])) / length) if length > 0.0 else 1.0
