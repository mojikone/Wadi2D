# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Strips of cells aligned with breaklines, built in the engine from the lines themselves (W45, stage 4).

A corridor is a curvilinear grid: stations every ``along`` metres on a smoothed centre line, rows at fixed offsets
along the station normals, and the rows that carry a breakline snapped onto it along their own cross lines, the outer
rows carried with them, so the breakline's faces lie on the line to the last digit (the step of the W44 trial that
MeshKernel could not do; the rest of its recipe is kept). The lattice cells under a corridor, and those within a
buffer of it, are removed; the gap between the staircase hole and the corridor is triangulated on the existing
nodes alone (shapely's constrained Delaunay), so every gap face shares its edge with a lattice cell, a corridor cell
or another triangle, nothing hangs, and every interface face is a lattice edge. A corridor that folds at a bend is
refused by name, with the stations that fold.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.spatial import cKDTree

from wadi2d.grid.tiles import TileGrid
from wadi2d.strips.geometry import MeshGeometry

SNAP_REACH = 2.5
"""A snapped row looks for its line this many rows out along the cross line, else takes the nearest point."""
NODE_TOLERANCE = 1e-3
MERGE_DN = 0.5
"""Two gap triangles whose centres stand closer than this share of the lattice cell along their shared face are joined
into one quad when it is convex: a sliver sets the time step for the whole model (W45, speed)."""
"""Two nodes closer than this, m, are one node."""
MIN_FACING_M = 120.0
"""Two banks farther apart than this do not face each other (W44's midline rule)."""


@dataclass
class Corridor:
    """One strip: its centre line, the row offsets across it (sorted, metres, negative to the left of the line's
    direction), the rows snapped to a breakline, and the station spacing along."""

    name: str
    centre: shapely.LineString
    offsets: np.ndarray
    along: float
    snap: dict[int, shapely.LineString] = field(default_factory=dict)
    """Row index (into ``offsets``) to the line that row lies on."""

    @property
    def rows(self) -> int:
        return int(self.offsets.size - 1)


@dataclass
class StripMesh:
    """What the mesher makes: the polygon mesh of all corridors and gap triangles, the lattice cells it replaces,
    and what each cell is."""

    geometry: MeshGeometry
    masked: tuple[np.ndarray, np.ndarray]
    """(j, i) of the lattice cells removed, on the grid the corridors were built on."""
    corridor: np.ndarray
    """Per cell the corridor index, -1 for a gap triangle."""
    row: np.ndarray
    """Per cell the row across its corridor, -1 for a triangle."""
    breakline_edges: dict[str, set[tuple[int, int]]]
    """Per snapped line (``corridor.name:row``) the node pairs of the faces lying on it."""
    polygons: list[shapely.Polygon]
    notes: list[str] = field(default_factory=list)
    """What the corridor builder cut or dropped, in words, when the corridors came from a banks file."""


def resample(line: shapely.LineString, step: float, smooth: int = 0) -> np.ndarray:
    """Points every ``step`` along a line, after a running mean over ``smooth`` points of a 10 m sampling."""
    if smooth > 1:
        stations = np.linspace(0.0, line.length, max(round(line.length / 10.0), 1) + 1)  # the end included
        fine = np.array([line.interpolate(s).coords[0] for s in stations])
        out = fine.copy()
        for i in range(1, len(fine) - 1):  # the ends stay: a mean there would pull the line inward
            a, b = max(0, i - smooth // 2), min(len(fine), i + smooth // 2 + 1)
            out[i] = fine[a:b].mean(axis=0)
        line = shapely.LineString(out)
    n = max(round(line.length / step), 1)
    return np.array([line.interpolate(t, normalized=True).coords[0] for t in np.linspace(0.0, 1.0, n + 1)])


def midline(left: shapely.LineString, right: shapely.LineString, step: float = 10.0) -> shapely.LineString | None:
    """The line midway between two facing banks over the stretch where they face each other (W44)."""
    pts = []
    for s in np.arange(step, left.length - step, step):
        p = left.interpolate(s)
        sr = right.project(p)
        if sr <= step or sr >= right.length - step:
            continue
        q = right.interpolate(sr)
        if p.distance(q) > MIN_FACING_M:
            continue
        pts.append([(p.x + q.x) / 2, (p.y + q.y) / 2])
    return shapely.LineString(pts) if len(pts) >= 5 else None


def corridor_nodes(c: Corridor, smooth: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """(stations, rows + 1) node coordinates: the centre resampled, rows along the station normals, snapped rows on
    their lines with the outer rows carried."""
    centre = resample(c.centre, c.along, smooth)
    n = centre.shape[0]
    ahead = centre[np.minimum(np.arange(n) + 1, n - 1)]
    behind = centre[np.maximum(np.arange(n) - 1, 0)]
    tangent = ahead - behind
    tangent /= np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-9)[:, None]
    normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))  # to the left of the direction of travel
    off = np.asarray(c.offsets, np.float64)
    x = centre[:, 0][:, None] + off[None, :] * normal[:, 0][:, None]
    y = centre[:, 1][:, None] + off[None, :] * normal[:, 1][:, None]
    middle = int(np.argmin(np.abs(off)))
    for j, line in sorted(c.snap.items(), key=lambda item: abs(item[0] - middle)):
        outward = 1 if off[j] > off[middle] else -1
        carried = range(j, off.size) if outward > 0 else range(j, -1, -1)
        for i in range(n):
            p0 = np.array([x[i, middle], y[i, middle]])
            pb = np.array([x[i, j], y[i, j]])
            d = pb - p0
            dn = np.hypot(*d)
            if dn < 1e-9:
                continue
            u = d / dn
            reach = SNAP_REACH * abs(off[j] - off[middle])
            seg = shapely.LineString([p0 + 0.05 * u, p0 + reach * u])
            hit = seg.intersection(line)
            if hit.is_empty:
                q = np.asarray(line.interpolate(line.project(shapely.Point(pb))).coords[0])
            else:
                pts = shapely.get_coordinates(hit)
                q = pts[np.argmin(np.hypot(*(pts - pb).T))]
            shift = q - pb
            for jj in carried:
                x[i, jj] += shift[0]
                y[i, jj] += shift[1]
    return x, y


