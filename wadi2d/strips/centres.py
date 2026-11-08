# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cells from their centres: the generator of W46, his rules of 2026-11-08.

A breakline is a chain of faces: mirrored centres half a cell either side of each station make the chord between
two stations a face by construction, as HEC-RAS enforces its breaklines, and the two cells on it are 4-sided. Rows
of centres repeat outward, a cell apart, as far as the bank on that side (``floor``), and the mesh is the Voronoi
diagram of all centres together with the lattice centres around them, so the squares stay exact squares, the cells
along a line are 4-sided, and the transition between them comes out as polygons of five to eight faces, no
triangle. A cell under the minimum area merges by losing a centre (a mirrored pair never goes: the centre behind it
does, outward), the lattice centres of the band relax towards their cell's centroid, and a cell over the face limit
loses its centre too. Lines rank by drainage area, hard lines (dykes, roads, crests) first: the higher rank places its
centres first, and a lower line's station whose pair would land within the clearance (two cells) of a placed centre
ends the line there, so a tributary stops short of the main stream with a cell of the band between them, the main
keeps its clean rows through the junction, and a cell of the main squeezed by a lower line's centre drops that
centre, never its own.
A guide line turning more than a 4-sided cell allows in one station is smoothed there; a hard line is reported.

The join to the squares: every lattice centre within the band is a strip cell (a square where nothing disturbs it),
the ring of lattice positions beyond bounds the diagram, and a face between two unmoved lattice centres is their
lattice edge, so every face between the strip and the squares is a lattice edge, as the hybrid step needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.spatial import Voronoi, cKDTree

from wadi2d.grid.tiles import TileGrid
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.mesher import StripMesh, resample

NEAR = 0.75
"""A lattice centre within this many cells of a line centre goes: a sliver would form between them."""
RELAX = 1.0
"""Lattice centres within this many cells of a line centre may move towards their cell's centroid; farther ones
stay on the lattice."""
BAND = 3.5
"""Lattice centres within this many cells of a line centre are strip cells, polygons of the diagram. A cell on the
band's rim has a frame neighbour and so stands over BAND - 1 cells from any line centre, and its own neighbours over
BAND - 1 - sqrt(2): with BAND at least RELAX + 2.42 none of them moved, so every rim cell is an exact square and every
face to the squares is a lattice edge."""
FRAME = 5.0
"""Lattice positions out to this many cells bound the diagram; their cells are the squares and are not taken."""
TURN_MAX = np.radians(57.0)
"""A guide line turning more than this in one station cannot carry a 4-sided cell on the inner side: smoothed."""
SNAP = 1e-6
"""Vertices this close, m, are one node."""
CORNER_SNAP = 1e-4
"""A vertex this close to a lattice corner, m, is that corner, so the join faces are the lattice's own edges."""
SMOOTH_WINDOW = 5
HOLD = 3


@dataclass
class Line:
    """A breakline for the generator: its vertices, its rank (drainage area; hard lines take infinity) and kind."""

    name: str
    xy: np.ndarray
    rank: float
    hard: bool = False


@dataclass(frozen=True)
class CentreSettings:
    dx: float
    min_area_fraction: float = 0.4
    max_faces: int = 8
    clearance_cells: float = 2.0
    relax_rounds: int = 2
    merge_rounds: int = 3
    hard_rows: int = 1
    max_cells: int = 12
    smooth: int = 5
    min_stations: int = 3
    min_share: float = 0.5


@dataclass
class Placed:
    """Every centre of the diagram and what it is."""

    xy: np.ndarray
    line: np.ndarray
    """Line index, -1 for a lattice centre."""
    station: np.ndarray
    side: np.ndarray
    """+1 left, -1 right, 0 lattice."""
    row: np.ndarray
    """0 for a mirrored pair, k for the k-th row out, -1 lattice."""
    relaxable: np.ndarray
    notes: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return int(self.xy.shape[0])

    def keep(self, mask: np.ndarray) -> Placed:
        return Placed(self.xy[mask], self.line[mask], self.station[mask], self.side[mask], self.row[mask], self.relaxable[mask], self.notes)


JUNCTION_M = 5.0
"""A segment ending this close to another's start meets it at a junction."""


