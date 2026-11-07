"""Step 1: the 20 m lattice over the Faydh 01 domain with MeshKernel, cells outside the domain polygon deleted.

usage: python s01_lattice.py
writes lattice.npz, lattice.json and fig_01_lattice.png beside this script.
"""

from __future__ import annotations

import json
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from meshkernel import DeleteMeshOption, MakeGridParameters, MeshKernel

from common import DX, HERE, dam_axis, domain
from mkutil import centroid_orthogonality, face_areas, mesh_summary, mk_orthogonality, polygon_geom, save_mesh, shares

poly = domain()
xy = np.asarray(poly.exterior.coords)
x0, y0 = xy[:, 0].min(), xy[:, 1].min()
ncol = int(round((xy[:, 0].max() - x0) / DX))
nrow = int(round((xy[:, 1].max() - y0) / DX))
print(f"domain {poly.area/1e6:.4f} km2, box {ncol} x {nrow} cells of {DX} m, expected inside {poly.area/DX**2:.1f}")

timing = {}
mk = MeshKernel()
t0 = time.perf_counter()
mk.mesh2d_make_rectangular_mesh(
    MakeGridParameters(num_columns=ncol, num_rows=nrow, origin_x=x0, origin_y=y0, block_size_x=DX, block_size_y=DX)
)
timing["make_rectangular_s"] = time.perf_counter() - t0
m_box = mk.mesh2d_get()
print("box mesh", mesh_summary(m_box), f"{timing['make_rectangular_s']:.2f} s")

t0 = time.perf_counter()
# delete everything outside the domain. INSIDE_NOT_INTERSECTED inverted dropped 2,790 boundary cells whose
# centres lie inside (the domain polygon runs along cell edges, so every boundary cell counts as intersected);
# the circumcentre option keeps exactly the cells with their centre inside.
mk.mesh2d_delete(polygon_geom(poly), DeleteMeshOption.FACES_WITH_INCLUDED_CIRCUMCENTERS, invert_deletion=True)
timing["delete_outside_s"] = time.perf_counter() - t0
m = mk.mesh2d_get()
summary = mesh_summary(m)
print("lattice", summary, f"{timing['delete_outside_s']:.2f} s")
print("array lengths: edge_nodes", len(m.edge_nodes), "edge_faces", len(m.edge_faces), "face_edges", len(m.face_edges))

# check against shapely: cells whose centre lies in the polygon
t0 = time.perf_counter()
cx = x0 + DX * (np.arange(ncol) + 0.5)
cy = y0 + DX * (np.arange(nrow) + 0.5)
gx, gy = np.meshgrid(cx, cy)
inside = shapely.contains_xy(poly, gx.ravel(), gy.ravel())
timing["shapely_check_s"] = time.perf_counter() - t0
print("shapely cells with centre inside:", int(inside.sum()))

t0 = time.perf_counter()
orth = mk_orthogonality(mk)
timing["orthogonality_s"] = time.perf_counter() - t0
o_mk = shares(orth)
co, off, interior = centroid_orthogonality(m)
o_c = shares(co)
areas = face_areas(m)
print("MeshKernel orthogonality (interior edges):", o_mk)
print("centroid orthogonality:", o_c)
print("areas: min %.3f max %.3f" % (areas.min(), areas.max()), "interior edges", int(interior.sum()))

save_mesh(HERE / "lattice.npz", m, face_kind=np.zeros(summary["faces"], np.int8), origin=np.array([x0, y0]), dx=np.array([DX]))
json.dump(
    {
        "dx": DX,
        "origin": [x0, y0],
        "box_cells": [ncol, nrow],
        "summary": summary,
        "expected_cells": poly.area / DX**2,
        "shapely_centre_inside": int(inside.sum()),
        "orthogonality_meshkernel": o_mk,
        "orthogonality_centroid": o_c,
        "area_min_max": [float(areas.min()), float(areas.max())],
        "timing_s": timing,
    },
    open(HERE / "lattice.json", "w"),
    indent=1,
)

fig, ax = plt.subplots(figsize=(14, 10))
en = np.asarray(m.edge_nodes).reshape(-1, 2)
# draw the mesh boundary only at full extent (the lattice itself is 190k cells) and a zoom near the dam
bnd = mk.mesh2d_get_mesh_boundaries_as_polygons()
bx = np.asarray(bnd.x_coordinates)
by = np.asarray(bnd.y_coordinates)
bx = np.where(bx <= -998, np.nan, bx)
by = np.where(by <= -998, np.nan, by)
ax.plot(bx, by, color="k", lw=0.5)
axis = dam_axis()
ax.plot(*axis.xy, color="r", lw=2)
ax.set_aspect("equal")
ax.set_title(f"20 m lattice boundary, {summary['faces']:,} cells; red: dam axis")
ins = ax.inset_axes([0.55, 0.05, 0.43, 0.43])
x = np.asarray(m.node_x)
y = np.asarray(m.node_y)
c = axis.centroid
win = (x > c.x - 300) & (x < c.x + 300) & (y > c.y - 300) & (y < c.y + 300)
sel = win[en[:, 0]] | win[en[:, 1]]
segs = np.stack([np.column_stack([x[en[sel, 0]], y[en[sel, 0]]]), np.column_stack([x[en[sel, 1]], y[en[sel, 1]]])], axis=1)
from matplotlib.collections import LineCollection

ins.add_collection(LineCollection(segs, colors="0.4", linewidths=0.4))
ins.plot(*axis.xy, color="r", lw=1.5)
ins.set_xlim(c.x - 300, c.x + 300)
ins.set_ylim(c.y - 300, c.y + 300)
ins.set_aspect("equal")
ins.set_title("600 m window at the dam axis", fontsize=8)
fig.tight_layout()
fig.savefig(HERE / "fig_01_lattice.png", dpi=120)
print("timing", timing)
