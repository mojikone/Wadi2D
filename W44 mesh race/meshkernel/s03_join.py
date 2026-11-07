"""Step 3: join the corridors into the lattice.

The lattice cells that intersect a corridor are removed; the gap between the staircase hole and the corridor's
outer boundary is triangulated on the existing nodes only (MeshKernel's mesh2d_make_triangular_mesh_from_polygon,
which on a polygon adds no interior points; shapely's constrained Delaunay as the check), so every triangle shares
its edges with a lattice cell, a corridor cell or another triangle and nothing hangs. A second variant merges
triangle pairs into convex quads where that is possible.

mesh2d_connect_meshes was tried first (probe_join.py): it adds the strip's nodes and none of its faces when the
strip does not share the hole's boundary, so it is not usable here.

usage: python s03_join.py
reads lattice.npz, strips.npz, strips_polygons.pkl; writes joined_tri.npz, joined_quad.npz, join.json, fig_03_*.png
"""

from __future__ import annotations

import json
import pickle
import time
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from matplotlib.collections import LineCollection, PolyCollection
from meshkernel import MeshKernel
from scipy.spatial import cKDTree

from common import DX, HERE, dam_axis, domain
from mkutil import centroid_orthogonality, face_geometry, faces_table, mesh_from_faces, mesh_summary, mk_orthogonality, polygon_geom, shares, topology

import sys

GAP_BUFFER = float(sys.argv[sys.argv.index("--gap-buffer") + 1]) if "--gap-buffer" in sys.argv else 0.0
SUFFIX = sys.argv[sys.argv.index("--suffix") + 1] if "--suffix" in sys.argv else ""
timing = {}
lat = np.load(HERE / "lattice.npz")
stp = np.load(HERE / "strips.npz")
corridors = pickle.load(open(HERE / "strips_polygons.pkl", "rb"))
axis = dam_axis()
poly = domain()

# ---- lattice cells to remove ----
t0 = time.perf_counter()
lx, ly = lat["node_x"], lat["node_y"]
lfaces = lat["face_nodes"]  # (n, 4)
cx = lx[lfaces].mean(axis=1)
cy = ly[lfaces].mean(axis=1)
boxes = shapely.box(cx - DX / 2, cy - DX / 2, cx + DX / 2, cy + DX / 2)
tree = shapely.STRtree(boxes)
corr_polys = [c["polygon"] for c in corridors]
# the same polygon removes the cells and cuts the gap: a corridor shrunk for the removal left a cell it overlapped
# by 7 mm in place, and the gap then had a vertex that was no node
# with GAP_BUFFER > 0 the cells within that distance of a corridor go too, so the gap is never thinner than it
hit = tree.query([p.buffer(GAP_BUFFER) if GAP_BUFFER > 0 else p for p in corr_polys], predicate="intersects")  # (2, k): corridor index, box index
removed = np.zeros(len(boxes), bool)
removed[hit[1]] = True
cell_corridor = np.full(len(boxes), -1, np.int64)
cell_corridor[hit[1]] = np.asarray([corridors[i]["k"] for i in hit[0]])
timing["remove_cells_s"] = time.perf_counter() - t0
print(f"lattice cells {len(boxes):,}, removed {removed.sum():,} under {len(corridors)} corridors ({timing['remove_cells_s']:.1f} s)")

# ---- the gap polygons ----
t0 = time.perf_counter()
hole = shapely.unary_union(boxes[removed])
gap = hole.difference(shapely.unary_union(corr_polys))
gaps = list(gap.geoms) if hasattr(gap, "geoms") else [gap]
timing["gap_polygons_s"] = time.perf_counter() - t0
print(f"gap: {len(gaps)} polygons, {sum(len(g.interiors) for g in gaps)} holes, area {gap.area:.0f} m2 = {gap.area / DX**2:.1f} lattice cells ({timing['gap_polygons_s']:.1f} s)")

