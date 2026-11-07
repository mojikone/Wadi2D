"""A close map of a strip run: the aligned cells and the squares, the bank breaklines, and the largest depth of the
run on every cell, with the result lines; two windows, the dam axis and a bank in detail.

    .venv\\Scripts\\python "W45 aligned mesh engine\\map_close.py" <run folder> <job json> <breaklines gpkg> <out png>
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import shapely
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.colors import Normalize

run, job, banks_path, out = (Path(a) for a in sys.argv[1:5])
cfg = json.loads(job.read_text(encoding="utf-8"))
lines = {ln["name"]: np.asarray(ln["coordinates"]) for ln in cfg["outputs"]["lines"]}
axis = lines["axis"]
dx = float(cfg["grid"]["dx"])

PIXELS = (run / "pixels" / "pixel_depth.tif").is_file()
"""With the pixel products the depth is at the DEM pixel over squares and strip alike; else the cell maxima."""
with rasterio.open(run / "pixels" / "pixel_depth.tif" if PIXELS else run / "maps" / "max_depth.tif") as src:
    depth = src.read(1).astype(np.float64)
    nodata = src.nodata
    t = src.transform
    left, top = t.c, t.f
    pixel = t.a
if nodata is not None:
    depth = np.where(depth == nodata, np.nan, depth)
depth = np.where(depth <= 0.0, np.nan, depth)

db = sqlite3.connect(run / "maps" / "strip_mesh.gpkg")


def blobs(table: str, fields: str):
    rows = db.execute(f"SELECT geom, {fields} FROM {table}").fetchall()
    geoms = [shapely.get_parts(shapely.from_wkb(r[0][40:]))[0] for r in rows]  # the layers hold multi-parts  # the GeoPackage header is 8 + 32 bytes with an envelope
    return geoms, [r[1:] for r in rows]


cell_geoms, cell_rows = blobs("strip_cells", "kind, max_depth_m, corridor")
face_geoms, face_rows = blobs("strip_faces", "kind, max_discharge_m3s")
db.close()

import fiona  # noqa: E402

banks = []
with fiona.open(banks_path, layer="breaklines") as src:
    for f in src:
        if f["properties"].get("kind") == "stream bank":
            banks.append(shapely.geometry.shape(f["geometry"]))

norm = Normalize(0.0, float(np.nanpercentile(depth, 99.5)))
cmap = plt.get_cmap("Blues")


def window(ax, cx: float, cy: float, half: float, title: str, lattice_edges: bool) -> None:
    x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
    box = shapely.box(x0, y0, x1, y1)
    # the lattice: the raster, cells the strip replaced are blank
    j0, j1 = int((top - y1) / pixel), int((top - y0) / pixel) + 1
    i0, i1 = int((x0 - left) / pixel), int((x1 - left) / pixel) + 1
    sub = depth[max(j0, 0) : j1, max(i0, 0) : i1]
    ex = (left + max(i0, 0) * pixel, left + i1 * pixel, top - j1 * pixel, top - max(j0, 0) * pixel)
    ax.imshow(sub, extent=ex, origin="upper", cmap=cmap, norm=norm, interpolation="nearest", zorder=1)
    if lattice_edges:
        xs = np.arange(np.floor(x0 / dx) * dx, x1 + dx, dx)
        ys = np.arange(np.floor(y0 / dx) * dx, y1 + dx, dx)
        ax.vlines(xs, y0, y1, colors="0.75", lw=0.3, zorder=2)
        ax.hlines(ys, x0, x1, colors="0.75", lw=0.3, zorder=2)
    # the strip cells
    keep = [k for k, g in enumerate(cell_geoms) if g.intersects(box)]
    polys = [np.asarray(cell_geoms[k].exterior.coords) for k in keep]
    values = np.array([cell_rows[k][1] for k in keep], np.float64)
    if PIXELS:  # the pixel raster shows through the cells; only their edges are drawn
        colours = "none"
    else:
        colours = [cmap(norm(v)) if v > 0.0 else (1.0, 1.0, 1.0, 1.0) for v in values]
    ax.add_collection(PolyCollection(polys, facecolors=colours, edgecolors="0.35", linewidths=0.35, zorder=3))
    # breakline faces of the strip and the interface
    for kind, colour, lw, z in (("interface", "#e08a00", 0.9, 4), ("breakline", "#c00000", 1.2, 5)):
        segs = [np.asarray(g.coords) for g, r in zip(face_geoms, face_rows, strict=True) if r[0] == kind and g.intersects(box)]
        if segs:
            ax.add_collection(LineCollection(segs, colors=colour, linewidths=lw, zorder=z))
    # W26's bank lines as suggested, under the strip's own breakline faces
    segs = [np.asarray(p.coords)[:, :2] for b in banks for p in (b.geoms if hasattr(b, "geoms") else [b]) if p.intersects(box)]
    if segs:
        ax.add_collection(LineCollection(segs, colors="#ff7f7f", linewidths=0.8, linestyles=(0, (3, 2)), zorder=4.5))
    ax.plot(axis[:, 0], axis[:, 1], "k--", lw=1.2, zorder=6)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=10)
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(useOffset=False, style="plain")


fig, axes = plt.subplots(1, 2, figsize=(15, 7.6), dpi=170)
acx, acy = float(axis[:, 0].mean()), float(axis[:, 1].mean())
window(axes[0], acx + 150.0, acy, 700.0, "Faydh 01 at 20 m: the dam axis (black dashed), largest depth of the run", False)
# detail: the point of the axis line nearest a breakline face, a bank the corridor rows follow
bl = [g for g, r in zip(face_geoms, face_rows, strict=True) if r[0] == "breakline"]
union = shapely.unary_union(bl) if bl else None
if union is not None:
    p = shapely.LineString(axis).interpolate(0.5, normalized=True)
    near = shapely.Point(shapely.shortest_line(union, p).coords[0])
    dcx, dcy = near.x, near.y
else:
    dcx, dcy = acx, acy
window(axes[1], dcx, dcy, 180.0, "Detail: aligned rows on the bank (red), squares either side, the join (orange)", True)
sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
cb = fig.colorbar(sm, ax=axes, fraction=0.025, pad=0.01)
cb.set_label(("largest depth of the run at the DEM pixel, m" if PIXELS else "largest depth of the run per cell, m"), fontsize=8)
cb.ax.tick_params(labelsize=7)
fig.text(
    0.5, 0.015,
    "Corridor cells 20 x 10 m on W26's bank pairs, gap triangles on the existing nodes, 20 m squares elsewhere; "
    "dashed pink: the suggested bank lines; red: the strip faces that sit on them.",
    ha="center", fontsize=8,
)  # fmt: skip
fig.savefig(out, bbox_inches="tight")
print("wrote", out, "cells in view", len(cell_geoms))
