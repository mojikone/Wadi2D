"""Step 4b: mesh2d_compute_orthogonalization on the joined mesh. Does it keep the strip faces on the breaklines,
and what does the orthogonality become?

Trials, each from the joined (triangle) mesh of s03:
  whole        the whole mesh, MeshKernel's default parameters, no land boundary
  whole_x5     the same with 5 outer iterations
  band_out     only nodes in the join band (the removed lattice cells less the corridor shrunk by 12 m, grown by
               1 m so the lattice hole-boundary nodes count): the gap, the strips' outer rows and the lattice's
               hole boundary move; the bank rows stay
  band_in      the band shrunk by 1 m instead: only the strips' outermost row moves

usage: python s04_orthogonalize.py [trial ...]
reads joined_tri.npz, lattice.npz, strips_polygons.pkl; writes orthogonalize.json, joined_tri_ortho_<trial>.npz,
fig_04_*.png
"""

from __future__ import annotations

import json
import pickle
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from matplotlib.collections import LineCollection
from meshkernel import GeometryList, Mesh2d, MeshKernel, OrthogonalizationParameters, ProjectToLandBoundaryOption

from common import DX, HERE, dam_axis
from mkutil import centroid_orthogonality, face_geometry, faces_table, mesh_from_faces, mk_orthogonality, multipolygon_geom, shares, topology

TRIALS = [a for a in sys.argv[1:] if not a.startswith("-") and (sys.argv[sys.argv.index(a) - 1] != "--in")] or ["whole", "whole_x5", "band_out", "band_in"]
IN = sys.argv[sys.argv.index("--in") + 1] if "--in" in sys.argv else ""  # suffix of the joined mesh to read
J = np.load(HERE / f"joined_tri{IN}.npz")
corridors = pickle.load(open(HERE / "strips_polygons.pkl", "rb"))
axis = dam_axis()
node_xy0 = np.column_stack([J["node_x"], J["node_y"]])
tbl, npf = J["face_nodes"], J["nodes_per_face"]
faces = [row[:n] for row, n in zip(tbl, npf)]
kinds = J["face_kind"]
en0 = J["edge_nodes"]
on_bank = J["edge_on_breakline"]
bank_side = J["edge_breakline_side"]
bank_corr = J["edge_breakline_corridor"]
lines = {(c["k"], 0): c["L"] for c in corridors}
lines.update({(c["k"], 1): c["R"] for c in corridors})
bank_nodes = np.unique(en0[on_bank].ravel())


def bank_distance(node_xy):
    mids = 0.5 * (node_xy[en0[on_bank, 0]] + node_xy[en0[on_bank, 1]])
    d = np.array([lines[(int(k), int(s))].distance(shapely.Point(p)) for p, k, s in zip(mids, bank_corr[on_bank], bank_side[on_bank])])
    return {"edges": int(len(d)), "median": float(np.median(d)), "p90": float(np.percentile(d, 90)), "max": float(d.max())}


def measure(mk, node_xy):
    got = mk.mesh2d_get()
    vals = mk_orthogonality(mk)
    en_mk = np.sort(np.asarray(got.edge_nodes, np.int64).reshape(-1, 2), axis=1)
    base = int(max(en0.max(), en_mk.max())) + 2
    lookup = dict(zip((en_mk[:, 0] * base + en_mk[:, 1]).tolist(), range(len(en_mk))))
    key = np.sort(en0, axis=1)
    idx = np.array([lookup.get(int(k), -1) for k in (key[:, 0] * base + key[:, 1]).tolist()])
    o = np.full(len(en0), np.nan)
    o[idx >= 0] = vals[idx[idx >= 0]]
    mesh = mesh_from_faces(node_xy, faces)
    co, off, interior = centroid_orthogonality(mesh)
    area, _, _ = face_geometry(mesh)
    ef = J["edge_faces"]
    k0 = np.where(ef[:, 0] >= 0, kinds[np.maximum(ef[:, 0], 0)], -1)
    k1 = np.where(ef[:, 1] >= 0, kinds[np.maximum(ef[:, 1], 0)], -1)
    by = {}
    names = {0: "lattice", 1: "strip", 2: "triangle"}
    for a in names:
        for b in names:
            if b < a:
                continue
            sel = ((k0 == a) & (k1 == b)) | ((k0 == b) & (k1 == a))
            if sel.any():
                by[f"{names[a]}-{names[b]}"] = shares(o[sel])
    return {
        "orthogonality_mk": shares(o),
        "orthogonality_centroid": shares(co),
        "by_kind_mk": by,
        "bank_edges_on_breakline": shares(o[on_bank]),
        "bank_distance_m": bank_distance(node_xy),
        "folded_or_empty_cells": int((area <= 1.0).sum()),
        "area_min": float(area.min()),
    }, o


def base_mesh():
    return Mesh2d(node_x=node_xy0[:, 0].copy(), node_y=node_xy0[:, 1].copy(), edge_nodes=en0.astype(np.int32).ravel(),
                  face_nodes=np.concatenate(faces).astype(np.int32), nodes_per_face=npf.astype(np.int32))


results = {}
mk = MeshKernel()
mk.mesh2d_set(base_mesh())
before, o_before = measure(mk, node_xy0)
print("before:", before["orthogonality_mk"], "bank distance", before["bank_distance_m"])
results["before"] = before

