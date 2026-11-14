# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rows across a narrow channel (W52): the pair of cells on a stream cut into narrower 4-sided cells between the walls.

The centre generator puts one cell either side of a stream's line and repeats rows outward to the bank. Where a deep
channel is narrower than that pair, its walls stand inside the pair's own cells, the rows stop there, and the channel
has exactly two cells across at every cell size: refining the grid refines along the flow and never across it (W48).
Published practice asks for more: HEC-RAS 5 to 7 cells across a channel, TUFLOW 3 to 4 with sub-grid sampling and 6 to
8 without, ARR Project 15 at least 5, SEPA 3 to 4.

Here, after the mesh is made: along each stream's chain of faces, at every vertex of the line, the ground is read on
the DEM's own pixels along the two faces that leave the line (one per side, the faces between consecutive cells of
the pair); the wall on a side is where the ground first stands ``wall_m`` above the lowest pixel of both. Where both
sides have a wall inside the pair's cell along at least ``HOLD`` vertices running, the reach is a gorge: each pair
cell of the reach is cut along the flow into rows of equal width between the line and the wall, half of ``rows`` each
side at most and never narrower than ``cell_min_m``, and what is left of the pair's cell beyond the wall is one cell
more. The cuts add nodes on the faces across the channel and faces along it, nothing else: the line stays a chain
of faces, every new cell has four sides, the outer faces of the pair's cells and everything beyond them are as they
were, so the join to the squares and the area the strip covers do not change. Where a reach begins and ends, the
uncut cell next to it carries the cut face's nodes on its own ring, as a quadtree's coarse cell does.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.mesher import StripMesh

SHARE_MAX = 0.8
"""The rows take at most this share of the face they are cut on, so the cell beyond the wall keeps a fifth of it."""
SMOOTH_WINDOW = 5
"""The wall's distance is the running median over this many vertices of a reach: one boulder is not a wall."""
HOLD = 3
"""A gorge reach is at least this many vertices running, as a change of row count must last three stations."""
SUSTAIN = 2
"""The ground must stand above the wall height on this many samples running to be the wall."""
NARROW_PERCENTILE = 10.0
"""A reach's row count is set at this percentile of its wall distances, so one narrow station does not thin it all."""
BLOCK_POINTS = 8192
"""Points per window read of the DEM sampler."""
WINDOW_PIXELS_MAX = 64_000_000
"""A window read is at most this many pixels; a block of points spread wider is halved."""


@dataclass(frozen=True)
class GorgeRule:
    """The numbers of the gorge rows: rows across the bed (even), the wall's height over the bed, the narrowest
    row, the spacing the ground is sampled at along a face, all in metres."""

    rows: int
    wall_m: float
    cell_min_m: float
    pixel: float


class DemSampler:
    """The DEM's own pixels at points, nearest pixel, NaN off the raster or on nodata; read by windows around runs
    of points, so only the ground near the lines is touched."""

    def __init__(self, path: str | Path) -> None:
        import rasterio

        self.src = rasterio.open(path)
        t = self.src.transform
        self.pixel = float(t.a)
        self.left, self.top = float(t.c), float(t.f)

    def close(self) -> None:
        self.src.close()

    def __enter__(self) -> DemSampler:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __call__(self, xy: np.ndarray) -> np.ndarray:
        xy = np.asarray(xy, np.float64).reshape(-1, 2)
        out = np.full(xy.shape[0], np.nan)
        col = np.floor((xy[:, 0] - self.left) / self.pixel).astype(np.int64)
        row = np.floor((self.top - xy[:, 1]) / self.pixel).astype(np.int64)
        inside = (col >= 0) & (col < self.src.width) & (row >= 0) & (row < self.src.height)
        todo = [(a, min(a + BLOCK_POINTS, xy.shape[0])) for a in range(0, xy.shape[0], BLOCK_POINTS)]
        while todo:
            a, b = todo.pop()
            keep = np.nonzero(inside[a:b])[0] + a
            if keep.size == 0:
                continue
            r0, r1, c0, c1 = int(row[keep].min()), int(row[keep].max()), int(col[keep].min()), int(col[keep].max())
            if (r1 - r0 + 1) * (c1 - c0 + 1) > WINDOW_PIXELS_MAX and b - a > 1:
                mid = (a + b) // 2
                todo += [(a, mid), (mid, b)]
                continue
            from rasterio.windows import Window

            z = self.src.read(1, window=Window(c0, r0, c1 - c0 + 1, r1 - r0 + 1), masked=True)
            values = np.asarray(z.filled(np.nan), np.float64)
            values[~np.isfinite(values) | (values > 1e30)] = np.nan
            out[keep] = values[row[keep] - r0, col[keep] - c0]
        return out


