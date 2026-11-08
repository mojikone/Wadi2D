# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Corridors from suggested bank lines (W45, stage 7): the W44 recipe in the engine, the rows set by the wadi's width.

The Suggest breaklines layer gives each bank its side and the drainage area of the wadi it banks, and the thalwegs
layer the wadi lines. Per wadi, the parts of one side are chained along its thalweg; a left chain and the right chain
with the longest facing stretch make a pair; the pair's mid-line is the corridor's centre, its two banks the lines of
two rows. The rows between the banks share the width: the cell across is a share of the width within two bounds (his
rules of 2026-11-07: a narrow wadi runs on cells no smaller than about 20 m, since small cells set the step, a wide one
needs none larger than about 50 m), one row stands beyond each bank at the same size, and a wadi with one bank or none
keeps its squares. Each corridor is cut clear of the accepted ones and of the domain edge.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.strips.mesher import Corridor, corridor_cells, corridor_nodes, corridor_polygon, fold_free_pieces, midline

BANK = "stream bank"
GAP_CHAIN_M = 30.0
"""Bank parts closer than this are one chain."""
MIN_LENGTH_M = 300.0
"""A corridor shorter than this is not built."""
CLEAR_M = 25.0
"""A corridor stays this far from an accepted one."""
SPLIT_ROUNDS = 3
"""A piece cut clear of a fold is checked again this many times, its own resampling may fold anew."""


@dataclass
class BankPair:
    area_km2: float
    left: shapely.LineString
    right: shapely.LineString
    mid: shapely.LineString


@dataclass(frozen=True)
class CellRule:
    """How the rows of a corridor follow the wadi's width (the job's ``strips`` section)."""

    cell_min: float = 20.0
    cell_max: float = 50.0
    fraction: float = 0.25
    rows_outside: int = 1

    def layout(self, width: float) -> tuple[list[float], int, float]:
        """Row offsets across a wadi of ``width`` between its banks, the cells across and their size, m.

        The cell across is ``fraction`` of the width held between the bounds, then the width is split into the
        nearest whole number of such cells, one at least, so the two bank rows stand at the banks; ``rows_outside``
        rows follow beyond each bank at the size the inner cells got.
        """
        wanted = float(np.clip(width * self.fraction, self.cell_min, self.cell_max))
        n = max(1, int(round(width / wanted)))
        across = width / n
        half = 0.5 * width
        inner = np.linspace(-half, half, n + 1)
        outer = half + across * np.arange(1, self.rows_outside + 1)
        offsets = np.concatenate((-outer[::-1], inner, outer))
        return [float(v) for v in offsets], n, across


def pair_width(pair: BankPair, step: float = 10.0) -> float:
    """The median distance between the two banks along the mid-line, m."""
    stations = np.arange(0.0, pair.mid.length + 1e-9, step)
    points = [pair.mid.interpolate(s) for s in stations]
    return float(np.median([pair.left.distance(p) + pair.right.distance(p) for p in points]))


def read_layers(path) -> tuple[list[dict], dict[float, shapely.LineString]]:
    """The bank lines (line, side, area_km2) and the thalwegs by drainage area, from the suggestion file."""
    import fiona

    banks = []
    with fiona.open(path, layer="breaklines") as src:
        for f in src:
            p = dict(f["properties"])
            if p.get("kind") != BANK:
                continue
            g = shapely.geometry.shape(f["geometry"])
            parts = g.geoms if g.geom_type == "MultiLineString" else [g]
            for part in parts:
                banks.append({"line": shapely.LineString(np.asarray(part.coords)[:, :2]), "side": p["side"], "area_km2": float(p["area_km2"])})
    thalwegs = {}
    with fiona.open(path, layer="thalwegs") as src:
        for f in src:
            g = shapely.geometry.shape(f["geometry"])
            if g.geom_type == "MultiLineString":
                g = max(g.geoms, key=lambda part: part.length)
            thalwegs[float(f["properties"]["area_km2"])] = shapely.LineString(np.asarray(g.coords)[:, :2])
    return banks, thalwegs