def folds(x: np.ndarray, y: np.ndarray) -> list[tuple[int, int]]:
    """The (station, row) cells whose ring is not counter-clockwise or has no area, and the cells on a row whose
    line crosses itself two or more stations apart (a bend tighter than the row's offset: the cells overlap though
    each keeps its area, and the corridor's ring is no longer simple)."""
    out = set()
    ns, nr = x.shape
    for i in range(ns - 1):
        for j in range(nr - 1):
            xq = np.array([x[i, j], x[i + 1, j], x[i + 1, j + 1], x[i, j + 1]])
            yq = np.array([y[i, j], y[i + 1, j], y[i + 1, j + 1], y[i, j + 1]])
            a = 0.5 * np.sum(xq * np.roll(yq, -1) - np.roll(xq, -1) * yq)
            if a <= 1e-6:
                out.add((i, j))
    if ns > 2:
        for j in range(nr):
            pts = np.column_stack((x[:, j], y[:, j]))
            segments = shapely.linestrings(np.stack((pts[:-1], pts[1:]), axis=1))
            a, b = shapely.STRtree(segments).query(segments, predicate="intersects")
            for i, k in zip(a.tolist(), b.tolist(), strict=True):
                if k > i + 1:  # not itself, not its neighbour, which shares a node with it
                    out.update(((i, min(j, nr - 2)), (k, min(j, nr - 2))))
    return sorted(out)


