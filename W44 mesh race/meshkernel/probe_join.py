"""Probe 3: what mesh2d_connect_meshes and mesh2d_make_triangular_mesh_from_polygon do on a toy: a 20 m lattice
with a hole, and a rotated strip of 20 x 10 m cells inside the hole. Writes probe_join.png.
"""

from __future__ import annotations

import traceback
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shapely
from matplotlib.collections import LineCollection
from meshkernel import DeleteMeshOption, MakeGridParameters, Mesh2d, MeshKernel

from common import HERE
from mkutil import face_polygons, geom_list, mesh_summary, mk_orthogonality, polygon_geom, shares


def draw(ax, m, title, color="k"):
    x = np.asarray(m.node_x)
    y = np.asarray(m.node_y)
    en = np.asarray(m.edge_nodes).reshape(-1, 2)
    segs = np.stack([np.column_stack([x[en[:, 0]], y[en[:, 0]]]), np.column_stack([x[en[:, 1]], y[en[:, 1]]])], axis=1)
    ax.add_collection(LineCollection(segs, colors=color, linewidths=0.6))
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=8)


# the strip: 20 m along x', 10 m across, rotated 30 degrees, 3 rows, 20 cells long
ang = np.radians(30)
R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
mk_s = MeshKernel()
mk_s.mesh2d_make_rectangular_mesh(MakeGridParameters(num_columns=20, num_rows=3, origin_x=0, origin_y=0, block_size_x=20, block_size_y=10))
strip = mk_s.mesh2d_get()
pts = np.column_stack([strip.node_x, strip.node_y]) @ R.T + [150.0, 140.0]
strip = Mesh2d(node_x=pts[:, 0].copy(), node_y=pts[:, 1].copy(), edge_nodes=strip.edge_nodes, face_nodes=strip.face_nodes, nodes_per_face=strip.nodes_per_face)
mk_s.mesh2d_set(strip)
strip = mk_s.mesh2d_get()
sb = mk_s.mesh2d_get_mesh_boundaries_as_polygons()
strip_poly = shapely.Polygon(np.column_stack([sb.x_coordinates, sb.y_coordinates]))
print("strip", mesh_summary(strip), "boundary vertices", len(sb.x_coordinates))

# the lattice: 30 x 20 cells of 20 m
mk = MeshKernel()
mk.mesh2d_make_rectangular_mesh(MakeGridParameters(num_columns=30, num_rows=20, origin_x=0, origin_y=0, block_size_x=20, block_size_y=20))
lat = mk.mesh2d_get()
# the hole: lattice cells intersecting the strip polygon
mk.mesh2d_delete(polygon_geom(strip_poly), DeleteMeshOption.INSIDE_AND_INTERSECTED, invert_deletion=False)
holed = mk.mesh2d_get()
print("lattice", mesh_summary(lat), "-> holed", mesh_summary(holed))

fig, axes = plt.subplots(2, 3, figsize=(18, 11))
axes = axes.ravel()
draw(axes[0], holed, "lattice with the hole (INSIDE_AND_INTERSECTED) + strip")
draw(axes[0], strip, "", color="r")

# A: mesh2d_connect_meshes with connect=True
for k, (connect, frac) in enumerate([(True, 0.4), (True, 2.0), (False, 0.4)]):
    try:
        mk2 = MeshKernel()
        mk2.mesh2d_set(holed)
        mk2.mesh2d_connect_meshes(strip, connect=connect, search_fraction=frac)
        joined = mk2.mesh2d_get()
        s = mesh_summary(joined)
        hang = mk2.mesh2d_get_hanging_edges()
        print(f"connect_meshes connect={connect} fraction={frac}:", s, "hanging edges", len(np.asarray(hang)))
        o = mk_orthogonality(mk2)
        print("   orthogonality", shares(o))
        draw(axes[1 + k], joined, f"connect_meshes connect={connect} search_fraction={frac}: {s['faces_by_nodes']}")
    except Exception:
        print("connect_meshes FAILED", connect, frac)
        traceback.print_exc()

# B: the gap triangulated by MeshKernel: gap polygon = union of removed lattice faces minus the strip
lat_polys = face_polygons(lat)
removed = [p for p in lat_polys if p.intersects(strip_poly)]
gap = shapely.unary_union(removed).difference(strip_poly)
print("gap:", gap.geom_type, "parts", shapely.get_num_geometries(gap), "area", round(gap.area, 1))
try:
    mk3 = MeshKernel()
    parts = list(gap.geoms) if hasattr(gap, "geoms") else [gap]
    # one polygon at a time: the gap around a strip is an annulus (a polygon with a hole) -> see what happens
    mk3.mesh2d_make_triangular_mesh_from_polygon(polygon_geom(parts[0]))
    tri = mk3.mesh2d_get()
    print("triangular mesh from the annular gap polygon:", mesh_summary(tri))
    draw(axes[4], tri, f"make_triangular_mesh_from_polygon(gap annulus): {mesh_summary(tri)['faces_by_nodes']}")
    draw(axes[4], strip, "", color="r")
except Exception:
    print("triangular from polygon FAILED")
    traceback.print_exc()

# C: constrained Delaunay of the gap with shapely (boundary vertices only)
try:
    cdt = shapely.constrained_delaunay_triangles(gap)
    tris = list(cdt.geoms)
    print("shapely CDT of the gap:", len(tris), "triangles; min angle distribution:")
    angs = []
    for t in tris:
        c = np.asarray(t.exterior.coords)[:3]
        v = [c[(i + 1) % 3] - c[i] for i in range(3)]
        a = []
        for i in range(3):
            u, w = -v[i - 1], v[i]
            a.append(np.degrees(np.arccos(np.clip(np.dot(u, w) / (np.linalg.norm(u) * np.linalg.norm(w)), -1, 1))))
        angs.append(min(a))
    angs = np.array(angs)
    print("   min angle: median %.1f p10 %.1f min %.1f; under 10 deg: %d" % (np.median(angs), np.percentile(angs, 10), angs.min(), (angs < 10).sum()))
    for t in tris:
        axes[5].plot(*t.exterior.xy, color="g", lw=0.5)
    draw(axes[5], holed, f"shapely constrained Delaunay of the gap: {len(tris)} triangles")
    draw(axes[5], strip, "", color="r")
except Exception:
    print("CDT FAILED")
    traceback.print_exc()

for ax in axes:
    ax.set_xlim(80, 560)
    ax.set_ylim(60, 400)
fig.tight_layout()
fig.savefig(HERE / "probe_join.png", dpi=110)
print("wrote probe_join.png")