# ---- the global node table: kept lattice nodes, then the strip nodes ----
kept_faces = lfaces[~removed]
used = np.zeros(len(lx), bool)
used[kept_faces.ravel()] = True
# where the hole reaches the domain edge, its boundary nodes belong to no kept face: keep every node of a removed
# face that lies on the hole's boundary too
cand = np.unique(lfaces[removed].ravel())
cand = cand[~used[cand]]
if len(cand):
    on_edge = shapely.dwithin(shapely.points(np.column_stack([lx[cand], ly[cand]])), hole.boundary, 1e-6)
    used[cand[on_edge]] = True
lat_map = np.full(len(lx), -1, np.int64)
lat_map[used] = np.arange(used.sum())
n_lat = int(used.sum())
node_xy = np.vstack([np.column_stack([lx[used], ly[used]]), np.column_stack([stp["node_x"], stp["node_y"]])])
n_strip = len(stp["node_x"])
faces = [row for row in lat_map[kept_faces]]
face_kind = [0] * len(faces)
face_corr = [-1] * len(faces)
face_row = [99] * len(faces)
sfaces = stp["face_nodes"] + n_lat
faces += [row for row in sfaces]
face_kind += [1] * len(sfaces)
face_corr += stp["face_corridor"].tolist()
face_row += stp["face_row"].tolist()
key_tree = cKDTree(node_xy)


worst_lookup = [0.0]


def node_id(p: np.ndarray) -> int:
    d, i = key_tree.query(p)
    worst_lookup[0] = max(worst_lookup[0], float(d))
    if d > 1e-3:
        raise KeyError(f"no node at {p} (nearest {d:.4f} m away)")
    return int(i)


def conform_ring(coords: np.ndarray) -> np.ndarray:
    """Insert every mesh node that lies on a ring segment, so the triangulation shares the mesh's edges."""
    out = []
    for p, q in zip(coords[:-1], coords[1:]):
        out.append(p)
        seg = q - p
        L = np.hypot(*seg)
        if L < 1e-9:
            continue
        cand = key_tree.query_ball_point((p + q) / 2, r=L / 2 + 0.01)
        if not cand:
            continue
        c = node_xy[cand]
        t = ((c - p) @ seg) / L**2
        off = np.abs((c[:, 0] - p[0]) * seg[1] - (c[:, 1] - p[1]) * seg[0]) / L
        sel = (off < 1e-4) & (t > 1e-6) & (t < 1 - 1e-6)
        order = np.argsort(t[sel])
        out.extend(c[sel][order])
    out.append(coords[-1])
    return np.asarray(out)


def conform_polygon(g: shapely.Polygon) -> shapely.Polygon:
    return shapely.Polygon(conform_ring(np.asarray(g.exterior.coords)), [conform_ring(np.asarray(r.coords)) for r in g.interiors])


# ---- triangulate each gap on its boundary nodes ----
t0 = time.perf_counter()
tri_rings = []
tri_gap = []
mk_fail = 0
cdt_used = 0
mk_errors = []
for gi, g in enumerate(gaps):
    gc = conform_polygon(g)
    tris = None
    try:
        mk = MeshKernel()
        mk.mesh2d_make_triangular_mesh_from_polygon(polygon_geom(gc))
        tm = mk.mesh2d_get()
        tbl, npf = faces_table(tm)
        if (npf != 3).any():
            raise RuntimeError("non-triangles")
        tx, ty = np.asarray(tm.node_x), np.asarray(tm.node_y)
        if len(tx) != len(gc.exterior.coords) - 1 + sum(len(r.coords) - 1 for r in gc.interiors):
            n_ring = len(gc.exterior.coords) - 1 + sum(len(r.coords) - 1 for r in gc.interiors)
            raise RuntimeError(f"MeshKernel changed the node count: {len(tx)} nodes against the ring's {n_ring}")
        tris = [np.column_stack([tx[r], ty[r]]) for r in tbl]
    except Exception as e:
        mk_fail += 1
        mk_errors.append(str(e)[:300])
        tris = None
    if tris is None:
        cdt = shapely.constrained_delaunay_triangles(gc)
        tris = [np.asarray(t.exterior.coords)[:3] for t in cdt.geoms]
        cdt_used += 1
    for t in tris:
        ids = [node_id(p) for p in t]
        # counter-clockwise
        a2 = (t[1, 0] - t[0, 0]) * (t[2, 1] - t[0, 1]) - (t[2, 0] - t[0, 0]) * (t[1, 1] - t[0, 1])
        if a2 < 0:
            ids = ids[::-1]
        tri_rings.append(np.asarray(ids))
        tri_gap.append(gi)