def chain_streams(thalwegs: list[dict], tolerance: float = JUNCTION_M) -> list[dict]:
    """The Suggest file cuts every stream into segments at the junctions, each running downstream with the drainage
    area at its outlet. Here the segments are chained into stems: at every junction the inflow with the larger area
    continues into the downstream segment, the smaller one is a tributary ending there. A stem carries its outlet's
    area as its rank, so it is placed first and its rows run unbroken through every junction, and the tributaries end
    short of it (his circles of 2026-11-08: the main channel runs uninterrupted, a branch never disturbs its bed).
    Returns dicts like the input (line, area_km2, incised_m), the chained stems first."""
    if not thalwegs:
        return []
    starts = np.array([np.asarray(t["line"].coords)[0, :2] for t in thalwegs])
    ends = np.array([np.asarray(t["line"].coords)[-1, :2] for t in thalwegs])
    areas = np.array([float(t["area_km2"]) for t in thalwegs])
    d, k = cKDTree(starts).query(ends)
    feeds: dict[int, list[int]] = {}  # downstream segment -> the segments ending at its start
    for i in range(len(thalwegs)):
        if d[i] <= tolerance and k[i] != i:
            feeds.setdefault(int(k[i]), []).append(i)
    continues: dict[int, int] = {}  # upstream segment -> the downstream segment it continues into
    for down, ups in feeds.items():
        main = max(ups, key=lambda i: areas[i])
        continues[main] = down
    fed = set(continues.values())
    out = []
    for head in range(len(thalwegs)):
        if head in fed:
            continue  # not the top of a chain
        chain = [head]
        while chain[-1] in continues:
            chain.append(continues[chain[-1]])
        coords = [np.asarray(thalwegs[chain[0]]["line"].coords)[:, :2]]
        for i in chain[1:]:
            coords.append(np.asarray(thalwegs[i]["line"].coords)[1:, :2])  # the junction point once
        incised = float(np.mean([thalwegs[i].get("incised_m", 0.0) for i in chain]))
        out.append({"line": shapely.LineString(np.vstack(coords)), "area_km2": float(areas[chain[-1]]), "incised_m": incised, "segments": len(chain)})
    return sorted(out, key=lambda t: -t["area_km2"])


def turns_of(pts: np.ndarray) -> np.ndarray:
    """The turn at every interior vertex, radians, left positive; zero at the ends."""
    t = np.diff(pts, axis=0)
    angle = np.arctan2(t[:, 1], t[:, 0])
    turn = np.zeros(pts.shape[0])
    if pts.shape[0] > 2:
        turn[1:-1] = np.angle(np.exp(1j * np.diff(angle)))
    return turn


def stations_of(line: Line, s: CentreSettings) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """The line's stations every cell along it and their left normals; a guide line smoothed where it turns more
    than a 4-sided cell allows, a hard line reported there."""
    notes: list[str] = []
    pts = resample(shapely.LineString(line.xy), s.dx, s.smooth if not line.hard else 0)
    if not line.hard:
        for _round in range(8):
            turn = turns_of(pts)
            sharp = np.nonzero(np.abs(turn) > TURN_MAX)[0]
            if sharp.size == 0:
                break
            smoothed = pts.copy()
            for i in sharp:
                smoothed[i] = pts[i - 1 : i + 2].mean(axis=0)
            pts = resample(shapely.LineString(smoothed), s.dx, 0)
    else:
        turn = turns_of(pts)
        for i in np.nonzero(np.abs(turn) > TURN_MAX)[0]:
            notes.append(
                f"hard line {line.name} turns {np.degrees(abs(turn[i])):.0f} degrees in one station near"
                f" ({pts[i, 0]:.0f}, {pts[i, 1]:.0f}): no 4-sided cell fits its inner side"
            )
    n = pts.shape[0]
    ahead = pts[np.minimum(np.arange(n) + 1, n - 1)]
    behind = pts[np.maximum(np.arange(n) - 1, 0)]
    tang = ahead - behind
    tang /= np.maximum(np.hypot(tang[:, 0], tang[:, 1]), 1e-12)[:, None]
    return pts, np.column_stack((-tang[:, 1], tang[:, 0])), notes


def counts_of(distance: np.ndarray, s: CentreSettings) -> np.ndarray:
    """Cells on one side at every station from the bank distance: rounded to whole cells, one at least where the
    side has a bank, the running median over five stations, a change held only when it lasts three."""
    n = np.where(np.isfinite(distance), np.clip(np.round(distance / s.dx), 1, s.max_cells), 1).astype(np.int64)
    if n.size >= SMOOTH_WINDOW:
        half = SMOOTH_WINDOW // 2
        n = np.array([int(np.median(n[max(0, i - half) : i + half + 1])) for i in range(n.size)])
    held = n.copy()
    current = int(n[0]) if n.size else 1
    i = 0
    while i < n.size:
        if n[i] == current:
            held[i] = current
            i += 1
            continue
        run = 1
        while i + run < n.size and n[i + run] == n[i]:
            run += 1
        if run >= HOLD:
            current = int(n[i])
        held[i : i + run] = current
        i += run
    return held