def _paths(edges: set[tuple[int, int]]) -> list[list[int]]:
    """The chains of nodes a line's faces make, each from one end to the other; a line cut by a higher line or the
    domain's edge gives several."""
    around: dict[int, list[int]] = {}
    for a, b in edges:
        around.setdefault(a, []).append(b)
        around.setdefault(b, []).append(a)
    seen: set[int] = set()
    out = []
    for start in sorted(v for v, nb in around.items() if len(nb) == 1):
        if start in seen:
            continue
        path, prev, at = [start], -1, start
        seen.add(start)
        while True:
            ahead = [v for v in around[at] if v != prev and v not in seen]
            if len(ahead) != 1:
                break
            prev, at = at, ahead[0]
            path.append(at)
            seen.add(at)
        out.append(path)
    return out


def _running_median(values: np.ndarray, window: int) -> np.ndarray:
    half = window // 2
    return np.array([np.median(values[max(0, i - half) : i + half + 1]) for i in range(values.size)])


def _first_wall(z: np.ndarray, bed: float, wall_m: float) -> int:
    """The first sample of a run of SUSTAIN samples standing wall_m above the bed (a shorter run at the line's far
    end counts), -1 where none."""
    high = (z - bed) >= wall_m
    n = high.size
    for i in range(n):
        if high[i] and high[i : i + SUSTAIN].all():
            return i
    return -1


