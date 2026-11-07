"""Step 2: aligned strips along the bank-line pairs with MeshKernel's advancing front.

W26's two banks of a reach sit about 20 m apart (one 10 m cell clear of the thalweg each side), so a strip per bank
would overlap its partner. Each PAIR becomes one corridor: the centre spline is the mid-line between the two banks,
the advancing front grows 3 layers of 10 m each side (aspect 0.5 x 20 m), so the grid lines at +-10 m fall near the
banks, and the +-20 and +-30 m lines are the two outer rows. The +-10 m nodes are then snapped onto the bank
polylines along their own cross lines (the one step MeshKernel does not offer), the outer nodes carried with them.

usage: python s02_strips.py [--no-snap] [--max-pairs N]
writes strips.npz (all accepted corridors as one mesh, with per-face corridor id and row index), strips.json,
strips_raw.npz (MeshKernel's unsnapped corridors), fig_02_*.png.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from matplotlib.collections import LineCollection
from meshkernel import CurvilinearParameters, MeshKernel, SplinesToCurvilinearParameters

from common import HERE, bank_lines, dam_axis, domain, thalwegs
from mkutil import centroid_orthogonality, face_geometry, geom_list, mesh_from_curvilinear, mesh_from_faces, mesh_summary, mk_orthogonality, shares, topology

SNAP = "--no-snap" not in sys.argv
MAX_PAIRS = int(sys.argv[sys.argv.index("--max-pairs") + 1]) if "--max-pairs" in sys.argv else 10**6
SMOOTH = int(sys.argv[sys.argv.index("--smooth") + 1]) if "--smooth" in sys.argv else 5  # mid-line smoothing window, 10 m samples
SUFFIX = sys.argv[sys.argv.index("--suffix") + 1] if "--suffix" in sys.argv else ""
MAX_RAW_MISS = 15.0  # m, a corridor whose raw +-10 m line misses a bank by more is mis-paired
MAX_SNAP_MISS = 5.0  # m, after the snap
LAYER = 10.0  # m, each row across
ROWS_PER_SIDE = 3  # channel half + 2 outer rows
WIDTH = 20.0  # m, cell length along the line
# cross splines at the two ends only: with cross splines every 100 m (all the same length) the front tapers the
# outer layers to 8.1, 6.6, 5.3 m and adds rows (probe_rows.py); with the ends alone every row is 10 m
CROSS_EVERY = 1e9
MIN_LENGTH = 300.0  # m, a corridor shorter than this is not built
GAP_CHAIN = 30.0  # m, bank parts closer than this are one chain
CLEAR = 25.0  # m, a new corridor stays this far from an accepted one

poly = domain()
banks = bank_lines()
thal = {t["area_km2"]: t["line"] for t in thalwegs()}
axis = dam_axis()


def chain_parts(parts: list[dict], order_line: shapely.LineString) -> list[shapely.LineString]:
    """Chain bank parts of one side of one reach in order of their station on the reach's thalweg; a gap over
    GAP_CHAIN starts a new chain."""
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
    chains = []
    cur = None
    for s0, s1, c in items:
        if cur is None:
            cur = [c]
            continue
        gap = np.hypot(*(c[0] - cur[-1][-1]))
        if gap <= GAP_CHAIN:
            cur.append(c)
        else:
            chains.append(cur)
            cur = [c]
    if cur:
        chains.append(cur)
    out = []
    for ch in chains:
        pts = [ch[0]]
        for c in ch[1:]:
            pts.append(c)
        xy = np.vstack(pts)
        # drop repeated points
        keep = np.concatenate([[True], np.hypot(*np.diff(xy, axis=0).T) > 0.01])
        out.append(shapely.LineString(xy[keep]))
    return out


def midline(L: shapely.LineString, R: shapely.LineString, step: float = 10.0) -> shapely.LineString | None:
    """The line midway between two facing banks over the length where they face each other."""
    st = np.arange(step, L.length - step, step)
    pts = []
    for s in st:
        p = L.interpolate(s)
        sr = R.project(p)
        if sr <= step or sr >= R.length - step:
            continue
        q = R.interpolate(sr)
        if p.distance(q) > 120.0:
            continue
        pts.append([(p.x + q.x) / 2, (p.y + q.y) / 2])
    if len(pts) < 5:
        return None
    pts = np.asarray(pts)
    # a light smoothing (SMOOTH x 10 m window) then resample every WIDTH
    k = SMOOTH
    sm = np.copy(pts)
    for i in range(len(pts)):
        a, b = max(0, i - k // 2), min(len(pts), i + k // 2 + 1)
        sm[i] = pts[a:b].mean(axis=0)
    ln = shapely.LineString(sm)
    if ln.length < MIN_LENGTH:
        return None
    n = max(int(round(ln.length / WIDTH)), 2)
    res = np.array([[q.x, q.y] for q in (ln.interpolate(t, normalized=True) for t in np.linspace(0, 1, n + 1))])
    return shapely.LineString(res)


def cross_splines(centre: shapely.LineString, half: float) -> list[np.ndarray]:
    out = []
    stations = np.arange(0.0, centre.length, CROSS_EVERY).tolist()
    if centre.length - stations[-1] > 0.5 * min(CROSS_EVERY, centre.length):
        stations.append(centre.length)
    else:
        stations[-1] = centre.length
    for s in stations:
        p = centre.interpolate(s)
        p1 = centre.interpolate(max(s - 1.0, 0.0))
        p2 = centre.interpolate(min(s + 1.0, centre.length))
        t = np.array([p2.x - p1.x, p2.y - p1.y])
        t /= max(np.hypot(*t), 1e-9)
        nrm = np.array([-t[1], t[0]])
        out.append(np.array([[p.x, p.y] - half * nrm, [p.x, p.y] + half * nrm]))
    return out


def grow(centre: shapely.LineString, curvature: int = 1) -> tuple[np.ndarray, np.ndarray, float]:
    """MeshKernel's advancing front from the centre spline; returns the (n along, m across) node arrays."""
    # the cross splines are exactly ROWS_PER_SIDE layers long: half a metre more and the front adds a fourth,
    # sliver-thin layer on each side (seen on every pair of the first run)
    half = ROWS_PER_SIDE * LAYER
    lines = [np.asarray(centre.coords)] + cross_splines(centre, half)
    mk = MeshKernel()
    t0 = time.perf_counter()
    mk.curvilinear_compute_orthogonal_from_splines(
        geom_list(lines),
        CurvilinearParameters(m_refinement=4000, n_refinement=40),
        SplinesToCurvilinearParameters(
            aspect_ratio=LAYER / WIDTH,
            aspect_ratio_grow_factor=1.0,
            average_width=WIDTH,
            curvature_adapted_grid_spacing=curvature,
            grow_grid_outside=False,
            maximum_num_faces_in_uniform_part=ROWS_PER_SIDE,
            check_front_collisions=True,
            remove_skinny_triangles=True,
        ),
    )
    dt = time.perf_counter() - t0
    g = mk.curvilineargrid_get()
    x = np.asarray(g.node_x).reshape(g.num_n, g.num_m)
    y = np.asarray(g.node_y).reshape(g.num_n, g.num_m)
    valid = np.isfinite(x) & (x > -900)
    return np.where(valid, x, np.nan), np.where(valid, y, np.nan), dt


