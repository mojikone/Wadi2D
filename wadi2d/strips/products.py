# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The strip on the map (W45, stage 7): its cells and faces as GeoPackage layers with what the run read on them.

The lattice maps leave the cells a strip replaced blank; ``strip_mesh.gpkg`` beside them carries the strip's cells
(corridor cells and gap triangles, each with its ground, its largest depth and level of the run and its last) and
its faces (interface, breakline or inner, each with the largest discharge of the run). The plugin draws them with the
cell grid; a close look at a breakline is this file.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import shapely

from wadi2d.io.geopackage import LINES, POLYGONS, VectorLayer, write_geopackage
from wadi2d.products.smooth import crs_text

STRIP_MESH_FILE = "strip_mesh.gpkg"
CELLS_LAYER, FACES_LAYER = "strip_cells", "strip_faces"


def strip_layers(hybrid, strip) -> list[VectorLayer]:
    """The cells and faces of a run's strip with its maxima and last state."""
    geo, mesh, kept = strip.strip.geometry, strip.mesh, strip.kept
    n = hybrid.nreal
    max_d, max_h, max_q = hybrid.strip_maxima()
    d_end = hybrid.strip_host("d")[:n]
    corridor, row = strip.strip.corridor, strip.strip.row
    cells = VectorLayer(
        CELLS_LAYER,
        {
            "cell": int, "corridor": int, "row": int, "kind": str, "zmin_m": float, "area_m2": float,
            "max_depth_m": float, "max_level_m": float, "max_mean_depth_m": float, "depth_end_m": float,
            "level_end_m": float,
        },
        kind=POLYGONS,
    )  # fmt: skip
    for c in range(n):
        nodes = geo.ring_node[geo.ring_start[c] : geo.ring_start[c + 1]]
        cells.geometries.append(shapely.Polygon(np.column_stack((geo.x[nodes], geo.y[nodes]))))
        zmin = float(mesh.zmin[c])
        cells.rows.append((
            c, int(corridor[c]), int(row[c]), "corridor" if corridor[c] >= 0 else "triangle", zmin, float(mesh.area[c]),
            float(max_d[c]), zmin + float(max_d[c]), float(max_h[c]), float(d_end[c]), zmin + float(d_end[c]),
        ))  # fmt: skip
    on_line: dict[tuple[int, int], str] = {}
    for name, edges in strip.strip.breakline_edges.items():
        for edge in edges:
            on_line[edge] = name
    faces = VectorLayer(
        FACES_LAYER,
        {"face": int, "kind": str, "line": str, "left": int, "right": int, "invert_m": float, "length_m": float, "max_discharge_m3s": float},
        kind=LINES,
    )  # fmt: skip
    for f in range(mesh.nfaces):
        a, b = (int(v) for v in geo.face_node[kept[f]])
        faces.geometries.append(shapely.LineString([(geo.x[a], geo.y[a]), (geo.x[b], geo.y[b])]))
        line = on_line.get((min(a, b), max(a, b)), "")
        kind = "interface" if mesh.right[f] >= n else ("breakline" if line else "inner")
        faces.rows.append((f, kind, line, int(mesh.left[f]), int(mesh.right[f]), float(mesh.zf[f]), float(mesh.length[f]), float(max_q[f])))
    return [cells, faces]


def write_strip_mesh(path: Path, hybrid, strip, crs) -> Path:
    return write_geopackage(path, strip_layers(hybrid, strip), crs_text(crs))


__all__ = ["STRIP_MESH_FILE", "strip_layers", "write_strip_mesh"]
