# Wadi2D. Copyright (C) 2026 Mojtaba.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A job's strips: from the ``strips`` section to the lattice cells they replace, their polygon mesh with its tables,
and the faces of its result lines (W45, stage 7).

``mask_for_strips`` runs before the lattice tables, so the faces of the replaced cells close; ``strip_tables`` runs
after them, reading the DEM window under the strips through the run's own bed; ``line_crossings`` gives a result line
the strip faces it crosses, signed as the lattice gives them (positive to the line's right).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely

from wadi2d.config.schema import RunConfig, Strips
from wadi2d.grid.tiles import TileGrid
from wadi2d.solver.poly.mesh import PolyMesh
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.hybrid import ghosts_for
from wadi2d.strips.mesher import Corridor, StripMesh, build_strip_mesh
from wadi2d.strips.tables import Pixels, build_poly_tables
from wadi2d.tables.builder import GridTables


@dataclass
class StripTables:
    """What a run with strips carries beside its lattice tables."""

    strip: StripMesh
    mesh: PolyMesh
    kept: np.ndarray
    """The geometry face of each mesh face."""


def corridors_of(cfg: Strips, dx: float) -> list[Corridor]:
    along = cfg.along if cfg.along is not None else dx
    out = []
    for spec in cfg.corridors:
        snap = {row.row: shapely.LineString(row.coordinates) for row in spec.snap}
        out.append(Corridor(spec.name, shapely.LineString(spec.centre), np.asarray(spec.offsets, np.float64), along, snap))
    return out


def mask_for_strips(cfg: RunConfig, mask: np.ndarray, x0: float, y0: float) -> tuple[np.ndarray, StripMesh]:
    """The domain mask with the cells under the strips taken out, and the strip mesh built on the padded grid the
    final mask gives (the padding is one cell north and west, whatever the mask)."""
    provisional = TileGrid.from_mask(mask, x0, y0, cfg.grid.dx)
    strip = build_strip_mesh(
        provisional, corridors_of(cfg.strips, cfg.grid.dx), cfg.strips.buffer_cells * cfg.grid.dx, cfg.strips.smooth
    )
    jj, ii = strip.masked
    out = mask.copy()
    out[jj - 1, ii - 1] = False
    return out, strip


def strip_tables(cfg: RunConfig, tables: GridTables, bed, strip: StripMesh, manning: float | np.ndarray) -> StripTables:
    """The strip's polygon mesh with its tables from the DEM window under it, and its ghosts on the lattice."""
    grid = tables.grid
    geo = strip.geometry
    pad = 2.0 * grid.dx
    x_lo, x_hi = float(geo.x.min()) - pad, float(geo.x.max()) + pad
    y_lo, y_hi = float(geo.y.min()) - pad, float(geo.y.max()) + pad
    k = round(grid.dx / bed.pixel)
    col0 = int(np.floor((x_lo - grid.x0) / bed.pixel))
    row0 = int(np.floor((grid.y0 - y_hi) / bed.pixel))
    ncols = int(np.ceil((x_hi - x_lo) / bed.pixel)) + 1
    nrows = int(np.ceil((y_hi - y_lo) / bed.pixel)) + 1
    z = bed.read(row0, col0, nrows, ncols)
    pix = Pixels(np.asarray(z, np.float64), grid.x0 + col0 * bed.pixel, grid.y0 - row0 * bed.pixel, grid.dx / k)
    ghosts = ghosts_for(geo, grid, tables)
    n = float(np.mean(manning)) if not np.isscalar(manning) else float(manning)
    mesh, kept = build_poly_tables(geo, pix, cfg.tables, grid.dx, n, ghosts=ghosts)
    return StripTables(strip, mesh, kept)


def line_crossings(geo: MeshGeometry, kept: np.ndarray, mesh: PolyMesh, coordinates) -> tuple[np.ndarray, np.ndarray]:
    """The mesh faces a polyline crosses and the sign that makes their discharge positive to the line's right.

    A face counts when the line crosses its interior or runs along it; a face that only ends on the line, at a
    node the line passes through, carries flow along the line and is left out.
    """
    line = shapely.LineString(coordinates)
    faces, signs = [], []
    a, b = geo.face_node[kept, 0], geo.face_node[kept, 1]
    segments = shapely.linestrings(np.stack((np.column_stack((geo.x[a], geo.y[a])), np.column_stack((geo.x[b], geo.y[b]))), axis=1))
    hit = np.nonzero(shapely.intersects(segments, line))[0]
    parts = np.asarray(line.coords)
    for f in hit:
        meet = segments[f].intersection(line)
        if meet.geom_type == "Point":
            ends = np.array([[geo.x[a[f]], geo.y[a[f]]], [geo.x[b[f]], geo.y[b[f]]]])
            if np.hypot(*(ends - np.array([meet.x, meet.y])).T).min() < 1e-6:
                continue  # the line passes through one of the face's nodes: along, not across
        elif meet.length <= 1e-9:
            continue
        xf, yf = mesh.xf[f], mesh.yf[f]
        # the line's direction at the crossing: its nearest segment
        s = line.project(shapely.Point(xf, yf))
        cum = np.concatenate(([0.0], np.cumsum(np.hypot(*np.diff(parts, axis=0).T))))
        k = int(np.clip(np.searchsorted(cum, s, side="right") - 1, 0, parts.shape[0] - 2))
        d = parts[k + 1] - parts[k]
        right = np.array([d[1], -d[0]])
        signs.append(1.0 if mesh.nx[f] * right[0] + mesh.ny[f] * right[1] > 0.0 else -1.0)
        faces.append(int(f))
    return np.asarray(faces, np.int64), np.asarray(signs, np.float64)