def read_thalwegs(path) -> list[dict]:
    """Every thalweg of the suggestion file as (line, area_km2, incised_m), in file order."""
    import fiona

    out = []
    with fiona.open(path, layer="thalwegs") as src:
        for f in src:
            g = shapely.geometry.shape(f["geometry"])
            if g.geom_type == "MultiLineString":
                g = max(g.geoms, key=lambda part: part.length)
            p = dict(f["properties"])
            out.append({"line": shapely.LineString(np.asarray(g.coords)[:, :2]), "area_km2": float(p["area_km2"]), "incised_m": float(p.get("incised_m") or 0.0)})
    return out


def corridor_specs_thalweg(
    thalwegs: list[dict],
    banks: list[dict],
    domain: shapely.Polygon,
    cell: float = 30.0,
    along: float = 30.0,
    reach: float = 300.0,
    min_share: float = 0.5,
    min_length: float = MIN_LENGTH_M,
    fixed: bool = True,
    max_cells: int = 12,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Corridors on the thalwegs themselves out to the banks (his direction of 2026-11-07: the centre lines drive
    the cells, the floor's edges say how far the cells repeat across).

    Per thalweg, biggest first: the distance from each station to the nearest bank of its own on each side; the
    thalweg is a defined wadi where both sides have one on at least ``min_share`` of its stations, else it keeps the
    squares. With ``fixed`` the corridor is ragged: cells of ``cell`` across at whole multiples of it either side,
    as many at each station as fit to the bank on that side, one at least, ``max_cells`` at most (his word: not
    varying cell sizes). Otherwise the rows run from the median right half-width to the median left one in cells of
    about ``cell``, the two edge rows snapped to the bank lines where they exist and kept at the median where they
    do not. Each corridor is cut clear of the accepted ones, the domain edge and its own folds. Returns the specs,
    the rejected or cut pieces with why, and per corridor the width, the cells across and their size."""
    by_area: dict[float, dict[str, list]] = defaultdict(lambda: {"left": [], "right": []})
    for b in banks:
        by_area[b["area_km2"]][b["side"]].append(b["line"])
    accepted: list[dict] = []
    polygons: list[shapely.Polygon] = []
    rejected: list[dict] = []
    rules: list[dict] = []
    edges: dict[float, tuple[shapely.Geometry, shapely.Geometry]] = {}
    for k, t in enumerate(sorted(thalwegs, key=lambda t: -t["area_km2"])):
        tag = f"thalweg {k} area {t['area_km2']:.2f} km2"
        line = t["line"]
        if line.length < min_length:
            continue
        sides = by_area.get(t["area_km2"])
        if not sides or not sides["left"] or not sides["right"]:
            rejected.append({"tag": tag, "why": "a bank on one side or none: not a defined wadi, the squares stay"})
            continue
        stations = np.arange(0.0, line.length + 1e-9, along)
        points = shapely.points(np.array([np.asarray(line.interpolate(s).coords[0])[:2] for s in stations]))
        half: dict[str, np.ndarray] = {}
        for side in ("left", "right"):
            union = shapely.union_all(sides[side])
            d = shapely.distance(points, union)
            half[side] = np.where(d <= reach, d, np.nan)
        both = np.isfinite(half["left"]) & np.isfinite(half["right"])
        share = float(both.mean()) if both.size else 0.0
        if share < min_share:
            rejected.append({"tag": tag, "why": f"banks on both sides along {100 * share:.0f} % of it, under {100 * min_share:.0f} %: not a defined wadi"})
            continue
        hl = float(np.nanmedian(half["left"]))
        hr = float(np.nanmedian(half["right"]))
        width = hl + hr
        if fixed:
            n_left = np.clip(np.round(np.where(np.isfinite(half["left"]), half["left"], cell) / cell), 1, max_cells)
            n_right = np.clip(np.round(np.where(np.isfinite(half["right"]), half["right"], cell) / cell), 1, max_cells)
            n = int(np.median(n_left + n_right))
            offsets = []
            extent = round(cell * float(max(n_left.max(), n_right.max())), 1)
            floor = {"left": shapely.union_all(sides["left"]), "right": shapely.union_all(sides["right"])}
        else:
            n = max(1, int(round(width / cell)))
            offsets = [float(v) for v in np.linspace(-hr, hl, n + 1)]
            extent = round(max(hl, hr), 1)
            floor = None
        if extent not in edges:
            edges[extent] = (
                domain.buffer(-(extent + along)),
                domain.envelope.buffer(4.0 * extent).difference(domain.buffer(-along)),
            )
        inside, outside = edges[extent]
        free = line.intersection(inside)
        if polygons:
            free = free.difference(shapely.unary_union([p.buffer(CLEAR_M) for p in polygons]))
        if free.is_empty:
            rejected.append({"tag": tag, "why": "inside an accepted corridor's clearance or outside the domain"})
            continue
        parts = [g for g in (free.geoms if hasattr(free, "geoms") else [free]) if g.geom_type == "LineString" and g.length >= min_length]
        if not parts:
            rejected.append({"tag": tag, "why": f"free stretches all under {min_length:.0f} m"})
            continue
        lines_of = {side: [[[float(x), float(y)] for x, y in np.asarray(ln.coords)[:, :2]] for ln in sides[side]] for side in ("left", "right")}
        snap_rows = [] if fixed else [
            {"row": n, "coordinates": lines_of["left"], "lines": sides["left"]},
            {"row": 0, "coordinates": lines_of["right"], "lines": sides["right"]},
        ]
        for m, part in enumerate(parts):
            spec = {
                "name": f"t{k}_{t['area_km2']:.1f}km2" + (f"_{m}" if len(parts) > 1 else ""),
                "centre": [[float(x), float(y)] for x, y in np.asarray(part.coords)[:, :2]],
                "offsets": offsets,
                "snap": [{"row": r["row"], "coordinates": r["coordinates"]} for r in snap_rows],
            }
            if fixed:
                spec.update(edges_left=lines_of["left"], edges_right=lines_of["right"], cell_m=cell, max_cells=max_cells)
            snap = {r["row"]: shapely.union_all(r["lines"]) for r in snap_rows}
            keep_out = shapely.unary_union([outside, *[p.buffer(CLEAR_M) for p in polygons]])
            pieces, cut = fold_free_specs(
                spec, along, keep_out=keep_out, min_length=min_length, snap=snap, snap_nearest=False, edges=floor, cell=cell if fixed else 0.0
            )
            rejected.extend({"tag": tag, "why": words} for words in cut)
            for piece in pieces:
                accepted.append(piece)
                rules.append({
                    "name": piece["name"], "area_km2": round(t["area_km2"], 2), "width_m": round(width, 1),
                    "cells_across": n, "across_m": round(cell if fixed else width / n, 1), "rows_outside": 0, "left_m": round(hl, 1), "right_m": round(hr, 1),
                })  # fmt: skip
                built = Corridor(piece["name"], shapely.LineString(piece["centre"]), np.asarray(offsets), along, snap, snap_nearest=False, edges=floor, cell=cell if fixed else 0.0, max_cells=max_cells)
                polygons.append(corridor_polygon(*corridor_cells(built)))
    return accepted, rejected, rules


def chain_parts(parts: list[dict], order_line: shapely.LineString) -> list[shapely.LineString]:
    """Chain the bank parts of one side of one wadi in order along its thalweg; a gap over GAP_CHAIN_M starts a new
    chain."""
    items = []
    for p in parts:
        c = np.asarray(p["line"].coords)
        s0 = order_line.project(shapely.Point(c[0]))
        s1 = order_line.project(shapely.Point(c[-1]))
        if s1 < s0:
            c = c[::-1]
            s0, s1 = s1, s0
        items.append((s0, s1, c))
    items.sort(key=lambda t: t[0])
    chains: list[list[np.ndarray]] = []
    current: list[np.ndarray] | None = None
    for _s0, _s1, c in items:
        if current is None:
            current = [c]
            continue
        gap = float(np.hypot(*(c[0] - current[-1][-1])))
        if gap <= GAP_CHAIN_M:
            current.append(c)
        else:
            chains.append(current)
            current = [c]
    if current:
        chains.append(current)
    out = []
    for ch in chains:
        xy = np.vstack(ch)
        keep = np.concatenate([[True], np.hypot(*np.diff(xy, axis=0).T) > 0.01])
        if keep.sum() >= 2:
            out.append(shapely.LineString(xy[keep]))
    return out


def pair_banks(
    banks: list[dict], thalwegs: dict[float, shapely.LineString], min_length: float = MIN_LENGTH_M
) -> list[BankPair]:
    """One pair per left chain: the right chain it faces longest; biggest wadis first."""
    by_area: dict[float, dict[str, list]] = defaultdict(lambda: {"left": [], "right": []})
    for b in banks:
        by_area[b["area_km2"]][b["side"]].append(b)
    pairs = []
    for area, sides in sorted(by_area.items(), key=lambda kv: -kv[0]):
        order = thalwegs.get(area)
        if order is None:
            order = max(sides["left"] + sides["right"], key=lambda b: b["line"].length)["line"]
        lefts = chain_parts(sides["left"], order) if sides["left"] else []
        rights = chain_parts(sides["right"], order) if sides["right"] else []
        used = set()
        for left in lefts:
            best = None
            for k, right in enumerate(rights):
                if k in used:
                    continue
                mid = midline(left, right)
                if mid is None or mid.length < min_length:
                    continue
                if best is None or mid.length > best[1].length:
                    best = (k, mid, right)
            if best is not None:
                used.add(best[0])
                pairs.append(BankPair(area, left, best[2], best[1]))
    return pairs


def fold_free_specs(
    spec: dict,
    along: float,
    smooth: int = 5,
    keep_out: shapely.Geometry | None = None,
    min_length: float = MIN_LENGTH_M,
    snap: dict[int, shapely.Geometry] | None = None,
    snap_nearest: bool = True,
    edges: dict[str, shapely.Geometry] | None = None,
    cell: float = 0.0,
) -> tuple[list[dict], list[str]]:
    """The spec split into the pieces whose corridor does not fold and stays off ``keep_out`` (the mesher's own
    geometry), each at least MIN_LENGTH_M; and what was cut, in words. A corridor with nothing to cut comes back
    as it is. ``snap`` gives the snapped rows' geometry when the spec's coordinates do not (several lines per row);
    ``edges`` and ``cell`` make the corridor ragged."""
    offsets = np.asarray(spec["offsets"], np.float64)
    if snap is None:
        snap = {row["row"]: shapely.LineString(row["coordinates"]) for row in spec["snap"]}
    todo, done, cut = [spec], [], []
    for _round in range(SPLIT_ROUNDS):
        again = []
        for s in todo:
            c = Corridor(s["name"], shapely.LineString(s["centre"]), offsets, along, snap, snap_nearest=snap_nearest, edges=edges, cell=cell, max_cells=int(s.get("max_cells", 12)))
            pieces, whole = fold_free_pieces(c, smooth, keep_out=keep_out)
            if whole:
                done.append(s)
                continue
            kept = 0.0
            for k, piece in enumerate(pieces):
                length = float(np.hypot(*np.diff(piece, axis=0).T).sum())
                if length < min_length:
                    continue
                kept += length
                again.append({**s, "name": f"{s['name']}_{k}" if len(pieces) > 1 else s["name"], "centre": [[float(x), float(y)] for x, y in piece]})
            cut.append(f"{s['name']}: folds or runs too close, {c.centre.length:.0f} m cut to {kept:.0f} m in {len(pieces)} piece(s)")
        todo = again
        if not todo:
            break
    else:
        cut.extend(f"{s['name']}: still folds after {SPLIT_ROUNDS} rounds, dropped" for s in todo)
        todo = []
    return done + todo, cut


def corridor_specs(
    pairs: list[BankPair],
    domain: shapely.Polygon,
    rule: CellRule = CellRule(),
    along: float = 20.0,
    min_length: float = MIN_LENGTH_M,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Corridor specifications for the job (``strips.corridors``), biggest wadis first, each cut clear of the accepted
    ones, the domain edge and its own folds; the pairs rejected or cut, with why; and per corridor the rule's
    numbers: the wadi width between its banks, the cells across and their size. The bank lines are the rows at
    half the width either side of the mid-line."""
    accepted: list[dict] = []
    polygons: list[shapely.Polygon] = []
    rejected: list[dict] = []
    rules: list[dict] = []
    edges: dict[float, tuple[shapely.Geometry, shapely.Geometry]] = {}
    for k, pr in enumerate(pairs):
        tag = f"pair {k} area {pr.area_km2:.2f} km2"
        width = pair_width(pr, along)
        offsets, cells, across = rule.layout(width)
        half = 0.5 * width
        left_row = int(np.argmin(np.abs(np.asarray(offsets) - half)))  # positive offsets lie left of travel
        right_row = int(np.argmin(np.abs(np.asarray(offsets) + half)))
        extent = round(offsets[-1], 1)
        if extent not in edges:
            edges[extent] = (
                domain.buffer(-(extent + along)),
                domain.envelope.buffer(4.0 * extent).difference(domain.buffer(-along)),  # a cell inside the edge
            )
        inside, outside = edges[extent]
        free = pr.mid.intersection(inside)
        if polygons:
            free = free.difference(shapely.unary_union([p.buffer(CLEAR_M) for p in polygons]))
        if free.is_empty:
            rejected.append({"tag": tag, "why": "inside an accepted corridor's clearance or outside the domain"})
            continue
        parts = list(free.geoms) if hasattr(free, "geoms") else [free]
        part = max(parts, key=lambda g: g.length)
        if part.length < min_length:
            rejected.append({"tag": tag, "why": f"free stretch {part.length:.0f} m under {min_length:.0f} m"})
            continue
        centre = np.asarray(part.coords)[:, :2]
        # which bank is to the left of the direction of travel: the left bank's side of the first stretch
        d = centre[min(5, len(centre) - 1)] - centre[0]
        p0 = np.asarray(pr.left.interpolate(pr.left.project(shapely.Point(centre[0]))).coords[0])
        on_left = d[0] * (p0[1] - centre[0][1]) - d[1] * (p0[0] - centre[0][0]) > 0.0
        left_line, right_line = (pr.left, pr.right) if on_left else (pr.right, pr.left)
        spec = {
            "name": f"pair{k}_{pr.area_km2:.1f}km2",
            "centre": [[float(x), float(y)] for x, y in centre],
            "offsets": offsets,
            "snap": [
                {"row": left_row, "coordinates": [[float(x), float(y)] for x, y in np.asarray(left_line.coords)[:, :2]]},
                {"row": right_row, "coordinates": [[float(x), float(y)] for x, y in np.asarray(right_line.coords)[:, :2]]},
            ],
        }
        keep_out = shapely.unary_union([outside, *[p.buffer(CLEAR_M) for p in polygons]])
        pieces, cut = fold_free_specs(spec, along, keep_out=keep_out, min_length=min_length)
        rejected.extend({"tag": tag, "why": words} for words in cut)
        snap = {row["row"]: shapely.LineString(row["coordinates"]) for row in spec["snap"]}
        for piece in pieces:
            accepted.append(piece)
            rules.append({
                "name": piece["name"], "area_km2": round(pr.area_km2, 2), "width_m": round(width, 1),
                "cells_across": cells, "across_m": round(across, 1), "rows_outside": rule.rows_outside,
            })  # fmt: skip
            built = Corridor(piece["name"], shapely.LineString(piece["centre"]), np.asarray(offsets), along, snap)
            polygons.append(corridor_polygon(*corridor_nodes(built)))
    return accepted, rejected, rules