def orient(x: np.ndarray, y: np.ndarray, L: shapely.LineString) -> tuple[np.ndarray, np.ndarray]:
    """Put the left bank on the low m side: the m=0 line should be nearer L than the m=-1 line."""
    d0 = np.nanmedian([L.distance(shapely.Point(p)) for p in np.column_stack([x[:, 0], y[:, 0]]) if np.isfinite(p[0])])
    d1 = np.nanmedian([L.distance(shapely.Point(p)) for p in np.column_stack([x[:, -1], y[:, -1]]) if np.isfinite(p[0])])
    if d1 < d0:
        return x[:, ::-1].copy(), y[:, ::-1].copy()
    return x, y


def snap(x: np.ndarray, y: np.ndarray, L: shapely.LineString, R: shapely.LineString) -> tuple[np.ndarray, np.ndarray, dict]:
    """Move the +-LAYER grid lines onto the banks along each station's cross line; carry the outer rows with them."""
    n, mm = x.shape
    c = mm // 2  # the centre line
    x2, y2 = x.copy(), y.copy()
    moves = {"left": [], "right": [], "left_missed": 0, "right_missed": 0}
    for i in range(n):
        if not np.isfinite(x[i]).all():
            continue
        p0 = np.array([x[i, c], y[i, c]])
        for side, line, j_bank, outer in (("left", L, c - 1, range(c - 1, -1, -1)), ("right", R, c + 1, range(c + 1, mm))):
            pb = np.array([x[i, j_bank], y[i, j_bank]])
            d = pb - p0
            dn = np.hypot(*d)
            if dn < 1e-9:
                continue
            u = d / dn
            # the cross line from the centre node, 0 to 2.5 layers out
            seg = shapely.LineString([p0 + 0.05 * u, p0 + 2.5 * LAYER * u])
            hit = seg.intersection(line)
            if hit.is_empty:
                moves[side + "_missed"] += 1
                q = np.asarray(line.interpolate(line.project(shapely.Point(pb))).coords[0])
            else:
                pts = shapely.get_coordinates(hit)
                # the crossing nearest the raw bank node
                q = pts[np.argmin(np.hypot(*(pts - pb).T))]
            shift = q - pb
            moves[side].append(float(np.dot(shift, u)))
            for j in outer:
                x2[i, j] = x[i, j] + shift[0]
                y2[i, j] = y[i, j] + shift[1]
    for side in ("left", "right"):
        v = np.abs(np.asarray(moves[side]))
        moves[side] = {"n": int(len(v)), "median": float(np.median(v)) if len(v) else None, "p90": float(np.percentile(v, 90)) if len(v) else None, "max": float(v.max()) if len(v) else None}
    return x2, y2, moves