def place_centres(
    lines: list[Line], floors: list[tuple[np.ndarray, np.ndarray] | None], s: CentreSettings, inside=None
) -> tuple[Placed, list[list[int]]]:
    """The line centres of every line in rank order: mirrored pairs at every station, rows outward to the bank;
    a lower line's station within the clearance of a placed centre ends it there, and so does a station whose pair
    would stand outside the active cells (``inside``: points to a boolean array). Returns the centres and per line
    the stations it kept, for the record."""
    order = sorted(range(len(lines)), key=lambda k: (not lines[k].hard, -lines[k].rank))
    xs, ls, st, sd, rw = [], [], [], [], []
    notes: list[str] = []
    kept_stations: list[list[int]] = [[] for _ in lines]
    clearance = s.clearance_cells * s.dx
    for k in order:
        line = lines[k]
        pts, normals, words = stations_of(line, s)
        notes.extend(words)
        if pts.shape[0] < 2:
            notes.append(f"line {line.name} is shorter than a cell: no centres")
            continue
        if line.hard or floors[k] is None:
            n_left = n_right = np.full(pts.shape[0], s.hard_rows + 1, np.int64)
        else:
            left_d, right_d = floors[k]
            both = np.isfinite(left_d) & np.isfinite(right_d)
            if both.mean() < s.min_share:
                notes.append(f"line {line.name}: banks on both sides along {100 * both.mean():.0f} % of its stations, under {100 * s.min_share:.0f} %: it keeps the squares")
                continue
            n_left, n_right = counts_of(left_d, s), counts_of(right_d, s)
        # the pairs are mirrored across each segment of the line, at its midpoint along its own normal, not across the
        # station along the mean normal: the four centres round every vertex are then equidistant from it, the
        # diagram's vertex falls on the line's vertex, and the chain of faces is the polyline itself with no short
        # face at a bend (his circled jog, 2026-11-08); the counts of a segment are the smaller of its two stations'
        seg = np.diff(pts, axis=0)
        length = np.maximum(np.hypot(seg[:, 0], seg[:, 1]), 1e-12)
        normals = np.column_stack((-seg[:, 1], seg[:, 0])) / length[:, None]
        pts = 0.5 * (pts[:-1] + pts[1:])
        n_left = np.minimum(n_left[:-1], n_left[1:])
        n_right = np.minimum(n_right[:-1], n_right[1:])
        placed = cKDTree(np.array(xs)) if xs else None
        # the pair decides whether a station lives: both its centres clear of every placed centre
        pair_l = pts + 0.5 * s.dx * normals
        pair_r = pts - 0.5 * s.dx * normals
        alive = np.ones(pts.shape[0], bool)
        if placed is not None:
            dl, _ = placed.query(pair_l)
            dr, _ = placed.query(pair_r)
            alive = (dl >= clearance) & (dr >= clearance)
        if inside is not None:
            alive &= np.asarray(inside(pair_l), bool) & np.asarray(inside(pair_r), bool)
        # pieces of consecutive live stations, each long enough
        pieces, start = [], None
        for i in range(pts.shape[0]):
            if alive[i]:
                start = i if start is None else start
            elif start is not None:
                pieces.append((start, i))
                start = None
        if start is not None:
            pieces.append((start, pts.shape[0]))
        pieces = [(a, b) for a, b in pieces if b - a >= s.min_stations]
        if not pieces:
            notes.append(f"line {line.name}: every station lies within the clearance of a higher line or outside the active cells, or too few stand together: no centres")
            continue
        dropped = int(pts.shape[0] - sum(b - a for a, b in pieces))
        if dropped:
            notes.append(f"line {line.name}: {dropped} of {pts.shape[0]} stations given up to higher lines, the domain's edge or too short to stand")
        own: list[np.ndarray] = []
        for a, b in pieces:
            kept_stations[k].extend(range(a, b))
            for side, sign, counts in ((1, 1.0, n_left), (-1, -1.0, n_right)):
                for i in range(a, b):
                    for j in range(int(counts[i])):
                        p = pts[i] + sign * (j + 0.5) * s.dx * normals[i]
                        if j > 0:
                            if placed is not None and placed.query(p)[0] < clearance:
                                break  # this row and the rows beyond it on this side give way
                            if inside is not None and not bool(np.asarray(inside(p[None, :]))[0]):
                                break  # the rows stop at the domain's edge
                            if own and cKDTree(np.vstack(own)).query(p)[0] < 0.5 * s.dx:
                                break  # the line's own rows meeting inside a bend
                        own.append(p[None, :])
                        xs.append(p)
                        ls.append(k)
                        st.append(i)
                        sd.append(side)
                        rw.append(j)
    xy = np.array(xs).reshape(-1, 2)
    out = Placed(xy, np.array(ls, np.int64), np.array(st, np.int64), np.array(sd, np.int64), np.array(rw, np.int64), np.zeros(len(xs), bool), notes)
    return out, kept_stations


