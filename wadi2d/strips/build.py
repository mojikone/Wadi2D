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
from wadi2d.strips.objects import crest_polylines, faces_from_objects
from wadi2d.strips.tables import Pixels, build_poly_tables
from wadi2d.tables.builder import GridTables
from wadi2d.terrain import Ground, apply_objects


@dataclass
class StripTables:
    """What a run with strips carries beside its lattice tables."""

    strip: StripMesh
    mesh: PolyMesh
    kept: np.ndarray
    """The geometry face of each mesh face."""


def corridors_of(
    cfg: Strips, dx: float, domain: shapely.Geometry | None = None
) -> tuple[list[Corridor], list[str], list[dict]]:
    """The corridors of a job: those given outright, else those built from the banks file inside ``domain``; what the
    builder cut or dropped, in words; and per built corridor the width rule's numbers."""
    along = cfg.along if cfg.along is not None else dx
    specs: list = list(cfg.corridors)
    notes: list[str] = []
    rules: list[dict] = []
    snap_nearest = cfg.centre != "thalweg"
    if not specs and cfg.banks:
        from wadi2d.config.schema import CorridorSpec
        from wadi2d.strips.banks import CellRule, corridor_specs, corridor_specs_thalweg, pair_banks, read_layers, read_thalwegs

        if domain is None:
            raise ValueError("corridors from a banks file need the domain: give grid.domain or grid.extent")
        banks, by_area = read_layers(cfg.banks)
        if cfg.centre == "thalweg":
            built, cut, rules = corridor_specs_thalweg(
                read_thalwegs(cfg.banks), banks, domain, cfg.cell_min_m, along, min_length=cfg.min_length_m, fixed=cfg.fixed_cells
            )
        else:
            pairs = pair_banks(banks, by_area, min_length=cfg.min_length_m)
            rule = CellRule(cfg.cell_min_m, cfg.cell_max_m, cfg.width_fraction, cfg.rows_outside)
            built, cut, rules = corridor_specs(pairs, domain, rule, along, cfg.min_length_m)
        specs = [CorridorSpec.model_validate(s) for s in built]
        notes = [c["why"] for c in cut]
        if not specs:
            raise ValueError(f"no corridor could be built from {cfg.banks}: {len(pairs)} bank pairs, all cut or dropped")
    out = []
    for spec in specs:
        snap = {row.row: snap_geometry(row.coordinates) for row in spec.snap}
        edges = None
        if spec.edges_left is not None:
            edges = {"left": snap_geometry(spec.edges_left), "right": snap_geometry(spec.edges_right)}
        out.append(Corridor(
            spec.name, shapely.LineString(spec.centre), np.asarray(spec.offsets, np.float64), along, snap,
            snap_nearest=snap_nearest, edges=edges, cell=spec.cell_m or 0.0, max_cells=spec.max_cells,
        ))  # fmt: skip
    return out, notes, rules


def snap_geometry(coordinates) -> shapely.Geometry:
    """A snapped row's line, or the pieces of it when the spec gives a list of lines."""
    first = coordinates[0]
    if first and isinstance(first[0], (list, tuple)):
        return shapely.union_all([shapely.LineString(np.asarray(part, np.float64)) for part in coordinates])
    return shapely.LineString(np.asarray(coordinates, np.float64))


def mask_for_strips(
    cfg: RunConfig, mask: np.ndarray, x0: float, y0: float, domain: shapely.Geometry | None = None
) -> tuple[np.ndarray, StripMesh]:
    """The domain mask with the cells under the strips taken out, and the strip mesh built on the padded grid the
    final mask gives (the padding is one cell north and west, whatever the mask)."""
    provisional = TileGrid.from_mask(mask, x0, y0, cfg.grid.dx)
    corridors, notes, rules = corridors_of(cfg.strips, cfg.grid.dx, domain)
    strip = build_strip_mesh(provisional, corridors, cfg.strips.buffer_cells * cfg.grid.dx, cfg.strips.smooth)
    strip.notes = notes
    strip.rules = rules
    jj, ii = strip.masked
    out = mask.copy()
    out[jj - 1, ii - 1] = False
    return out, strip


def strip_squares(geo: MeshGeometry, grid: TileGrid) -> tuple[np.ndarray, np.ndarray]:
    """The lattice square each strip cell's centroid stands in, as (row, column) on the grid."""
    _area, cx, cy = geo.areas_centroids()
    sj = np.clip(np.floor((grid.y0 - cy) / grid.dx).astype(np.int64), 0, grid.shape[0] - 1)
    si = np.clip(np.floor((cx - grid.x0) / grid.dx).astype(np.int64), 0, grid.shape[1] - 1)
    return sj, si


def strip_manning(geo: MeshGeometry, grid: TileGrid, manning: float | np.ndarray, fallback: float) -> float | np.ndarray:
    """Each strip cell's roughness: where a raster gave the squares theirs, the value of the square the cell stands
    in (read at those squares too, since the mask dropped them); one value otherwise. Before this the strip took one
    mean of the squares' grid, NaN where the squares under it had left the mask."""
    if np.isscalar(manning):
        return float(manning)
    sj, si = strip_squares(geo, grid)
    n = np.asarray(manning, np.float64)[sj, si]
    return np.where(np.isfinite(n), n, fallback)


def strip_tables(cfg: RunConfig, tables: GridTables, bed, strip: StripMesh, manning: float | np.ndarray) -> StripTables:
    """The strip's polygon mesh with its tables from the DEM window under it, and its ghosts on the lattice.
    ``manning`` is the squares' grid, read at the squares under the strip as well, or one value."""
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
    z = np.asarray(bed.read(row0, col0, nrows, ncols), np.float64)
    ground = Ground(bed, grid.x0, grid.y0)
    edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain, ground)
    if edits.edit is not None:  # burn lines and shaped objects rebuild the strip's ground as they do the squares'
        edits.edit(z, row0, col0)
    pix = Pixels(z, grid.x0 + col0 * bed.pixel, grid.y0 - row0 * bed.pixel, grid.dx / k)
    ghosts = ghosts_for(geo, grid, tables)
    lines = crest_polylines(cfg.terrain.objects, grid.dx, cfg.terrain, ground, edits.shapes)
    crest, cw, wall = faces_from_objects(geo, ghosts, lines)
    n = strip_manning(geo, grid, manning, cfg.terrain.manning)
    mesh, kept = build_poly_tables(
        geo, pix, cfg.tables, grid.dx, n, wall=wall if wall.any() else None, given_cw=cw, ghosts=ghosts, crest=crest
    )
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