def bank_edge_distances(x: np.ndarray, y: np.ndarray, L: shapely.LineString, R: shapely.LineString) -> dict:
    """Distance of every edge on the +-LAYER grid lines (the breakline faces) from its bank polyline: the edge
    midpoint and both ends."""
    c = x.shape[1] // 2
    out = {}
    for side, line, j in (("left", L, c - 1), ("right", R, c + 1)):
        px, py = x[:, j], y[:, j]
        ok = np.isfinite(px)
        pts = np.column_stack([px[ok], py[ok]])
        mids = 0.5 * (pts[1:] + pts[:-1])
        d_mid = np.array([line.distance(shapely.Point(p)) for p in mids])
        d_node = np.array([line.distance(shapely.Point(p)) for p in pts])
        out[side] = {
            "edges": int(len(mids)),
            "mid_median": float(np.median(d_mid)),
            "mid_p90": float(np.percentile(d_mid, 90)),
            "mid_max": float(d_mid.max()),
            "node_median": float(np.median(d_node)),
            "node_p90": float(np.percentile(d_node, 90)),
            "node_max": float(d_node.max()),
        }
    return out


def strip_polygon(mesh) -> shapely.Polygon:
    mk = MeshKernel()
    mk.mesh2d_set(mesh)
    b = mk.mesh2d_get_mesh_boundaries_as_polygons()
    bx = np.asarray(b.x_coordinates)
    by = np.asarray(b.y_coordinates)
    cut = np.where(bx <= -998)[0]
    start = 0
    rings = []
    for e in list(cut) + [len(bx)]:
        if e > start + 2:
            rings.append(shapely.Polygon(np.column_stack([bx[start:e], by[start:e]])))
        start = e + 1
    return max(rings, key=lambda r: r.area)


# ---- pair the banks: one reach per area_km2 label, left and right chains ordered along its thalweg ----
by_area = defaultdict(lambda: {"left": [], "right": []})
for b in banks:
    by_area[b["area_km2"]][b["side"]].append(b)