timing["triangulate_s"] = time.perf_counter() - t0
print(f"triangles {len(tri_rings):,} in {timing['triangulate_s']:.1f} s; MeshKernel triangulation failed on {mk_fail} gap polygons, shapely CDT used on {cdt_used}; worst node lookup {worst_lookup[0]:.2e} m")
from collections import Counter as _C
for msg, n in _C(mk_errors).most_common(5):
    print(f"   MeshKernel triangulation error x{n}: {msg}")

# triangle quality
tri = np.asarray(tri_rings)
P = node_xy[tri]  # (n, 3, 2)
e = np.roll(P, -1, axis=1) - P
l = np.hypot(e[..., 0], e[..., 1])
angles = np.zeros((len(tri), 3))
for i in range(3):
    u = -e[:, i - 1]
    v = e[:, i]
    angles[:, i] = np.degrees(np.arccos(np.clip((u * v).sum(axis=1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1)), -1, 1)))
min_ang = angles.min(axis=1)
max_ang = angles.max(axis=1)
tri_area = 0.5 * np.abs(e[:, 0, 0] * e[:, 1, 1] - e[:, 1, 0] * e[:, 0, 1])
tri_stats = {
    "count": int(len(tri)),
    "min_angle_median": float(np.median(min_ang)),
    "min_angle_p10": float(np.percentile(min_ang, 10)),
    "min_angle_min": float(min_ang.min()),
    "slivers_under_10deg": int((min_ang < 10).sum()),
    "slivers_under_5deg": int((min_ang < 5).sum()),
    "obtuse_over_120deg": int((max_ang > 120).sum()),
    "area_median": float(np.median(tri_area)),
    "area_min": float(tri_area.min()),
    "area_max": float(tri_area.max()),
}
print("triangles:", tri_stats)

# ---- variant A: triangles ----
faces_tri = faces + [r for r in tri_rings]
kind_tri = face_kind + [2] * len(tri_rings)
corr_tri = face_corr + [-1] * len(tri_rings)
row_tri = face_row + [99] * len(tri_rings)
t0 = time.perf_counter()
mesh_tri = mesh_from_faces(node_xy, faces_tri)
en_t, ef_t, fe_t = topology(mesh_tri)
timing["topology_tri_s"] = time.perf_counter() - t0
summary_tri = mesh_summary(mesh_tri)
print("joined (triangles):", summary_tri)


def mk_measure(mesh, en_mine):
    """MeshKernel's orthogonality on a mesh set from our arrays, mapped back onto our edge order."""
    mk = MeshKernel()
    t0 = time.perf_counter()
    mk.mesh2d_set(mesh)
    got = mk.mesh2d_get()
    vals = mk_orthogonality(mk)
    dt = time.perf_counter() - t0
    en_mk = np.sort(np.asarray(got.edge_nodes, np.int64).reshape(-1, 2), axis=1)
    base = int(max(en_mine.max(), en_mk.max())) + 2
    key_mk = en_mk[:, 0] * base + en_mk[:, 1]
    key_me = en_mine[:, 0] * base + en_mine[:, 1]
    lookup = dict(zip(key_mk.tolist(), range(len(key_mk))))
    idx = np.array([lookup.get(k, -1) for k in key_me.tolist()])
    out = np.full(len(key_me), np.nan)
    ok = idx >= 0
    out[ok] = vals[idx[ok]]
    return out, dt, mk, int((~ok).sum())