def lattice_centres(
    grid: TileGrid, line_xy: np.ndarray, s: CentreSettings, keep_out: np.ndarray | None = None
) -> tuple[Placed, np.ndarray, tuple[np.ndarray, np.ndarray], np.ndarray]:
    """The lattice positions around the line centres: the band's active centres (strip cells, those within RELAX
    marked relaxable), the frame positions beyond (returned apart, active or not), the (j, i) of the active lattice
    cells the strip replaces, the band's and those dropped for standing too near a line centre, and the positions
    outside the domain near the lines. Squares in ``keep_out`` stay squares whatever stands near them."""
    dx = s.dx
    ny, nx = grid.shape
    if line_xy.shape[0] == 0:
        empty = Placed(np.zeros((0, 2)), np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, bool))
        return empty, np.zeros((0, 2)), (np.zeros(0, np.int64), np.zeros(0, np.int64)), np.zeros((0, 2))
    reach = int(np.ceil(FRAME)) + 1
    i0 = int(np.floor((line_xy[:, 0].min() - grid.x0) / dx)) - reach
    i1 = int(np.floor((line_xy[:, 0].max() - grid.x0) / dx)) + reach
    j0 = int(np.floor((grid.y0 - line_xy[:, 1].max()) / dx)) - reach
    j1 = int(np.floor((grid.y0 - line_xy[:, 1].min()) / dx)) + reach
    jj, ii = np.mgrid[j0 : j1 + 1, i0 : i1 + 1]
    jj, ii = jj.ravel(), ii.ravel()
    cx = grid.x0 + (ii + 0.5) * dx
    cy = grid.y0 - (jj + 0.5) * dx
    inside = (jj >= 0) & (jj < ny) & (ii >= 0) & (ii < nx)
    active = np.zeros(jj.size, bool)
    active[inside] = grid.mask[jj[inside], ii[inside]]
    kept = np.zeros(jj.size, bool)
    if keep_out is not None:
        kept[inside] = keep_out[jj[inside], ii[inside]]
    d, _ = cKDTree(line_xy).query(np.column_stack((cx, cy)))
    dropped = active & ~kept & (d < NEAR * dx)
    band = active & ~kept & ~dropped & (d <= BAND * dx)
    # the frame: active positions beyond the band, and positions outside the domain only beyond the band's reach, so
    # no frame point stands near a line centre and eats into the squares the strip must cover; the cells reaching
    # outside the domain are cut back to its squares instead
    frame = ~dropped & ~band & (d <= FRAME * dx) & (active | (d > BAND * dx))
    placed = Placed(
        np.column_stack((cx[band], cy[band])), np.full(int(band.sum()), -1, np.int64), np.full(int(band.sum()), -1, np.int64),
        np.zeros(int(band.sum()), np.int64), np.full(int(band.sum()), -1, np.int64), d[band] <= RELAX * dx,
    )  # fmt: skip
    masked = dropped | band
    blocked = ~active & (d <= FRAME * dx)  # positions outside the domain near the lines: the strip ends against them
    return placed, np.column_stack((cx[frame], cy[frame])), (jj[masked], ii[masked]), np.column_stack((cx[blocked], cy[blocked]))


