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
    """The mesh faces a polyline separates and the sign that makes their discharge positive to the line's right.

    The lattice rasterises a line into a staircase of faces between the cells on either side of it; here the same
    rule on polygons: a cell is on the line's left or right by its centroid against the nearest stretch of the line,
    and a face counts when its two cells (a ghost, the tile cell beyond the join, included) lie on different sides.
    A line across a corridor is parallel to the station faces that carry the flow and would cut none of them.
    Faces past the line's ends, which the nearest stretch would still take sides on, stay out.
    """
    line = shapely.LineString(coordinates)
    parts = np.asarray(line.coords)[:, :2]
    seg = np.diff(parts, axis=0)
    cum = np.concatenate(([0.0], np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))))
    cx, cy = mesh.cx, mesh.cy

    def side(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """+1 left of the line, -1 right, by the nearest stretch."""
        pts = shapely.points(np.column_stack((x, y)))
        s = shapely.line_locate_point(line, pts)
        k = np.clip(np.searchsorted(cum, s, side="right") - 1, 0, seg.shape[0] - 1)
        px, py = np.asarray(shapely.get_coordinates(shapely.line_interpolate_point(line, s))).T
        cross = seg[k, 0] * (y - py) - seg[k, 1] * (x - px)
        return np.where(cross >= 0.0, 1.0, -1.0)

    sides = side(cx, cy)
    L, R = mesh.left, mesh.right
    across = sides[L] != sides[R]
    faces = np.nonzero(across)[0]
    if faces.size == 0:
        return faces, np.zeros(0, np.float64)
    mids = shapely.points(np.column_stack((mesh.xf[faces], mesh.yf[faces])))
    s = shapely.line_locate_point(line, mids)
    reach = 0.5 * np.sqrt(np.maximum(mesh.area[L[faces]], mesh.area[R[faces]]))
    at_end = (s <= 1e-6) | (s >= line.length - 1e-6)
    beyond = at_end & (shapely.distance(line, mids) > reach)
    faces = faces[~beyond]
    signs = np.where(sides[L[faces]] > 0.0, 1.0, -1.0)  # positive discharge runs left cell to right cell
    return faces, signs
