"""Step 4 and 5: the measurements side by side (lattice alone, strips alone raw and snapped, joined) and the
solver-ready export.

usage: python s05_measure_export.py [--in _gap10]
reads lattice.npz, strips.npz, strips_raw.npz, strips_polygons.pkl, joined_tri<in>.npz, join<in>.json;
writes measure.json, fig_05_orthogonality.png, fig_05_bank_distance.png, fig_05_cell_size.png and
mesh_faydh01_hybrid_20m.npz (the joined mesh with its format described in NOTES.md).
"""

from __future__ import annotations

import json
import pickle
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from meshkernel import Mesh2d, MeshKernel

from common import DX, HERE
from mkutil import mk_orthogonality, shares, topology

IN = sys.argv[sys.argv.index("--in") + 1] if "--in" in sys.argv else "_gap10"
lat = np.load(HERE / "lattice.npz")
stp = np.load(HERE / "strips.npz")
raw = np.load(HERE / "strips_raw.npz")
J = np.load(HERE / f"joined_tri{IN}.npz")
join_info = json.load(open(HERE / f"join{IN}.json"))
corridors = pickle.load(open(HERE / "strips_polygons.pkl", "rb"))
lines = {(c["k"], 0): c["L"] for c in corridors}
lines.update({(c["k"], 1): c["R"] for c in corridors})

out = {"input_suffix": IN}


def mk_ortho_of(node_x, node_y, face_nodes, npf):
    fn = np.concatenate([row[:n] for row, n in zip(face_nodes, npf)]).astype(np.int32)
    m = Mesh2d(node_x=np.asarray(node_x, float), node_y=np.asarray(node_y, float), face_nodes=fn, nodes_per_face=np.asarray(npf, np.int32))
    en, ef, _ = topology(m)
    m.edge_nodes = en.astype(np.int32).ravel()
    mk = MeshKernel()
    mk.mesh2d_set(m)
    got = mk.mesh2d_get()
    vals = mk_orthogonality(mk)
    en_mk = np.sort(np.asarray(got.edge_nodes, np.int64).reshape(-1, 2), axis=1)
    base = int(max(en.max(), en_mk.max())) + 2
    lookup = dict(zip((en_mk[:, 0] * base + en_mk[:, 1]).tolist(), range(len(en_mk))))
    idx = np.array([lookup.get(int(k), -1) for k in (en[:, 0] * base + en[:, 1]).tolist()])
    o = np.full(len(en), np.nan)
    o[idx >= 0] = vals[idx[idx >= 0]]
    return o, en, ef


# ---- orthogonality: the three meshes ----
o_lat = lat["face_nodes"]  # the lattice is exactly orthogonal (s01: every interior edge 0)
o_strip_raw, en_raw, _ = mk_ortho_of(raw["node_x"], raw["node_y"], raw["face_nodes"], raw["nodes_per_face"])
o_strip, en_s, _ = mk_ortho_of(stp["node_x"], stp["node_y"], stp["face_nodes"], stp["nodes_per_face"])
o_join = J["edge_orthogonality_mk"]
out["orthogonality_mk"] = {
    "lattice_alone": json.load(open(HERE / "lattice.json"))["orthogonality_meshkernel"],
    "strips_alone_raw_meshkernel": shares(o_strip_raw),
    "strips_alone_snapped": shares(o_strip),
    "joined": shares(o_join),
    "joined_by_kind": join_info["joined_tri"]["by_kind_mk"],
}
out["orthogonality_centroid"] = {
    "strips_alone_snapped": json.load(open(HERE / "strips.json"))["all_strips"]["orthogonality_centroid"],
    "joined": join_info["joined_tri"]["orthogonality_centroid"],
}

# ---- distance of every breakline face from its breakline, raw and snapped ----
bank = stp["bank_edges"]  # (n, 4): a, b, corridor, side


def bank_dist(nx, ny):
    xy = np.column_stack([nx, ny])
    mids = 0.5 * (xy[bank[:, 0]] + xy[bank[:, 1]])
    d = np.array([lines[(int(k), int(s))].distance(shapely.Point(p)) for p, k, s in zip(mids, bank[:, 2], bank[:, 3])])
    ends = np.array([max(lines[(int(k), int(s))].distance(shapely.Point(xy[a])), lines[(int(k), int(s))].distance(shapely.Point(xy[b]))) for a, b, k, s in bank])
    return d, ends


d_raw, e_raw = bank_dist(raw["node_x"], raw["node_y"])
d_snap, e_snap = bank_dist(stp["node_x"], stp["node_y"])
out["bank_edge_distance_m"] = {
    "edges": int(len(d_raw)),
    "raw_meshkernel": {"midpoint_median": float(np.median(d_raw)), "midpoint_p90": float(np.percentile(d_raw, 90)), "midpoint_max": float(d_raw.max()), "ends_max": float(e_raw.max())},
    "snapped": {"midpoint_median": float(np.median(d_snap)), "midpoint_p90": float(np.percentile(d_snap, 90)), "midpoint_max": float(d_snap.max()), "ends_max": float(e_snap.max()), "ends_p90": float(np.percentile(e_snap, 90))},
    "staircase_reference_half_cell_m": DX / 2,
}
# the breakline edges inside the joined mesh are the same nodes (strip nodes offset by the kept lattice count)
assert J["edge_on_breakline"].sum() == len(bank)