def _rings_of(points: np.ndarray, nreal: int, grid: TileGrid, dx: float) -> tuple[np.ndarray, list[np.ndarray], dict[tuple[int, int], tuple[int, int]]]:
    """The Voronoi diagram of all points: the nodes (vertices snapped to lattice corners where they are one, then
    merged), one counter-clockwise ring of node indices per real point, and per pair of real points sharing a face
    the two nodes of that face."""
    vor = Voronoi(points)
    v = vor.vertices.copy()
    # a vertex at a lattice corner is that corner exactly, so the join faces are the lattice's own edges
    ci = np.round((v[:, 0] - grid.x0) / dx)
    cj = np.round((grid.y0 - v[:, 1]) / dx)
    corner_x, corner_y = grid.x0 + ci * dx, grid.y0 - cj * dx
    at_corner = (np.abs(v[:, 0] - corner_x) < CORNER_SNAP) & (np.abs(v[:, 1] - corner_y) < CORNER_SNAP)
    v[at_corner, 0], v[at_corner, 1] = corner_x[at_corner], corner_y[at_corner]
    key = np.round(v / SNAP).astype(np.int64)
    _uniq, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.ravel()
    nodes = v[first]
    rings: list[np.ndarray] = []
    for p in range(nreal):
        region = vor.regions[vor.point_region[p]]
        if not region or -1 in region:
            raise ValueError(f"the diagram is unbounded at ({points[p, 0]:.0f}, {points[p, 1]:.0f}): a line centre too near the edge of the lattice")
        ids = inverse[np.asarray(region, np.int64)]
        keep = np.ones(ids.size, bool)
        keep[1:] = ids[1:] != ids[:-1]
        ids = ids[keep]
        if ids.size > 1 and ids[0] == ids[-1]:
            ids = ids[:-1]
        if ids.size >= 3:
            x, y = nodes[ids, 0], nodes[ids, 1]
            if 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) < 0.0:
                ids = ids[::-1]
        rings.append(ids)
    shared: dict[tuple[int, int], tuple[int, int]] = {}
    for (a, b), (va, vb) in zip(vor.ridge_points.tolist(), vor.ridge_vertices, strict=True):
        if a < nreal and b < nreal and va >= 0 and vb >= 0:
            na, nb = int(inverse[va]), int(inverse[vb])
            if na != nb:
                shared[(min(a, b), max(a, b))] = (min(na, nb), max(na, nb))
    return nodes, rings, shared


def _areas_centroids(nodes: np.ndarray, rings: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    area = np.zeros(len(rings))
    cen = np.zeros((len(rings), 2))
    for k, r in enumerate(rings):
        if r.size < 3:
            continue
        x, y = nodes[r, 0], nodes[r, 1]
        x1, y1 = np.roll(x, -1), np.roll(y, -1)
        cross = x * y1 - x1 * y
        a = 0.5 * cross.sum()
        area[k] = a
        if abs(a) > 1e-12:
            cen[k] = (((x + x1) * cross).sum() / (6.0 * a), ((y + y1) * cross).sum() / (6.0 * a))
        else:
            cen[k] = (x.mean(), y.mean())
    return area, cen


SHORT_FACE = 0.15
"""A face shorter than this share of a cell is contracted to a node: the Voronoi diagram of lattice and line centres
leaves edges of a few centimetres to a few metres where four centres are nearly equidistant from a vertex, and a face
that short carries a degenerate conveyance table and set the time step at 0.07 s on Faydh (2026-11-08)."""


def _contract_short_faces(nodes: np.ndarray, rings: list[np.ndarray], grid: TileGrid, dx: float) -> tuple[np.ndarray, list[np.ndarray]]:
    """Every face shorter than SHORT_FACE cells merged into one node, at the midpoint, or at the lattice corner when
    one end is one (so the join faces stay the lattice's edges); the rings re-threaded, repeated until none is left.
    Moving a shared vertex passes area between the cells around it and changes their sum by nothing."""
    nodes = nodes.copy()
    limit = SHORT_FACE * dx
    ci = np.round((nodes[:, 0] - grid.x0) / dx)
    cj = np.round((grid.y0 - nodes[:, 1]) / dx)
    corner = (np.abs(nodes[:, 0] - (grid.x0 + ci * dx)) < CORNER_SNAP) & (np.abs(nodes[:, 1] - (grid.y0 - cj * dx)) < CORNER_SNAP)
    parent = np.arange(nodes.shape[0])

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for _round in range(6):
        merged = 0
        seen: set[tuple[int, int]] = set()
        for r in rings:
            for k in range(r.size):
                a, b = find(int(r[k])), find(int(r[(k + 1) % r.size]))
                if a == b:
                    continue
                key = (min(a, b), max(a, b))
                if key in seen:
                    continue
                seen.add(key)
                if np.hypot(*(nodes[a] - nodes[b])) < limit:
                    if corner[a] and corner[b]:
                        continue  # a lattice edge is never that short; two corners stay apart
                    keep, gone = (a, b) if corner[a] else ((b, a) if corner[b] else (a, b))
                    if not corner[keep]:
                        nodes[keep] = 0.5 * (nodes[a] + nodes[b])
                    parent[gone] = keep
                    merged += 1
        if merged == 0:
            break
        out = []
        for r in rings:
            ids = np.array([find(int(v)) for v in r], np.int64)
            keep_mask = np.ones(ids.size, bool)
            keep_mask[1:] = ids[1:] != ids[:-1]
            ids = ids[keep_mask]
            if ids.size > 1 and ids[0] == ids[-1]:
                ids = ids[:-1]
            out.append(ids)
        rings = out
    return nodes, rings


def _clip_to_hole(nodes: np.ndarray, rings: list[np.ndarray], which: np.ndarray, hole: shapely.Geometry) -> tuple[np.ndarray, list[np.ndarray]]:
    """The rings named in ``which`` cut to the hole the strip fills (the squares it replaces), so at the domain's
    edge a cell ends on the lattice edges there; new vertices become nodes, a cell cut to pieces keeps its largest."""
    shapely.prepare(hole)
    keys = np.round(nodes / SNAP).astype(np.int64)
    lookup = {(int(a), int(b)): i for i, (a, b) in enumerate(keys.tolist())}
    extra: list[np.ndarray] = []

    def node_of(pt: np.ndarray) -> int:
        key = (int(round(pt[0] / SNAP)), int(round(pt[1] / SNAP)))
        k = lookup.get(key)
        if k is None:
            k = nodes.shape[0] + len(extra)
            extra.append(np.asarray(pt, np.float64))
            lookup[key] = k
        return k

    for c in which.tolist():
        ring = rings[c]
        if ring.size < 3:
            continue
        poly = shapely.Polygon(nodes[ring])
        if hole.covers(poly):
            continue
        clipped = poly.intersection(hole)
        if clipped.is_empty or clipped.area < 1e-9:
            rings[c] = ring[:0]
            continue
        if clipped.geom_type != "Polygon":
            clipped = max((g for g in clipped.geoms if g.geom_type == "Polygon"), key=lambda g: g.area, default=None)
            if clipped is None:
                rings[c] = ring[:0]
                continue
        coords = np.asarray(clipped.exterior.coords)[:-1]
        x, y = coords[:, 0], coords[:, 1]
        if 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y) < 0.0:
            coords = coords[::-1]
        ids = np.array([node_of(p) for p in coords], np.int64)
        keep = np.ones(ids.size, bool)
        keep[1:] = ids[1:] != ids[:-1]
        rings[c] = ids[keep]
    if extra:
        nodes = np.vstack((nodes, np.array(extra)))
    return nodes, rings