o_tri, dt, mk_tri, missing = mk_measure(mesh_tri, en_t)
timing["mk_orthogonality_tri_s"] = dt
co_tri, off_tri, int_tri = centroid_orthogonality(mesh_tri)
print(f"  MK orthogonality ({dt:.1f} s, {missing} edges unmatched):", shares(o_tri))
print("  centroid orthogonality:", shares(co_tri))


# ---- variant B: triangle pairs merged into convex quads ----
def merge_pairs(rings: list[np.ndarray]) -> tuple[list[np.ndarray], int]:
    """Greedy: merge two triangles sharing an edge into a quad when the quad is convex with every angle under
    150 degrees; pairs with the best (largest) minimum angle first."""
    tri = np.asarray(rings)
    edge_of = {}
    for ti, r in enumerate(tri):
        for a, b in ((r[0], r[1]), (r[1], r[2]), (r[2], r[0])):
            edge_of.setdefault((min(a, b), max(a, b)), []).append(ti)
    cands = []
    for (a, b), ts in edge_of.items():
        if len(ts) != 2:
            continue
        t1, t2 = tri[ts[0]], tri[ts[1]]
        c1 = [v for v in t1 if v not in (a, b)][0]
        c2 = [v for v in t2 if v not in (a, b)][0]
        quad = np.array([a, c1, b, c2])
        p = node_xy[quad]
        # orientation and convexity: every cross product of consecutive edges the same sign
        d = np.roll(p, -1, axis=0) - p
        cr = d[:, 0] * np.roll(d, -1, axis=0)[:, 1] - d[:, 1] * np.roll(d, -1, axis=0)[:, 0]
        if not ((cr > 1e-9).all() or (cr < -1e-9).all()):
            continue
        if cr[0] < 0:
            quad = quad[::-1]
            p = p[::-1]
            d = np.roll(p, -1, axis=0) - p
        u = -np.roll(d, 1, axis=0)
        ang = np.degrees(np.arccos(np.clip((u * d).sum(axis=1) / (np.linalg.norm(u, axis=1) * np.linalg.norm(d, axis=1)), -1, 1)))
        if ang.max() > 150 or ang.min() < 20:
            continue
        cands.append((ang.min(), ts[0], ts[1], quad))
    cands.sort(key=lambda c: -c[0])
    taken = np.zeros(len(tri), bool)
    out = []
    for _, i, j, quad in cands:
        if taken[i] or taken[j]:
            continue
        taken[i] = taken[j] = True
        out.append(quad)
    n_quads = len(out)
    out += [tri[i] for i in range(len(tri)) if not taken[i]]
    return out, n_quads


t0 = time.perf_counter()
merged, n_quads = merge_pairs(tri_rings)
timing["merge_pairs_s"] = time.perf_counter() - t0
faces_quad = faces + merged
kind_quad = face_kind + [3 if len(r) == 4 else 2 for r in merged]
corr_quad = face_corr + [-1] * len(merged)
row_quad = face_row + [99] * len(merged)
mesh_quad = mesh_from_faces(node_xy, faces_quad)
en_q, ef_q, fe_q = topology(mesh_quad)
summary_quad = mesh_summary(mesh_quad)
print(f"joined (merged): {n_quads} quads from {2 * n_quads} triangles, {len(merged) - n_quads} triangles left;", summary_quad)
o_quad, dt, mk_quad, missing = mk_measure(mesh_quad, en_q)
timing["mk_orthogonality_quad_s"] = dt
co_quad, off_quad, int_quad = centroid_orthogonality(mesh_quad)
print(f"  MK orthogonality ({dt:.1f} s, {missing} unmatched):", shares(o_quad))
print("  centroid orthogonality:", shares(co_quad))

# ---- per-kind breakdown of the orthogonality on the joined (triangle) mesh ----
kind_arr = np.asarray(kind_tri)