# ---- cell sizes ----
area = J["face_area"]
kind = J["face_kind"]
names = {0: "lattice", 1: "strip", 2: "join triangle"}
out["cell_size"] = {}
for k, name in names.items():
    s = np.sqrt(np.abs(area[kind == k]))
    if len(s):
        out["cell_size"][name] = {"n": int(len(s)), "sqrt_area_median": float(np.median(s)), "p10": float(np.percentile(s, 10)), "p90": float(np.percentile(s, 90)), "min": float(s.min()), "max": float(s.max())}
# strip edge lengths along and across
sx, sy = stp["node_x"], stp["node_y"]
el = np.hypot(sx[en_s[:, 1]] - sx[en_s[:, 0]], sy[en_s[:, 1]] - sy[en_s[:, 0]])
out["strip_edge_length_m"] = {"median": float(np.median(el)), "p10": float(np.percentile(el, 10)), "p90": float(np.percentile(el, 90)), "min": float(el.min()), "max": float(el.max())}
out["cell_count"] = {
    "plain_lattice": int(len(lat["face_nodes"])),
    "lattice_kept": int((kind == 0).sum()),
    "strip_cells": int((kind == 1).sum()),
    "join_triangles": int((kind == 2).sum()),
    "joined_total": int(len(kind)),
    "ratio_to_plain": float(len(kind) / len(lat["face_nodes"])),
}
out["triangles"] = join_info["triangles"]
json.dump(out, open(HERE / f"measure{IN}.json", "w"), indent=1, default=float)

# ---- figures ----
bins = np.concatenate([[0], np.logspace(-5, 0, 51)])
fig, ax = plt.subplots(figsize=(10, 5.5))
for label, v, c in (
    (f"strips alone, MeshKernel raw: >0.01 {shares(o_strip_raw)['share_gt_0.01']*100:.0f} %, >0.05 {shares(o_strip_raw)['share_gt_0.05']*100:.1f} %", o_strip_raw, "C0"),
    (f"strips alone, snapped to the banks: >0.01 {shares(o_strip)['share_gt_0.01']*100:.0f} %, >0.05 {shares(o_strip)['share_gt_0.05']*100:.1f} %", o_strip, "C1"),
    (f"joined mesh, all edges: >0.01 {shares(o_join)['share_gt_0.01']*100:.1f} %, >0.05 {shares(o_join)['share_gt_0.05']*100:.1f} %", o_join, "C3"),
):
    ax.hist(v[np.isfinite(v)], bins=bins, histtype="step", color=c, label=label, lw=1.2)
ax.set_xscale("symlog", linthresh=1e-4)
ax.set_yscale("log")
for t in (0.01, 0.02, 0.05):
    ax.axvline(t, color="0.6", lw=0.6, ls="--")
ax.set_xlabel("MeshKernel orthogonality per interior edge (|cos| edge vs circumcentre line; 0 = orthogonal)")
ax.set_ylabel("edges (log)")
ax.set_title("orthogonality: the plain lattice is 0 on all 376,220 interior edges (not drawn)")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(HERE / f"fig_05_orthogonality{IN}.png", dpi=130)

fig, ax = plt.subplots(figsize=(9, 5))
b = np.linspace(0, 15, 61)
ax.hist(d_raw, bins=b, histtype="step", color="C0", label=f"MeshKernel raw +-10 m line: median {np.median(d_raw):.2f}, p90 {np.percentile(d_raw, 90):.2f}, max {d_raw.max():.1f} m")
ax.hist(d_snap, bins=b, histtype="step", color="C1", label=f"snapped: median {np.median(d_snap):.2f}, p90 {np.percentile(d_snap, 90):.2f}, max {d_snap.max():.1f} m")
ax.axvline(DX / 2, color="r", ls="--", lw=0.8, label="half a 20 m cell: the staircase's worst offset")
ax.set_xlabel("distance of the breakline face midpoint from the W26 bank line (m)")
ax.set_ylabel("faces")
ax.set_title(f"{len(d_raw):,} breakline faces on {len(corridors)} corridors")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(HERE / "fig_05_bank_distance.png", dpi=130)

fig, ax = plt.subplots(figsize=(9, 5))
b = np.linspace(0, 25, 51)
for k, name in names.items():
    s = np.sqrt(np.abs(area[kind == k]))
    ax.hist(s, bins=b, histtype="step", label=f"{name}: n {len(s):,}, median {np.median(s):.1f} m", lw=1.2)
ax.set_yscale("log")
ax.set_xlabel("sqrt(cell area), m")
ax.set_ylabel("cells (log)")
ax.set_title("cell sizes of the joined mesh")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(HERE / f"fig_05_cell_size{IN}.png", dpi=130)

# ---- the export ----
np.savez_compressed(
    HERE / "mesh_faydh01_hybrid_20m.npz",
    node_x=J["node_x"],
    node_y=J["node_y"],
    face_nodes=J["face_nodes"],
    nodes_per_face=J["nodes_per_face"],
    face_kind=J["face_kind"],
    face_corridor=J["face_corridor"],
    face_row=J["face_row"],
    face_area=J["face_area"],
    face_cx=J["face_cx"],
    face_cy=J["face_cy"],
    edge_nodes=J["edge_nodes"],
    edge_faces=J["edge_faces"],
    face_edges=J["face_edges"],
    edge_boundary=J["edge_boundary"],
    edge_on_breakline=J["edge_on_breakline"],
    edge_breakline_side=J["edge_breakline_side"],
    edge_breakline_corridor=J["edge_breakline_corridor"],
    edge_orthogonality_mk=J["edge_orthogonality_mk"],
    crs=np.array(["EPSG:32640"]),
    dx=np.array([DX]),
)
print(json.dumps(out, indent=1, default=float))
