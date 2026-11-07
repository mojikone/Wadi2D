# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Corridors from suggested bank lines (W45, stage 7): the W44 recipe in the engine.

The Suggest breaklines layer gives each bank its side and the drainage area of the wadi it banks, and the thalwegs
layer the wadi lines. Per wadi, the parts of one side are chained along its thalweg; a left chain and the right chain
with the longest facing stretch make a pair; the pair's mid-line is the corridor's centre, its two banks the lines of
the rows at ``+-layer``. Each corridor is cut clear of the accepted ones and of the domain edge. What W44 measured on
Faydh 01: 39 pairs, 30 corridors along 29.3 km.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.strips.mesher import midline

BANK = "stream bank"
GAP_CHAIN_M = 30.0
"""Bank parts closer than this are one chain."""
MIN_LENGTH_M = 300.0
"""A corridor shorter than this is not built."""
CLEAR_M = 25.0
"""A corridor stays this far from an accepted one."""


@dataclass
class BankPair:
    area_km2: float
    left: shapely.LineString
    right: shapely.LineString
    mid: shapely.LineString


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


def pair_banks(banks: list[dict], thalwegs: dict[float, shapely.LineString]) -> list[BankPair]:
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
                if mid is None or mid.length < MIN_LENGTH_M:
                    continue
                if best is None or mid.length > best[1].length:
                    best = (k, mid, right)
            if best is not None:
                used.add(best[0])
                pairs.append(BankPair(area, left, best[2], best[1]))
    return pairs


def corridor_specs(
    pairs: list[BankPair], domain: shapely.Polygon, layer: float, rows_per_side: int = 3, along: float = 20.0
) -> tuple[list[dict], list[dict]]:
    """Corridor specifications for the job (``strips.corridors``), biggest wadis first, each cut clear of the accepted
    ones and the domain edge; and the pairs rejected, with why. The banks sit on the rows at +-layer."""
    half = rows_per_side * layer
    offsets = [float(v) for v in np.arange(-half, half + 1e-9, layer)]
    left_row = int(np.argmin(np.abs(np.asarray(offsets) + layer)))
    right_row = int(np.argmin(np.abs(np.asarray(offsets) - layer)))
    inside = domain.buffer(-(half + 5.0))
    accepted: list[dict] = []
    polygons: list[shapely.Polygon] = []
    rejected: list[dict] = []
    for k, pr in enumerate(pairs):
        tag = f"pair {k} area {pr.area_km2:.2f} km2"
        free = pr.mid.intersection(inside)
        if polygons:
            free = free.difference(shapely.unary_union([p.buffer(CLEAR_M) for p in polygons]))
        if free.is_empty:
            rejected.append({"tag": tag, "why": "inside an accepted corridor's clearance or outside the domain"})
            continue
        parts = list(free.geoms) if hasattr(free, "geoms") else [free]
        part = max(parts, key=lambda g: g.length)
        if part.length < MIN_LENGTH_M:
            rejected.append({"tag": tag, "why": f"free stretch {part.length:.0f} m under {MIN_LENGTH_M:.0f} m"})
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
                {"row": right_row, "coordinates": [[float(x), float(y)] for x, y in np.asarray(left_line.coords)[:, :2]]},
                {"row": left_row, "coordinates": [[float(x), float(y)] for x, y in np.asarray(right_line.coords)[:, :2]]},
            ],
        }
        accepted.append(spec)
        polygons.append(shapely.LineString(centre).buffer(half + 1.0))
    return accepted, rejected