def by_kind(o, ef, kinds):
    out = {}
    k0 = np.where(ef[:, 0] >= 0, kinds[np.maximum(ef[:, 0], 0)], -1)
    k1 = np.where(ef[:, 1] >= 0, kinds[np.maximum(ef[:, 1], 0)], -1)
    names = {0: "lattice", 1: "strip", 2: "triangle", 3: "join quad"}
    for a in sorted(names):
        for b in sorted(names):
            if b < a:
                continue
            sel = ((k0 == a) & (k1 == b)) | ((k0 == b) & (k1 == a))
            if sel.any():
                out[f"{names[a]}-{names[b]}"] = shares(o[sel])
    return out


bk_tri = by_kind(o_tri, ef_t, kind_arr)
bk_quad = by_kind(o_quad, ef_q, np.asarray(kind_quad))
for k, v in bk_tri.items():
    print(f"  tri mesh, {k}: n {v['n']}, median {v['median']:.4f}, p90 {v['p90']:.4f}, max {v['max']:.4f}, >0.01 {v['share_gt_0.01']:.3f}, >0.05 {v['share_gt_0.05']:.3f}")
for k, v in bk_quad.items():
    print(f"  quad mesh, {k}: n {v['n']}, median {v['median']:.4f}, p90 {v['p90']:.4f}, max {v['max']:.4f}, >0.01 {v['share_gt_0.01']:.3f}, >0.05 {v['share_gt_0.05']:.3f}")

# ---- the breakline edges in the joined mesh ----
bank_edges = stp["bank_edges"].copy()
bank_edges[:, :2] += n_lat


def edge_index(en, pairs):
    base = int(en.max()) + 2
    key = np.sort(en, axis=1)
    key = key[:, 0] * base + key[:, 1]
    lookup = dict(zip(key.tolist(), range(len(key))))
    p = np.sort(pairs, axis=1)
    return np.array([lookup[int(a * base + b)] for a, b in p])


bank_edge_idx_tri = edge_index(en_t, bank_edges[:, :2])
bank_edge_idx_quad = edge_index(en_q, bank_edges[:, :2])


def save(path, mesh, en, ef, fe, kinds, corr, rows, o_mk, bank_idx):
    tbl, npf = faces_table(mesh)
    area, fcx, fcy = face_geometry(mesh)
    boundary = ef[:, 1] < 0
    on_bank = np.zeros(len(en), bool)
    on_bank[bank_idx] = True
    bank_side = np.full(len(en), -1, np.int8)
    bank_side[bank_idx] = bank_edges[:, 3]
    bank_corr = np.full(len(en), -1, np.int64)
    bank_corr[bank_idx] = bank_edges[:, 2]
    np.savez_compressed(
        path,
        node_x=node_xy[:, 0],
        node_y=node_xy[:, 1],
        face_nodes=tbl,
        nodes_per_face=npf,
        face_kind=np.asarray(kinds, np.int8),
        face_corridor=np.asarray(corr, np.int64),
        face_row=np.asarray(rows, np.int64),
        face_area=area,
        face_cx=fcx,
        face_cy=fcy,
        edge_nodes=en,
        edge_faces=ef,
        face_edges=fe,
        edge_boundary=boundary,
        edge_on_breakline=on_bank,
        edge_breakline_side=bank_side,
        edge_breakline_corridor=bank_corr,
        edge_orthogonality_mk=o_mk,
        dx=np.array([DX]),
    )


save(HERE / f"joined_tri{SUFFIX}.npz", mesh_tri, en_t, ef_t, fe_t, kind_tri, corr_tri, row_tri, o_tri, bank_edge_idx_tri)
save(HERE / f"joined_quad{SUFFIX}.npz", mesh_quad, en_q, ef_q, fe_q, kind_quad, corr_quad, row_quad, o_quad, bank_edge_idx_quad)