def station_strips(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The polygon between each pair of stations, all rows: shapely polygons, one per station cell row."""
    rings = [
        np.concatenate((np.column_stack((x[i], y[i])), np.column_stack((x[i + 1, ::-1], y[i + 1, ::-1]))))
        for i in range(x.shape[0] - 1)
    ]
    return shapely.polygons([shapely.linearrings(r) for r in rings]) if rings else np.empty(0, object)


def fold_free_pieces(
    c: Corridor, smooth: int = 5, min_stations: int = 3, margin: int = 1, keep_out: shapely.Geometry | None = None
) -> tuple[list[np.ndarray], bool]:
    """The stretches of a corridor's centre line (its resampled middle row) whose cells do not fold and stay off
    ``keep_out`` (the ground beyond the active cells, other corridors), each cut ``margin`` stations clear of a bad
    one and at least ``min_stations`` long: what a corridor builder splits a corridor by, so the mesher's own
    geometry decides, not a copy of it; and whether the corridor is whole (nothing to cut)."""
    x, y = corridor_nodes(c, smooth)
    n = x.shape[0]
    middle = int(np.argmin(np.abs(np.asarray(c.offsets, np.float64))))
    bad = np.zeros(max(n - 1, 0), bool)
    for i, _j in folds(x, y):
        bad[max(0, i - margin) : min(n - 1, i + margin + 1)] = True
    if keep_out is not None and n > 1:
        for i in np.nonzero(shapely.intersects(station_strips(x, y), keep_out))[0]:
            bad[max(0, i - margin) : min(n - 1, i + margin + 1)] = True
    pieces, start = [], None
    for i in range(n - 1):
        if not bad[i]:
            start = i if start is None else start
        elif start is not None:
            pieces.append((start, i))
            start = None
    if start is not None:
        pieces.append((start, n - 1))
    out = [np.column_stack((x[a : b + 1, middle], y[a : b + 1, middle])) for a, b in pieces if b - a >= min_stations]
    return out, not bad.any()


def corridor_polygon(x: np.ndarray, y: np.ndarray) -> shapely.Polygon:
    ring = np.concatenate(
        (
            np.column_stack((x[:, 0], y[:, 0])),
            np.column_stack((x[-1, 1:], y[-1, 1:])),
            np.column_stack((x[::-1, -1], y[::-1, -1]))[1:],
            np.column_stack((x[0, ::-1], y[0, ::-1]))[1:],
        )
    )
    return shapely.make_valid(shapely.Polygon(ring))


def _conform_ring(coords: np.ndarray, tree: cKDTree, xy: np.ndarray) -> np.ndarray:
    """Every mesh node lying on a ring segment inserted into it, so the triangulation shares the mesh's edges."""
    out = []
    for p, q in itertools.pairwise(coords):
        out.append(p)
        seg = q - p
        length = float(np.hypot(*seg))
        if length < 1e-9:
            continue
        cand = tree.query_ball_point((p + q) / 2, r=length / 2 + 0.01)
        if not cand:
            continue
        c = xy[cand]
        t = ((c - p) @ seg) / length**2
        off = np.abs((c[:, 0] - p[0]) * seg[1] - (c[:, 1] - p[1]) * seg[0]) / length
        sel = (off < 1e-4) & (t > 1e-6) & (t < 1 - 1e-6)
        out.extend(c[sel][np.argsort(t[sel])])
    out.append(coords[-1])
    return np.asarray(out)


def build_strip_mesh(
    grid: TileGrid, corridors: list[Corridor], buffer: float | None = None, smooth: int = 5, merge: float = MERGE_DN
) -> StripMesh:
    """The corridors as cells, the lattice cells under them removed, the gap triangulated: one polygon mesh."""
    dx = float(grid.dx)
    buffer = 0.5 * dx if buffer is None else buffer
    xs: list[float] = []
    ys: list[float] = []
    rings: list[np.ndarray] = []
    corridor_of: list[int] = []
    row_of: list[int] = []
    polygons: list[shapely.Polygon] = []
    breakline_edges: dict[str, set[tuple[int, int]]] = {}
    for k, c in enumerate(corridors):
        x, y = corridor_nodes(c, smooth)
        bad = folds(x, y)
        if bad:
            stations = sorted({i for i, _j in bad})[:8]
            raise ValueError(f"corridor {c.name} folds at stations {stations}: a bend too tight for its width")
        base = len(xs)
        ns, nr = x.shape
        xs.extend(x.ravel().tolist())
        ys.extend(y.ravel().tolist())
        for i in range(ns - 1):
            for j in range(nr - 1):
                a, b = base + i * nr + j, base + (i + 1) * nr + j
                rings.append(np.array([a, b, b + 1, a + 1]))
                corridor_of.append(k)
                row_of.append(j)
        for j in c.snap:
            pairs = {(base + i * nr + j, base + (i + 1) * nr + j) for i in range(ns - 1)}
            breakline_edges[f"{c.name}:{j}"] = {(min(p), max(p)) for p in pairs}
        polygons.append(corridor_polygon(x, y))
    # the lattice cells to remove: those whose box meets a buffered corridor
    jj, ii = np.nonzero(grid.mask)
    cx, cy = grid.xy_of(jj, ii)
    boxes = shapely.box(cx - dx / 2, cy - dx / 2, cx + dx / 2, cy + dx / 2)
    tree = shapely.STRtree(boxes)
    hit = tree.query([p.buffer(buffer) if buffer > 0 else p for p in polygons], predicate="intersects")
    removed = np.zeros(jj.size, bool)
    removed[hit[1]] = True
    hole = shapely.unary_union(boxes[removed])
    for k, p in enumerate(polygons):
        if not hole.buffer(NODE_TOLERANCE).covers(p):
            at = p.difference(hole).representative_point()
            raise ValueError(
                f"corridor {corridors[k].name} reaches outside the active cells near ({at.x:.0f}, {at.y:.0f}): "
                "keep it a cell inside the domain"
            )
    gap = hole.difference(shapely.unary_union(polygons))
    gaps = [g for g in (gap.geoms if hasattr(gap, "geoms") else [gap]) if g.area > 1e-6]
    # nodes: the corridors', then every lattice corner on the hole's boundary
    corner_xy = shapely.get_coordinates(hole.boundary)
    xy = np.column_stack((np.array(xs), np.array(ys)))
    known = cKDTree(xy)
    fresh = corner_xy[known.query(corner_xy)[0] > NODE_TOLERANCE] if xy.size else corner_xy
    fresh = np.unique(np.round(fresh, 6), axis=0)
    xy = np.vstack((xy, fresh)) if fresh.size else xy
    tree_nodes = cKDTree(xy)

    def node(p: np.ndarray) -> int:
        d, i = tree_nodes.query(p)
        if d > NODE_TOLERANCE:
            raise RuntimeError(f"no node at {p} (nearest {d:.4f} m away)")
        return int(i)

    gap_start = len(rings)
    for g in gaps:
        shell = _conform_ring(np.asarray(g.exterior.coords), tree_nodes, xy)
        holes = [_conform_ring(np.asarray(r.coords), tree_nodes, xy) for r in g.interiors]
        for t in shapely.constrained_delaunay_triangles(shapely.Polygon(shell, holes)).geoms:
            pts = np.asarray(t.exterior.coords)[:3]
            ids = [node(p) for p in pts]
            twice = (pts[1, 0] - pts[0, 0]) * (pts[2, 1] - pts[0, 1]) - (pts[2, 0] - pts[0, 0]) * (pts[1, 1] - pts[0, 1])
            if twice < 0:
                ids = ids[::-1]
            rings.append(np.array(ids))
            corridor_of.append(-1)
            row_of.append(-1)
    merged = merge_slivers(xy, rings[gap_start:], merge * dx) if merge > 0.0 else rings[gap_start:]
    rings = rings[:gap_start] + merged
    corridor_of = corridor_of[:gap_start] + [-1] * len(merged)
    row_of = row_of[:gap_start] + [-1] * len(merged)
    geometry = MeshGeometry.from_rings(xy[:, 0], xy[:, 1], rings)
    return StripMesh(
        geometry, (jj[removed], ii[removed]), np.array(corridor_of, np.int64), np.array(row_of, np.int64),
        breakline_edges, polygons,
    )  # fmt: skip


def _convex(xy: np.ndarray, ring: np.ndarray) -> bool:
    p = xy[ring]
    d = np.roll(p, -1, axis=0) - p
    cross = d[:, 0] * np.roll(d, -1, axis=0)[:, 1] - d[:, 1] * np.roll(d, -1, axis=0)[:, 0]
    return bool((cross > 1e-9 * float(np.abs(cross).max())).all())


def merge_slivers(xy: np.ndarray, triangles: list[np.ndarray], dn_min: float) -> list[np.ndarray]:
    """Pairs of gap triangles whose centres stand closer than ``dn_min`` along their shared face become one quad when
    it is convex; closest pairs first, each triangle in one pair a pass, passes until nothing merges. The time step
    of the whole model follows the smallest centre-to-centre distance across a wet face, and the constrained Delaunay
    of a gap on the existing nodes leaves slivers where a corridor node stands near a lattice corner."""
    rings = [np.asarray(r, np.int64) for r in triangles]
    while True:
        edges: dict[tuple[int, int], list[int]] = {}
        for k, r in enumerate(rings):
            if r.size != 3:
                continue
            for m in range(3):
                a, b = int(r[m]), int(r[(m + 1) % 3])
                edges.setdefault((min(a, b), max(a, b)), []).append(k)
        pairs = []
        for (a, b), ks in edges.items():
            if len(ks) != 2:
                continue
            ca, cb = xy[rings[ks[0]]].mean(axis=0), xy[rings[ks[1]]].mean(axis=0)
            ex, ey = xy[b] - xy[a]
            length = float(np.hypot(ex, ey))
            if length < 1e-9:
                continue
            dn = abs((cb[0] - ca[0]) * ey - (cb[1] - ca[1]) * ex) / length
            if dn < dn_min:
                pairs.append((dn, ks[0], ks[1], a, b))
        pairs.sort()
        used: set[int] = set()
        gone: set[int] = set()
        for _dn, ka, kb, a, b in pairs:
            if ka in used or kb in used:
                continue
            ra, rb = rings[ka], rings[kb]
            w = int(next(v for v in rb if v != a and v != b))
            m = int(np.nonzero((ra == a) | (ra == b))[0].min())
            if {int(ra[m]), int(ra[(m + 1) % 3])} != {a, b}:
                m = (m + 2) % 3  # the shared edge runs from the last node to the first
            quad = np.concatenate((ra[: m + 1], [w], ra[m + 1 :]))
            if _convex(xy, quad):
                rings[ka] = quad
                used.update((ka, kb))
                gone.add(kb)
        if not gone:
            return rings
        rings = [r for k, r in enumerate(rings) if k not in gone]


def breakline_faces(mesh: StripMesh) -> dict[str, np.ndarray]:
    """Per snapped line the indices of the geometry's faces lying on it."""
    pairs = {(int(min(a, b)), int(max(a, b))): f for f, (a, b) in enumerate(mesh.geometry.face_node.tolist())}
    return {name: np.array(sorted(pairs[e] for e in edges if e in pairs), np.int64) for name, edges in mesh.breakline_edges.items()}