pairs = []
singles = 0
for area, sides in sorted(by_area.items(), key=lambda kv: -kv[0]):
    order_line = thal.get(area)
    if order_line is None:
        # no thalweg of that area: order along the longest bank part
        order_line = max(sides["left"] + sides["right"], key=lambda b: b["line"].length)["line"]
    Ls = chain_parts(sides["left"], order_line) if sides["left"] else []
    Rs = chain_parts(sides["right"], order_line) if sides["right"] else []
    if not Ls or not Rs:
        singles += len(Ls) + len(Rs)
        continue
    used_R = set()
    for L in Ls:
        best = None
        for k, R in enumerate(Rs):
            if k in used_R:
                continue
            mid = midline(L, R)
            if mid is None:
                continue
            if best is None or mid.length > best[1].length:
                best = (k, mid, R)
        if best is None:
            singles += 1
            continue
        used_R.add(best[0])
        pairs.append({"area_km2": area, "L": L, "R": best[2], "mid": best[1]})
    singles += len(Rs) - len(used_R)
print(f"reaches {len(by_area)}, bank pairs with a facing stretch >= {MIN_LENGTH:.0f} m: {len(pairs)}, unpaired chains: {singles}")

# ---- build the corridors in order of drainage area, each kept clear of the accepted ones ----
accepted = []
rejected = []
raw_meshes = []
snapped_meshes = []
timing = {"grow_s": 0.0, "snap_s": 0.0}
for k, pr in enumerate(pairs[:MAX_PAIRS]):
    mid = pr["mid"]
    tag = f"pair {k} area {pr['area_km2']:.2f} km2"
    # keep clear of accepted corridors and of the domain edge
    blocked = shapely.unary_union([a["polygon"].buffer(CLEAR) for a in accepted]) if accepted else None
    free = mid.difference(blocked) if blocked is not None else mid
    free = free.intersection(poly.buffer(-ROWS_PER_SIDE * LAYER - 5.0))
    if free.is_empty:
        rejected.append({"tag": tag, "why": "entirely inside an accepted corridor's clearance or outside the domain"})
        continue
    parts = list(free.geoms) if hasattr(free, "geoms") else [free]
    part = max(parts, key=lambda g: g.length)
    if part.length < MIN_LENGTH:
        rejected.append({"tag": tag, "why": f"free stretch {part.length:.0f} m under {MIN_LENGTH:.0f} m"})
        continue
    if part.length < mid.length - 1.0:
        n = max(int(round(part.length / WIDTH)), 2)
        part = shapely.LineString([[q.x, q.y] for q in (part.interpolate(t, normalized=True) for t in np.linspace(0, 1, n + 1))])
    try:
        x, y, dt = grow(part)
    except Exception as e:
        rejected.append({"tag": tag, "why": f"MeshKernel refused: {e}"})
        continue
    timing["grow_s"] += dt
    # a thin extra layer at the outside (the front overshoots by the spline's sampling) is dropped
    while x.shape[1] > 2 * ROWS_PER_SIDE + 1:
        h0 = np.nanmedian(np.hypot(x[:, 1] - x[:, 0], y[:, 1] - y[:, 0]))
        h1 = np.nanmedian(np.hypot(x[:, -1] - x[:, -2], y[:, -1] - y[:, -2]))
        if min(h0, h1) > 3.0:
            break
        x, y = (x[:, 1:], y[:, 1:]) if h0 <= h1 else (x[:, :-1], y[:, :-1])
    if x.shape[1] != 2 * ROWS_PER_SIDE + 1:
        rejected.append({"tag": tag, "why": f"grid has {x.shape[1] - 1} rows across, not {2 * ROWS_PER_SIDE}"})
        continue
    x, y = orient(x, y, pr["L"])
    raw_mesh, _ = mesh_from_curvilinear(x, y)
    area_raw, _, _ = face_geometry(raw_mesh)
    if (area_raw <= 1.0).any():
        rejected.append({"tag": tag, "why": f"{int((area_raw <= 1.0).sum())} folded or empty cells in the raw grid"})
        continue
    d_raw = bank_edge_distances(x, y, pr["L"], pr["R"])
    if max(d_raw["left"]["mid_max"], d_raw["right"]["mid_max"]) > MAX_RAW_MISS:
        rejected.append({"tag": tag, "why": f"raw +-10 m line misses a bank by {max(d_raw['left']['mid_max'], d_raw['right']['mid_max']):.1f} m: mis-paired banks"})
        continue
    t0 = time.perf_counter()
    if SNAP:
        xs, ys, moves = snap(x, y, pr["L"], pr["R"])
    else:
        xs, ys, moves = x, y, {}
    timing["snap_s"] += time.perf_counter() - t0
    mesh, idx = mesh_from_curvilinear(xs, ys)
    area_s, _, _ = face_geometry(mesh)
    if (area_s <= 1.0).any():
        rejected.append({"tag": tag, "why": f"{int((area_s <= 1.0).sum())} folded or empty cells after the snap"})
        continue
    pg = strip_polygon(mesh)
    if not pg.is_valid or shapely.get_num_geometries(pg) != 1:
        rejected.append({"tag": tag, "why": "strip boundary is not a simple polygon"})
        continue
    if accepted and pg.intersects(shapely.unary_union([a["polygon"] for a in accepted])):
        rejected.append({"tag": tag, "why": "strip overlaps an accepted corridor after growth"})
        continue
    d_snap = bank_edge_distances(xs, ys, pr["L"], pr["R"])
    if max(d_snap["left"]["mid_max"], d_snap["right"]["mid_max"]) > MAX_SNAP_MISS:
        rejected.append({"tag": tag, "why": f"a bank edge still {max(d_snap['left']['mid_max'], d_snap['right']['mid_max']):.1f} m off after the snap"})
        continue
    co, off, interior = centroid_orthogonality(mesh)
    mk = MeshKernel()
    mk.mesh2d_set(mesh)
    o_mk = mk_orthogonality(mk)
    mk_raw = MeshKernel()
    mk_raw.mesh2d_set(raw_mesh)
    o_mk_raw = mk_orthogonality(mk_raw)
    n_along = int(np.isfinite(x[:, x.shape[1] // 2]).sum()) - 1
    accepted.append(
        {
            "k": k,
            "area_km2": pr["area_km2"],
            "length_m": float(part.length),
            "trimmed_from_m": float(mid.length),
            "cells": int(len(area_s)),
            "cells_along": n_along,
            "rows": int(x.shape[1] - 1),
            "grow_s": dt,
            "bank_distance_raw": d_raw,
            "bank_distance_snapped": d_snap,
            "snap_moves_m": moves,
            "orthogonality_mk_raw": shares(o_mk_raw),
            "orthogonality_mk_snapped": shares(o_mk),
            "orthogonality_centroid_snapped": shares(co),
            "crosses_dam_axis": bool(pg.intersects(axis)),
            "polygon": pg,
            "x": xs,
            "y": ys,
            "x_raw": x,
            "y_raw": y,
            "L": pr["L"],
            "R": pr["R"],
        }
    )
    print(f"{tag}: {part.length:.0f} m, {len(area_s)} cells, grow {dt*1e3:.0f} ms; bank edge mid distance raw L/R p90 "
          f"{d_raw['left']['mid_p90']:.2f}/{d_raw['right']['mid_p90']:.2f} max {d_raw['left']['mid_max']:.2f}/{d_raw['right']['mid_max']:.2f}; "
          f"snapped p90 {d_snap['left']['mid_p90']:.2f}/{d_snap['right']['mid_p90']:.2f} max {d_snap['left']['mid_max']:.2f}/{d_snap['right']['mid_max']:.2f}; "
          f"MK ortho raw p90 {shares(o_mk_raw)['p90']:.4f} snapped p90 {shares(o_mk)['p90']:.4f} max {shares(o_mk)['max']:.4f}")

print(f"accepted {len(accepted)} corridors, rejected {len(rejected)}")
for r in rejected[:40]:
    print("  rejected", r)

# ---- one mesh of all corridors (no shared nodes between corridors by construction) ----
node_xy = []
faces = []
face_corridor = []
face_row = []
on_bank_edges = []  # (node a, node b, corridor, side)
offset = 0
for a in accepted:
    xs, ys = a["x"], a["y"]
    valid = np.isfinite(xs)
    idx = np.full(xs.shape, -1, np.int64)
    idx[valid] = offset + np.arange(valid.sum())
    node_xy.append(np.column_stack([xs[valid], ys[valid]]))
    n, mm = xs.shape
    c = mm // 2
    for i in range(n - 1):
        for j in range(mm - 1):
            q = [idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]]
            if min(q) < 0:
                continue
            faces.append(np.array(q))
            face_corridor.append(a["k"])
            face_row.append(j - c)  # -3..2: row -1 and 0 are the channel halves (banks at the -1/0 and 0/1 lines)
    for side, j in (("left", c - 1), ("right", c + 1)):
        for i in range(n - 1):
            if idx[i, j] >= 0 and idx[i + 1, j] >= 0:
                on_bank_edges.append((idx[i, j], idx[i + 1, j], a["k"], 0 if side == "left" else 1))
    offset += int(valid.sum())
node_xy = np.vstack(node_xy)
mesh_all = mesh_from_faces(node_xy, faces)
# orientation to counter-clockwise
area_all, _, _ = face_geometry(mesh_all)
tbl = np.asarray(faces)
tbl[area_all < 0] = tbl[area_all < 0][:, ::-1]
mesh_all = mesh_from_faces(node_xy, list(tbl))
summary = mesh_summary(mesh_all)
mk = MeshKernel()
mk.mesh2d_set(mesh_all)
t0 = time.perf_counter()
o_all = mk_orthogonality(mk)
timing["orthogonality_s"] = time.perf_counter() - t0
co_all, off_all, interior_all = centroid_orthogonality(mesh_all)
print("all strips:", summary, "MK orthogonality", shares(o_all))
print("   centroid orthogonality", shares(co_all))
en, ef, fe = topology(mesh_all)
np.savez_compressed(
    HERE / f"strips{SUFFIX}.npz",
    node_x=node_xy[:, 0],
    node_y=node_xy[:, 1],
    face_nodes=tbl,
    nodes_per_face=np.full(len(tbl), 4, np.int64),
    edge_nodes=en,
    edge_faces=ef,
    face_edges=fe,
    face_corridor=np.asarray(face_corridor, np.int64),
    face_row=np.asarray(face_row, np.int64),
    bank_edges=np.asarray(on_bank_edges, np.int64).reshape(-1, 4),
)
# the raw (unsnapped) corridors too, for the comparison
raw_xy = []
raw_faces = []
offset = 0
for a in accepted:
    xs, ys = a["x_raw"], a["y_raw"]
    valid = np.isfinite(xs)
    idx = np.full(xs.shape, -1, np.int64)
    idx[valid] = offset + np.arange(valid.sum())
    raw_xy.append(np.column_stack([xs[valid], ys[valid]]))
    n, mm = xs.shape
    for i in range(n - 1):
        for j in range(mm - 1):
            q = [idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]]
            if min(q) >= 0:
                raw_faces.append(q)
    offset += int(valid.sum())
raw_xy = np.vstack(raw_xy)
raw_tbl = np.asarray(raw_faces)
m_raw = mesh_from_faces(raw_xy, list(raw_tbl))
a_raw, _, _ = face_geometry(m_raw)
raw_tbl[a_raw < 0] = raw_tbl[a_raw < 0][:, ::-1]
np.savez_compressed(HERE / f"strips_raw{SUFFIX}.npz", node_x=raw_xy[:, 0], node_y=raw_xy[:, 1], face_nodes=raw_tbl, nodes_per_face=np.full(len(raw_tbl), 4, np.int64))

out = {
    "settings": {"smooth_window": SMOOTH, "layer_m": LAYER, "rows_per_side": ROWS_PER_SIDE, "width_m": WIDTH, "cross_every_m": CROSS_EVERY, "min_length_m": MIN_LENGTH, "clear_m": CLEAR, "snap": SNAP},
    "reaches": len(by_area),
    "pairs_found": len(pairs),
    "unpaired_chains": singles,
    "accepted": [{k: v for k, v in a.items() if k not in ("polygon", "x", "y", "x_raw", "y_raw", "L", "R")} for a in accepted],
    "rejected": rejected,
    "all_strips": {"summary": summary, "orthogonality_mk": shares(o_all), "orthogonality_centroid": shares(co_all), "offset_centroid": shares(off_all)},
    "timing_s": timing,
}
json.dump(out, open(HERE / f"strips{SUFFIX}.json", "w"), indent=1, default=float)
# the corridor polygons for the join step
import pickle

pickle.dump([{"k": a["k"], "polygon": a["polygon"], "L": a["L"], "R": a["R"], "area_km2": a["area_km2"]} for a in accepted], open(HERE / f"strips_polygons{SUFFIX}.pkl", "wb"))


# ---- figures ----
def draw_mesh(ax, m, color="k", lw=0.4):
    x = np.asarray(m.node_x)
    y = np.asarray(m.node_y)
    e = np.asarray(m.edge_nodes).reshape(-1, 2)
    segs = np.stack([np.column_stack([x[e[:, 0]], y[e[:, 0]]]), np.column_stack([x[e[:, 1]], y[e[:, 1]]])], axis=1)
    ax.add_collection(LineCollection(segs, colors=color, linewidths=lw))


fig, ax = plt.subplots(figsize=(16, 12))
ax.plot(*poly.exterior.xy, color="0.5", lw=0.6)
draw_mesh(ax, mesh_all, color="k", lw=0.3)
for a in accepted:
    ax.plot(*a["L"].xy, color="r", lw=0.5)
    ax.plot(*a["R"].xy, color="b", lw=0.5)
ax.plot(*axis.xy, color="m", lw=2)
ax.autoscale()
ax.set_aspect("equal")
ax.set_title(f"{len(accepted)} corridors, {summary['faces']:,} cells; red/blue: W26 bank lines, magenta: dam axis")
fig.tight_layout()
fig.savefig(HERE / f"fig_02_strips_all{SUFFIX}.png", dpi=130)

# zooms at the dam axis: raw vs snapped
main = accepted[0]
c = axis.centroid
for name, xx, yy in (("raw", main["x_raw"], main["y_raw"]), ("snapped", main["x"], main["y"])):
    fig, axs = plt.subplots(1, 2, figsize=(18, 9))
    m_, _ = mesh_from_curvilinear(xx, yy)
    for ax, (cx, cy, w) in zip(axs, ((c.x, c.y, 150), (main["x"][len(main["x"]) // 3, 3], main["y"][len(main["y"]) // 3, 3], 150))):
        draw_mesh(ax, m_, color="k", lw=0.6)
        ax.plot(*main["L"].xy, color="r", lw=1.0, label="W26 left bank")
        ax.plot(*main["R"].xy, color="b", lw=1.0, label="W26 right bank")
        ax.plot(*axis.xy, color="m", lw=1.5, label="dam axis")
        ax.set_xlim(cx - w, cx + w)
        ax.set_ylim(cy - w, cy + w)
        ax.set_aspect("equal")
    axs[0].legend(loc="upper left", fontsize=8)
    axs[0].set_title(f"main corridor, {name}: 300 m window at the dam axis")
    axs[1].set_title(f"main corridor, {name}: 300 m window a third of the way along")
    fig.tight_layout()
    fig.savefig(HERE / f"fig_02_main_{name}{SUFFIX}.png", dpi=130)

# histogram of the orthogonality, raw vs snapped, all strips
mk_r = MeshKernel()
mk_r.mesh2d_set(m_raw)
o_raw_all = mk_orthogonality(mk_r)
fig, ax = plt.subplots(figsize=(9, 5))
bins = np.concatenate([[0], np.logspace(-5, 0, 41)])
ax.hist(o_raw_all[np.isfinite(o_raw_all)], bins=bins, histtype="step", label=f"MeshKernel raw, p90 {shares(o_raw_all)['p90']:.4f}")
ax.hist(o_all[np.isfinite(o_all)], bins=bins, histtype="step", label=f"snapped, p90 {shares(o_all)['p90']:.4f}")
ax.hist(co_all[np.isfinite(co_all)], bins=bins, histtype="step", label=f"snapped, centroid measure, p90 {shares(co_all)['p90']:.4f}")
ax.set_xscale("symlog", linthresh=1e-4)
ax.set_xlabel("orthogonality (|cos| between edge and centre line; 0 is orthogonal)")
ax.set_ylabel("interior edges")
for v in (0.01, 0.02, 0.05):
    ax.axvline(v, color="0.6", lw=0.6, ls="--")
ax.legend(fontsize=8)
ax.set_title("strips alone: orthogonality of interior edges")
fig.tight_layout()
fig.savefig(HERE / f"fig_02_strips_orthogonality{SUFFIX}.png", dpi=130)
print("timing", timing)