# cell sizes
area_tri, _, _ = face_geometry(mesh_tri)
size = np.sqrt(np.abs(area_tri))
kinds_t = np.asarray(kind_tri)
size_stats = {}
for k, name in {0: "lattice", 1: "strip", 2: "triangle"}.items():
    s = size[kinds_t == k]
    if len(s):
        size_stats[name] = {"n": int(len(s)), "sqrt_area_median": float(np.median(s)), "p10": float(np.percentile(s, 10)), "p90": float(np.percentile(s, 90)), "min": float(s.min()), "max": float(s.max())}
area_quad, _, _ = face_geometry(mesh_quad)
sq = np.sqrt(np.abs(area_quad))[np.asarray(kind_quad) == 3]
if len(sq):
    size_stats["join quad"] = {"n": int(len(sq)), "sqrt_area_median": float(np.median(sq)), "p10": float(np.percentile(sq, 10)), "p90": float(np.percentile(sq, 90)), "min": float(sq.min()), "max": float(sq.max())}

out = {
    "lattice_cells": int(len(boxes)),
    "removed_cells": int(removed.sum()),
    "gap_polygons": len(gaps),
    "gap_area_cells": float(gap.area / DX**2),
    "strip_cells": int(len(sfaces)),
    "triangles": tri_stats,
    "merged_quads": n_quads,
    "triangles_left_after_merge": len(merged) - n_quads,
    "joined_tri": {"summary": summary_tri, "orthogonality_mk": shares(o_tri), "orthogonality_centroid": shares(co_tri), "offset_centroid": shares(off_tri), "by_kind_mk": bk_tri},
    "joined_quad": {"summary": summary_quad, "orthogonality_mk": shares(o_quad), "orthogonality_centroid": shares(co_quad), "offset_centroid": shares(off_quad), "by_kind_mk": bk_quad},
    "cell_sizes": size_stats,
    "cells_vs_plain_lattice": {"plain": int(len(boxes)), "joined_tri": summary_tri["faces"], "joined_quad": summary_quad["faces"]},
    "meshkernel_triangulation_failures": mk_fail,
    "meshkernel_triangulation_errors": dict(_C(mk_errors).most_common(5)),
    "gap_buffer_m": GAP_BUFFER,
    "timing_s": timing,
}
json.dump(out, open(HERE / f"join{SUFFIX}.json", "w"), indent=1, default=float)


# ---- figures ----
def draw_faces(ax, mesh, kinds, window, title):
    tbl, npf = faces_table(mesh)
    fcx = node_xy[tbl[:, 0], 0]
    fcy = node_xy[tbl[:, 0], 1]
    x0, y0, w = window
    sel = (fcx > x0 - w - 40) & (fcx < x0 + w + 40) & (fcy > y0 - w - 40) & (fcy < y0 + w + 40)
    colors = {0: "#dddddd", 1: "#9ecae1", 2: "#fdae6b", 3: "#a1d99b"}
    for k, col in colors.items():
        rows = np.where(sel & (np.asarray(kinds) == k))[0]
        if len(rows) == 0:
            continue
        polys = [node_xy[tbl[i, : npf[i]]] for i in rows]
        ax.add_collection(PolyCollection(polys, facecolors=col, edgecolors="k", linewidths=0.4))
    ax.set_xlim(x0 - w, x0 + w)
    ax.set_ylim(y0 - w, y0 + w)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=9)


c = axis.centroid
main = corridors[0]
end_pt = np.asarray(main["polygon"].exterior.coords)[0]
fig, axs = plt.subplots(2, 2, figsize=(18, 17))
draw_faces(axs[0, 0], mesh_tri, kind_tri, (c.x, c.y, 160), "triangle join, 320 m window at the dam axis (grey lattice, blue strip, orange triangles)")
axs[0, 0].plot(*axis.xy, color="m", lw=1.5)
draw_faces(axs[0, 1], mesh_quad, kind_quad, (c.x, c.y, 160), "merged join (green quads, orange triangles left)")
axs[0, 1].plot(*axis.xy, color="m", lw=1.5)
draw_faces(axs[1, 0], mesh_tri, kind_tri, (end_pt[0], end_pt[1], 120), "triangle join at a corridor end")
draw_faces(axs[1, 1], mesh_quad, kind_quad, (end_pt[0], end_pt[1], 120), "merged join at a corridor end")
for ax in axs.ravel():
    for cr in corridors:
        ax.plot(*cr["L"].xy, color="r", lw=0.8)
        ax.plot(*cr["R"].xy, color="b", lw=0.8)