# the join band for the band trials
lat = np.load(HERE / "lattice.npz")
lx, ly = lat["node_x"], lat["node_y"]
lf = lat["face_nodes"]
cx = lx[lf].mean(axis=1)
cy = ly[lf].mean(axis=1)
boxes = shapely.box(cx - DX / 2, cy - DX / 2, cx + DX / 2, cy + DX / 2)
tree = shapely.STRtree(boxes)
corr_polys = [c["polygon"] for c in corridors]
hit = tree.query(corr_polys, predicate="intersects")
hole = shapely.unary_union(boxes[np.unique(hit[1])])
inner = shapely.unary_union([p.buffer(-12.0) for p in corr_polys])
band = hole.difference(inner)


def band_geom(delta):
    g = band.buffer(delta)
    parts = list(g.geoms) if hasattr(g, "geoms") else [g]
    return multipolygon_geom([p for p in parts if p.area > 1.0])


for trial in TRIALS:
    mk = MeshKernel()
    mk.mesh2d_set(base_mesh())
    params = OrthogonalizationParameters()
    sel = GeometryList()
    if trial == "whole_x5":
        params.outer_iterations = 5
    elif trial == "band_out":
        sel = band_geom(+1.0)
    elif trial == "band_in":
        sel = band_geom(-1.0)
    t0 = time.perf_counter()
    try:
        mk.mesh2d_compute_orthogonalization(ProjectToLandBoundaryOption.DO_NOT_PROJECT_TO_LANDBOUNDARY, params, GeometryList(), sel)
    except Exception as e:
        results[trial] = {"error": str(e), "seconds": time.perf_counter() - t0}
        print(trial, "FAILED", e)
        continue
    dt = time.perf_counter() - t0
    got = mk.mesh2d_get()
    xy = np.column_stack([got.node_x, got.node_y])
    if len(xy) != len(node_xy0):
        results[trial] = {"error": f"node count changed {len(node_xy0)} -> {len(xy)}", "seconds": dt}
        print(trial, "node count changed")
        continue
    move = np.hypot(*(xy - node_xy0).T)
    after, o_after = measure(mk, xy)
    after["seconds"] = dt
    after["node_move_m"] = {"moved_over_1mm": int((move > 1e-3).sum()), "median_of_moved": float(np.median(move[move > 1e-3])) if (move > 1e-3).any() else 0.0, "p90_of_moved": float(np.percentile(move[move > 1e-3], 90)) if (move > 1e-3).any() else 0.0, "max": float(move.max())}
    after["bank_node_move_m"] = {"n": int(len(bank_nodes)), "median": float(np.median(move[bank_nodes])), "p90": float(np.percentile(move[bank_nodes], 90)), "max": float(move[bank_nodes].max())}
    results[trial] = after
    print(f"{trial}: {dt:.1f} s; ortho {after['orthogonality_mk']}; bank nodes moved max {after['bank_node_move_m']['max']:.2f} m, p90 {after['bank_node_move_m']['p90']:.2f}; bank distance {after['bank_distance_m']}; folded {after['folded_or_empty_cells']}")
    np.savez_compressed(HERE / f"joined_tri{IN}_ortho_{trial}.npz", node_x=xy[:, 0], node_y=xy[:, 1], face_nodes=tbl, nodes_per_face=npf, face_kind=kinds, edge_nodes=en0, edge_orthogonality_mk=o_after, node_move_m=move)

    # figure: before/after at the dam axis
    c = axis.centroid
    fig, axs = plt.subplots(1, 2, figsize=(18, 9))
    for ax, pts, o, title in ((axs[0], node_xy0, o_before, "before"), (axs[1], xy, o_after, f"after {trial} ({dt:.0f} s)")):
        segs = np.stack([pts[en0[:, 0]], pts[en0[:, 1]]], axis=1)
        s = (segs[:, 0, 0] > c.x - 180) & (segs[:, 0, 0] < c.x + 180) & (segs[:, 0, 1] > c.y - 180) & (segs[:, 0, 1] < c.y + 180)
        lc = LineCollection(segs[s], cmap="magma_r", norm=matplotlib.colors.LogNorm(vmin=1e-3, vmax=1.0), linewidths=1.0)
        lc.set_array(np.maximum(np.where(np.isfinite(o[s]), o[s], 0.0), 1e-4))
        ax.add_collection(lc)
        for cr in corridors:
            ax.plot(*cr["L"].xy, color="c", lw=0.8)
            ax.plot(*cr["R"].xy, color="c", lw=0.8)
        ax.plot(*axis.xy, color="lime", lw=1.2)
        ax.set_xlim(c.x - 180, c.x + 180)
        ax.set_ylim(c.y - 180, c.y + 180)
        ax.set_aspect("equal")
        ax.set_title(f"{title}: orthogonality per edge (cyan: W26 banks)", fontsize=9)
    fig.colorbar(lc, ax=axs, label="MeshKernel orthogonality (log)", shrink=0.6)
    fig.savefig(HERE / f"fig_04_ortho{IN}_{trial}.png", dpi=120)
    plt.close(fig)

json.dump(results, open(HERE / f"orthogonalize{IN}.json", "w"), indent=1, default=float)
print("done")