def _common_edge(ra: np.ndarray, rb: np.ndarray) -> tuple[int, int] | None:
    """The face two counter-clockwise rings share, as its two nodes, or None."""
    edges = {(int(ra[k]), int(ra[(k + 1) % ra.size])) for k in range(ra.size)}
    for k in range(rb.size):
        e = (int(rb[(k + 1) % rb.size]), int(rb[k]))  # the neighbour runs the shared face the other way
        if e in edges:
            return (min(e), max(e))
    return None


def build_centre_mesh(
    grid: TileGrid, lines: list[Line], floors: list[tuple[np.ndarray, np.ndarray] | None], s: CentreSettings,
    keep_out: np.ndarray | None = None,
) -> StripMesh:
    """The mesh of a job's lines on the lattice: see the module's words. ``keep_out`` marks the lattice squares that
    must stay squares, the cells of the job's boundary lines: the strip ends BAND cells before them, so its water
    leaves through squares that carry the boundary (the strip covering the outlet's squares ponded 23 m deep at
    Faydh's outlet, 2026-11-08, since a strip face on the domain's edge is a wall)."""
    dx = s.dx
    ny, nx = grid.shape
    kept_tree = None
    if keep_out is not None and keep_out.any():
        kj, ki = np.nonzero(keep_out)
        kept_tree = cKDTree(np.column_stack((grid.x0 + (ki + 0.5) * dx, grid.y0 - (kj + 0.5) * dx)))

    def inside(xy: np.ndarray) -> np.ndarray:
        """Whether points stand in active squares of the lattice, clear of the squares kept for the boundaries."""
        j = np.floor((grid.y0 - xy[:, 1]) / dx).astype(np.int64)
        i = np.floor((xy[:, 0] - grid.x0) / dx).astype(np.int64)
        ok = (j >= 0) & (j < ny) & (i >= 0) & (i < nx)
        ok[ok] = grid.mask[j[ok], i[ok]]
        if kept_tree is not None and ok.any():
            d, _ = kept_tree.query(xy[ok])
            ok[np.nonzero(ok)[0][d <= BAND * dx]] = False
        return ok

    centres, kept_stations = place_centres(lines, floors, s, inside)
    notes = list(centres.notes)
    if centres.n == 0:
        raise ValueError("no line gave a centre: " + ("; ".join(notes) if notes else "no lines"))
    band, frame, masked, blocked = lattice_centres(grid, centres.xy, s, keep_out)
    # at the domain's edge the diagram is bounded by positions outside it; the cells there are cut to the squares the
    # strip replaces, so the strip ends on lattice edges whatever the line does near the edge
    hole = None
    edge_tree = cKDTree(blocked) if blocked.shape[0] else None
    if edge_tree is not None and masked[0].size:
        mx = grid.x0 + (masked[1] + 0.5) * dx
        my = grid.y0 - (masked[0] + 0.5) * dx
        dm, _ = edge_tree.query(np.column_stack((mx, my)))
        close = dm <= 4.5 * dx
        if close.any():
            hole = shapely.unary_union(shapely.box(mx[close] - dx / 2, my[close] - dx / 2, mx[close] + dx / 2, my[close] + dx / 2))
    ok = inside(centres.xy)  # the stations' own rule keeps every centre inside; this is the safety on it
    if not ok.all():
        bad = np.nonzero(~ok)[0]
        names = sorted({lines[int(centres.line[b])].name for b in bad})
        at = centres.xy[bad[0]]
        raise ValueError(
            f"{bad.size} centres of {', '.join(names[:4])} stand outside the active cells near ({at[0]:.0f}, {at[1]:.0f}): "
            "keep the lines a cell inside the domain"
        )
    all_pts = Placed(
        np.vstack((centres.xy, band.xy)), np.concatenate((centres.line, band.line)), np.concatenate((centres.station, band.station)),
        np.concatenate((centres.side, band.side)), np.concatenate((centres.row, band.row)), np.concatenate((centres.relaxable, band.relaxable)),
    )  # fmt: skip
    min_area = s.min_area_fraction * dx * dx

    def diagram(p: Placed):
        pts = np.vstack((p.xy, frame))
        nodes, rings, shared = _rings_of(pts, p.n, grid, dx)
        if hole is not None:
            near, _ = edge_tree.query(p.xy)
            nodes, rings = _clip_to_hole(nodes, rings, np.nonzero(near <= 3.0 * dx)[0], hole)
        nodes, rings = _contract_short_faces(nodes, rings, grid, dx)
        area, cen = _areas_centroids(nodes, rings)
        return nodes, rings, shared, area, cen

    nodes, rings, shared, area, cen = diagram(all_pts)
    rank = np.array([(np.inf if line.hard else line.rank) for line in lines], np.float64)

    def neighbours_of(pairs) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for a, b in pairs:
            out.setdefault(a, []).append(b)
            out.setdefault(b, []).append(a)
        return out

    def crowding_lower(c: int, around: dict[int, list[int]]) -> int | None:
        """Among the centres sharing a face with cell ``c``, the one of the lowest-ranked line below ``c``'s own, or
        None: the higher line keeps its cells, a lower line's centre that squeezes them goes (his rule: the main stem
        wins the cells aligned to it; at a junction the tributary's last pair had cost the main its second row)."""
        own = rank[all_pts.line[c]]
        best, best_rank = None, np.inf
        for other in around.get(c, ()):
            if all_pts.line[other] < 0 or all_pts.line[other] == all_pts.line[c]:
                continue
            r = rank[all_pts.line[other]]
            if r < own and r < best_rank:
                best, best_rank = other, r
        return best

    # merge: a small cell loses a centre, a pair the centre behind it, a cell squeezed by a lower line that line's centre
    for _round in range(s.merge_rounds):
        small = np.nonzero(area < min_area)[0]
        if small.size == 0:
            break
        drop = np.zeros(all_pts.n, bool)
        around = neighbours_of(shared.keys())
        for c in small:
            lower = crowding_lower(int(c), around) if all_pts.line[c] >= 0 else None
            if lower is not None:
                drop[lower] = True
            elif all_pts.row[c] == 0 and all_pts.line[c] >= 0:
                behind = np.nonzero(
                    (all_pts.line == all_pts.line[c]) & (all_pts.station == all_pts.station[c]) & (all_pts.side == all_pts.side[c]) & (all_pts.row == 1)
                )[0]
                if behind.size:
                    drop[behind[0]] = True
                else:
                    notes.append(f"line {lines[int(all_pts.line[c])].name}: a cell on the line near ({cen[c, 0]:.0f}, {cen[c, 1]:.0f}) holds {area[c]:.0f} m2, under the minimum, and nothing behind it to merge")
            else:
                drop[c] = True
        if not drop.any():
            break
        all_pts = all_pts.keep(~drop)
        nodes, rings, shared, area, cen = diagram(all_pts)
    # relax the band's near lattice centres towards their centroids, then drop any cell still over the face limit
    for _round in range(s.relax_rounds):
        move = all_pts.relaxable
        if not move.any():
            break
        all_pts.xy[move] = cen[move]
        nodes, rings, shared, area, cen = diagram(all_pts)
    faces = np.array([r.size for r in rings])
    for _round in range(s.merge_rounds):
        # a band cell over the face limit loses its centre; a line cell cut to a triangle at a line's end loses the
        # centre behind it, as a small cell does; each drop can make a neighbour's count grow, so a few rounds
        over = (faces > s.max_faces) & (all_pts.line < 0)
        tri = (faces == 3)
        drop = over.copy()
        lattice_tree = cKDTree(all_pts.xy[all_pts.line < 0]) if (all_pts.line < 0).any() else None
        lattice_index = np.nonzero(all_pts.line < 0)[0]
        for c in np.nonzero(tri)[0]:
            if all_pts.line[c] >= 0 and all_pts.row[c] == 0:
                behind = np.nonzero((all_pts.line == all_pts.line[c]) & (all_pts.station == all_pts.station[c]) & (all_pts.side == all_pts.side[c]) & (all_pts.row == 1))[0]
                if behind.size:
                    drop[behind[0]] = True
                elif lattice_tree is not None:  # nothing of its own behind it: the lattice centre beyond it goes, and the cell grows outward
                    d, k = lattice_tree.query(cen[c])
                    if d <= 1.5 * dx:
                        drop[lattice_index[k]] = True
            else:
                drop[c] = True
        if not drop.any():
            break
        all_pts = all_pts.keep(~drop)
        nodes, rings, shared, area, cen = diagram(all_pts)
        faces = np.array([r.size for r in rings])
    gone = faces < 3  # a cell the domain's edge cut to nothing, or a sliver the merge rounds left: its centre goes
    if gone.any():
        all_pts = all_pts.keep(~gone)
        nodes, rings, shared, area, cen = diagram(all_pts)
        faces = np.array([r.size for r in rings])
        if (faces < 3).any():
            c = int(np.nonzero(faces < 3)[0][0])
            raise ValueError(f"a cell near ({all_pts.xy[c, 0]:.0f}, {all_pts.xy[c, 1]:.0f}) has no area after the domain's edge cut it: keep the line clear of the edge there")
    for c in np.nonzero(faces > s.max_faces)[0]:
        notes.append(f"a cell near ({cen[c, 0]:.0f}, {cen[c, 1]:.0f}) keeps {faces[c]} faces, over {s.max_faces}")
    # what the mesh is made of
    used = np.unique(np.concatenate(rings))
    index = np.full(nodes.shape[0], -1, np.int64)
    index[used] = np.arange(used.size)
    rings = [index[r] for r in rings]
    geometry = MeshGeometry.from_rings(nodes[used, 0], nodes[used, 1], rings)
    is_line = all_pts.line >= 0
    corridor = np.where(is_line, all_pts.line, -1).astype(np.int64)
    row = np.where(is_line, all_pts.row, -1).astype(np.int64)
    breakline_edges: dict[str, set[tuple[int, int]]] = {}
    by_key = {(int(all_pts.line[c]), int(all_pts.station[c]), int(all_pts.side[c])): c for c in range(all_pts.n) if is_line[c] and all_pts.row[c] == 0}
    for (k, i, side), c in by_key.items():
        if side != 1:
            continue
        other = by_key.get((k, i, -1))
        if other is None:
            continue
        edge = _common_edge(rings[c], rings[other])
        if edge is not None:
            breakline_edges.setdefault(f"{lines[k].name}:0", set()).add(edge)
    polygons: list[shapely.Geometry] = []
    for k in range(len(lines)):
        mine = np.nonzero(corridor == k)[0]
        if mine.size == 0:
            polygons.append(shapely.Polygon())
            continue
        polygons.append(shapely.unary_union([shapely.Polygon(np.column_stack((geometry.x[r], geometry.y[r]))) for r in (rings[c] for c in mine)]))
    # the cells tile the squares they replace, to the last digit that matters
    hole = masked[0].size * dx * dx
    tiled = float(area.sum())
    if abs(tiled - hole) > 1e-6 * max(hole, 1.0):
        raise ValueError(f"the cells cover {tiled:.1f} m2 where the squares they replace cover {hole:.1f}: the diagram and the lattice disagree")
    rules = [
        {"name": lines[k].name, "hard": lines[k].hard, "rank_km2": None if lines[k].hard else lines[k].rank, "stations": len(kept_stations[k]),
         "cells": int((corridor == k).sum()), "cells_across": int(np.bincount(np.abs(all_pts.station[corridor == k]), minlength=1).max()) if (corridor == k).any() else 0}
        for k in range(len(lines))
    ]  # fmt: skip
    mesh = StripMesh(geometry, masked, corridor, row, breakline_edges, polygons, notes, rules)
    return mesh


__all__ = ["BAND", "FRAME", "NEAR", "RELAX", "CentreSettings", "Line", "Placed", "build_centre_mesh", "chain_streams", "counts_of", "place_centres", "stations_of"]