fig.tight_layout()
fig.savefig(HERE / f"fig_03_join_zoom{SUFFIX}.png", dpi=120)

# the orthogonality drawn on the join zone: edges coloured by MeshKernel's value
fig, ax = plt.subplots(figsize=(14, 12))
mid = np.column_stack([node_xy[en_t[:, 0]], node_xy[en_t[:, 1]]]).reshape(-1, 2, 2)
sel = (mid[:, 0, 0] > c.x - 200) & (mid[:, 0, 0] < c.x + 200) & (mid[:, 0, 1] > c.y - 200) & (mid[:, 0, 1] < c.y + 200)
vals = np.where(np.isfinite(o_tri), o_tri, 0.0)
lc = LineCollection(mid[sel], cmap="magma_r", norm=matplotlib.colors.LogNorm(vmin=1e-3, vmax=1.0), linewidths=1.2)
lc.set_array(np.maximum(vals[sel], 1e-4))
ax.add_collection(lc)
ax.plot(*axis.xy, color="c", lw=1.5)
ax.set_xlim(c.x - 200, c.x + 200)
ax.set_ylim(c.y - 200, c.y + 200)
ax.set_aspect("equal")
fig.colorbar(lc, ax=ax, label="MeshKernel orthogonality (log scale; 0 = orthogonal)")
ax.set_title("triangle join: orthogonality per edge, 400 m window at the dam axis")
fig.tight_layout()
fig.savefig(HERE / f"fig_03_join_orthogonality_map{SUFFIX}.png", dpi=120)

# histograms
fig, ax = plt.subplots(figsize=(10, 5.5))
bins = np.concatenate([[0], np.logspace(-5, 0, 41)])
for name, v in (("lattice alone (all 0)", np.zeros(10)), ("strips alone", np.load(HERE / "strips.npz")["node_x"][:0])):
    pass
o_strips = stp_o = None
ax.hist(o_tri[np.isfinite(o_tri)], bins=bins, histtype="step", color="C1", label=f"joined, triangles: p90 {shares(o_tri)['p90']:.3f}, >0.05: {shares(o_tri)['share_gt_0.05']*100:.2f} %")
ax.hist(o_quad[np.isfinite(o_quad)], bins=bins, histtype="step", color="C2", label=f"joined, merged quads: p90 {shares(o_quad)['p90']:.3f}, >0.05: {shares(o_quad)['share_gt_0.05']*100:.2f} %")
sel_s = (kind_arr[np.maximum(ef_t[:, 0], 0)] == 1) & (kind_arr[np.maximum(ef_t[:, 1], 0)] == 1) & (ef_t[:, 1] >= 0)
ax.hist(o_tri[sel_s & np.isfinite(o_tri)], bins=bins, histtype="step", color="C0", label=f"strip-strip edges: p90 {shares(o_tri[sel_s])['p90']:.4f}")
ax.set_xscale("symlog", linthresh=1e-4)
ax.set_yscale("log")
for v in (0.01, 0.02, 0.05):
    ax.axvline(v, color="0.6", lw=0.6, ls="--")
ax.set_xlabel("MeshKernel orthogonality per interior edge (0 = orthogonal)")
ax.set_ylabel("edges")
ax.legend(fontsize=8)
ax.set_title("joined mesh: orthogonality (the lattice's own edges are all exactly 0)")
fig.tight_layout()
fig.savefig(HERE / f"fig_03_join_orthogonality_hist{SUFFIX}.png", dpi=130)
print("timing", {k: round(v, 2) for k, v in timing.items()})