def split_gorge_rows(mesh: StripMesh, ground: Callable[[np.ndarray], np.ndarray], rule: GorgeRule) -> StripMesh:
    """The mesh with the pair cells of every gorge reach cut into rows: see the module's words. ``ground`` gives the
    DEM at points (n, 2). A mesh with no gorge comes back as it was, with ``gorge`` all zero."""
    geo = mesh.geometry
    ncells = geo.ncells
    rings = [np.asarray(geo.ring(c), np.int64) for c in range(ncells)]
    x, y = geo.x, geo.y
    hard = {r["name"] for r in mesh.rules if r.get("hard")}
    per_side = max(1, rule.rows // 2)
    pair = (np.asarray(mesh.row) == 0) & (np.asarray(mesh.corridor) >= 0)
    notes = list(mesh.notes)
    gorge = np.zeros(ncells, np.int64)
    line_edges: set[tuple[int, int]] = set()
    for edges in mesh.breakline_edges.values():
        line_edges |= set(edges)

    # every pair cell with one face on a line: the face's two nodes and the nodes its ring reaches next either way,
    # which are the far ends of the two faces across the channel (the spokes of the line's vertices)
    spokes: dict[int, dict[int, list[int]]] = {}  # line node -> far node -> the pair cells on that spoke
    cell_face: dict[int, tuple[int, int, int, int]] = {}
    for c in np.nonzero(pair)[0].tolist():
        r = rings[c]
        n = r.size
        on = [k for k in range(n) if (min(int(r[k]), int(r[(k + 1) % n])), max(int(r[k]), int(r[(k + 1) % n]))) in line_edges]
        if len(on) != 1 or n < 4:
            continue
        k = on[0]
        a, b, o_a, o_b = int(r[k]), int(r[(k + 1) % n]), int(r[(k - 1) % n]), int(r[(k + 2) % n])
        if o_a == o_b:
            continue
        cell_face[c] = (a, b, o_a, o_b)
        spokes.setdefault(a, {}).setdefault(o_a, []).append(c)
        spokes.setdefault(b, {}).setdefault(o_b, []).append(c)

    # the vertices that can be cut: two spokes, one each side, each between two whole pair cells
    cut: dict[tuple[int, int], list[int]] = {}  # (line node, far node) -> the new nodes out from the line
    new_xy: list[tuple[float, float]] = []
    nnodes = x.size
    reaches = 0
    for name, edges in mesh.breakline_edges.items():
        if name.rsplit(":", 1)[0] in hard:
            continue
        cut_here = 0
        widths: list[float] = []
        for path in _paths(set(edges)):
            if len(path) < HOLD + 2:
                continue
            m = len(path)
            ok = np.zeros(m, bool)
            far = np.full((m, 2), -1, np.int64)  # left, right
            for i in range(1, m - 1):
                v = path[i]
                sp = spokes.get(v, {})
                if len(sp) != 2 or any(len(cells) != 2 for cells in sp.values()):
                    continue
                tx, ty = x[path[i + 1]] - x[path[i - 1]], y[path[i + 1]] - y[path[i - 1]]
                sides = {}
                for o in sp:
                    sides[tx * (y[o] - y[v]) - ty * (x[o] - x[v]) > 0.0] = o
                if len(sides) != 2:
                    continue
                far[i] = (sides[True], sides[False])
                ok[i] = True
            if not ok.any():
                continue
            # the ground along both spokes of every vertex, one read
            pts, slices, lengths = [], {}, np.zeros((m, 2))
            at = 0
            for i in np.nonzero(ok)[0]:
                v = path[i]
                for s in (0, 1):
                    o = far[i, s]
                    length = float(np.hypot(x[o] - x[v], y[o] - y[v]))
                    count = max(int(np.ceil(length / rule.pixel - 1e-9)), 1)
                    t = (np.arange(count) + 0.5) / count
                    pts.append(np.column_stack((x[v] + (x[o] - x[v]) * t, y[v] + (y[o] - y[v]) * t)))
                    slices[(i, s)] = (at, at + count)
                    lengths[i, s] = length
                    at += count
            z = np.asarray(ground(np.vstack(pts)), np.float64)
            wall = np.full((m, 2), np.nan)
            for i in np.nonzero(ok)[0]:
                za, zb = z[slice(*slices[(i, 0)])], z[slice(*slices[(i, 1)])]
                if not (np.isfinite(za).any() and np.isfinite(zb).any()):
                    continue
                bed = min(np.nanmin(za), np.nanmin(zb))
                for s, zs in ((0, za), (1, zb)):
                    k = _first_wall(np.where(np.isfinite(zs), zs, -np.inf), bed, rule.wall_m)
                    if k > 0:
                        wall[i, s] = k * lengths[i, s] / zs.size
            is_gorge = ok & np.isfinite(wall).all(axis=1) & (wall >= rule.cell_min_m).all(axis=1)
            # reaches of at least HOLD vertices running
            i = 0
            while i < m:
                if not is_gorge[i]:
                    i += 1
                    continue
                j = i
                while j < m and is_gorge[j]:
                    j += 1
                if j - i >= HOLD:
                    reaches += 1
                    for s in (0, 1):
                        w = np.minimum(_running_median(wall[i:j, s], SMOOTH_WINDOW), SHARE_MAX * lengths[i:j, s])
                        # the count from the reach's narrow end (its tenth percentile, not one vertex), and where the
                        # bed is narrower still the cut moves up the wall so no row is under the floor
                        n_rows = int(max(1, min(per_side, np.floor(np.percentile(w, NARROW_PERCENTILE) / rule.cell_min_m + 1e-9))))
                        w = np.minimum(np.maximum(w, n_rows * rule.cell_min_m), SHARE_MAX * lengths[i:j, s])
                        widths.append(float(np.median(w)) / n_rows)
                        for q in range(i, j):
                            v, o = path[q], int(far[q, s])
                            share = w[q - i] / lengths[q, s]
                            ids = []
                            for k in range(1, n_rows + 1):
                                f = share * k / n_rows
                                new_xy.append((x[v] + (x[o] - x[v]) * f, y[v] + (y[o] - y[v]) * f))
                                ids.append(nnodes + len(new_xy) - 1)
                            cut[(v, o)] = ids
                    cut_here += j - i
                i = j
        if cut_here:
            rule_of = next((r for r in mesh.rules if r.get("name") == name.rsplit(":", 1)[0]), None)
            if rule_of is not None:
                rule_of["gorge_vertices"] = cut_here
                rule_of["gorge_row_m"] = round(float(np.median(widths)), 2)
    if not cut:
        return StripMesh(mesh.geometry, mesh.masked, mesh.corridor, mesh.row, mesh.breakline_edges, mesh.polygons, notes, mesh.rules, gorge)

    # the rings: every face that was cut carries its new nodes; a pair cell cut at both ends becomes its rows and
    # the cell beyond the wall, one cut at one end only keeps its ring with the new nodes on it
    cut_nodes = {v for v, _o in cut}

    def with_nodes(r: np.ndarray) -> np.ndarray:
        out: list[int] = []
        n = r.size
        for k in range(n):
            p, q = int(r[k]), int(r[(k + 1) % n])
            out.append(p)
            ids = cut.get((p, q))
            if ids is not None:
                out.extend(ids)
            else:
                ids = cut.get((q, p))
                if ids is not None:
                    out.extend(reversed(ids))
        return np.asarray(out, np.int64)

    new_rings: list[np.ndarray] = []
    new_corridor: list[int] = []
    new_gorge: list[int] = []
    for c in range(ncells):
        r = rings[c]
        if not any(int(v) in cut_nodes for v in r):
            continue
        face = cell_face.get(c)
        ids_a = cut.get((face[0], face[2])) if face else None
        ids_b = cut.get((face[1], face[3])) if face else None
        if ids_a is None or ids_b is None or len(ids_a) != len(ids_b):
            rings[c] = with_nodes(r)
            continue
        a, b, _o_a, _o_b = face
        inner_a, inner_b = [a, *ids_a], [b, *ids_b]
        n_rows = len(ids_a)
        for k in range(n_rows):
            quad = np.array([inner_a[k], inner_b[k], inner_b[k + 1], inner_a[k + 1]], np.int64)
            if k == 0:
                rings[c] = quad  # the cell on the line keeps its index
                gorge[c] = 1
            else:
                new_rings.append(quad)
                new_corridor.append(int(mesh.corridor[c]))
                new_gorge.append(k + 1)
        # beyond the wall: the pair cell's ring with its two line nodes moved out to the last cut
        rest = with_nodes(np.array([ids_a[-1] if int(v) == a else (ids_b[-1] if int(v) == b else int(v)) for v in r], np.int64))
        new_rings.append(rest)
        new_corridor.append(int(mesh.corridor[c]))
        new_gorge.append(-1)
    all_x = np.concatenate((x, np.array([p[0] for p in new_xy])))
    all_y = np.concatenate((y, np.array([p[1] for p in new_xy])))
    before = float(geo.areas_centroids()[0].sum())
    out_geo = MeshGeometry.from_rings(all_x, all_y, rings + new_rings)
    areas = out_geo.areas_centroids()[0]
    if (areas <= 0.0).any() or abs(float(areas.sum()) - before) > 1e-6 * max(before, 1.0):
        raise ValueError(
            f"the gorge rows changed the strip's cells from {before:.1f} to {float(areas.sum()):.1f} m2,"
            f" {int((areas <= 0.0).sum())} of them empty or turned over: the cut is wrong"
        )
    extra = len(new_rings)
    narrow = int((gorge == 1).sum()) + sum(1 for k in new_gorge if k > 0)
    notes.append(f"gorge rows: {reaches} reaches, {narrow} cells in rows between the walls and {sum(1 for k in new_gorge if k < 0)} beyond them, {extra} cells more than the pair gave")
    return StripMesh(
        out_geo, mesh.masked, np.concatenate((mesh.corridor, np.asarray(new_corridor, np.int64))),
        np.concatenate((mesh.row, np.zeros(extra, np.int64))), mesh.breakline_edges, mesh.polygons, notes, mesh.rules,
        np.concatenate((gorge, np.asarray(new_gorge, np.int64))),
    )  # fmt: skip


__all__ = ["HOLD", "SHARE_MAX", "DemSampler", "GorgeRule", "split_gorge_rows"]
