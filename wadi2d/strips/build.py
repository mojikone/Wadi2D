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
from wadi2d.solver.poly.mesh import DN_MIN, PolyMesh
from wadi2d.strips.geometry import MeshGeometry
from wadi2d.strips.hybrid import ghosts_for
from wadi2d.strips.mesher import Corridor, StripMesh, build_strip_mesh
from wadi2d.strips.objects import crest_polylines, faces_from_objects
from wadi2d.strips.tables import BedPixels, build_poly_tables
from wadi2d.tables.builder import GridTables
from wadi2d.tables.parallel import ThreadBeds
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
        from wadi2d.strips.banks import (
            CellRule,
            corridor_specs,
            corridor_specs_thalweg,
            pair_banks,
            read_layers,
            read_thalwegs,
        )

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


HARD_KINDS = ("crest_line", "wall", "embankment", "channel_dyke")
"""Terrain objects whose line is a hard breakline for the centre generator: its faces carry the physics."""


def centre_mesh_of(cfg: RunConfig, grid: TileGrid) -> StripMesh:
    """The centre generator's mesh of a job (W46): guide lines are the thalwegs of the banks file, ranked by drainage
    area, their banks read on the DEM by the floor rule; hard lines are the job's crests and walls."""
    from wadi2d.breaklines.window import read_window
    from wadi2d.strips.banks import read_thalwegs
    from wadi2d.strips.centres import CentreSettings, Line, build_centre_mesh, chain_streams
    from wadi2d.strips.floor import FloorRule, floor_of_line

    s = cfg.strips
    settings = CentreSettings(
        dx=cfg.grid.dx, min_area_fraction=s.min_area_fraction, max_faces=s.max_faces, clearance_cells=s.clearance_cells,
        relax_rounds=s.relax_rounds, hard_rows=s.hard_rows, smooth=s.smooth,
    )  # fmt: skip
    lines: list[Line] = []
    for obj in cfg.terrain.objects:
        if obj.kind in HARD_KINDS and len(obj.coordinates) >= 2:
            lines.append(Line(f"{obj.kind}:{obj.name}" if getattr(obj, "name", None) else obj.kind, np.asarray(obj.coordinates, np.float64)[:, :2], np.inf, hard=True))
    if s.banks:
        for k, t in enumerate(chain_streams(read_thalwegs(s.banks))):  # stems, not the file's segments: the main runs unbroken
            lines.append(Line(f"t{k}_{t['area_km2']:.1f}km2", np.asarray(t["line"].coords, np.float64), t["area_km2"]))
    if not lines:
        raise ValueError("the centre generator needs lines: a banks file with thalwegs (strips.banks) or crest and wall objects")
    floors: list[tuple[np.ndarray, np.ndarray] | None] = [None] * len(lines)
    if any(not line.hard for line in lines):
        from wadi2d.strips.centres import stations_of

        win = read_window(cfg)
        rule = FloorRule.from_settings(cfg.breaklines, cfg.grid.dx)
        for k, line in enumerate(lines):
            if line.hard:
                continue
            pts, _normals, _notes = stations_of(line, settings)
            if pts.shape[0] >= 2:
                floors[k] = floor_of_line(win, pts, rule)
    # the cells of the job's boundary lines, as the run itself picks them, and one ring of squares round them stay
    # squares: the boundaries are applied on the lattice, a strip face against a boundary cell passed nothing, and
    # the strip ponded 20 m deep against Faydh's outlet (2026-11-08); with a plain square between, the water goes
    # strip to square to boundary as it does with the ring corridors
    keep_out = np.zeros(grid.shape, bool)
    if cfg.boundaries:
        from scipy import ndimage

        from wadi2d.forcing import cells_along

        for boundary in cfg.boundaries:
            try:
                bj, bi = cells_along(grid, boundary.coordinates, 4, boundary.snap_m)
            except ValueError:
                continue  # a line off the domain is the run's own refusal, not the mesher's
            keep_out[bj, bi] = True
        keep_out = ndimage.binary_dilation(keep_out, structure=np.ones((3, 3), bool)) & grid.mask
    mesh = build_centre_mesh(grid, lines, floors, settings, keep_out=keep_out)
    if s.gorge_rows >= 2:  # rows across a channel narrower than the pair, cut on the finished mesh (W52)
        from wadi2d.strips.gorge import DemSampler, GorgeRule, split_gorge_rows

        with DemSampler(cfg.terrain.dem) as ground:
            mesh = split_gorge_rows(mesh, ground, GorgeRule(s.gorge_rows, s.gorge_wall_m, s.gorge_cell_min_m, ground.pixel))
    return mesh


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
    if cfg.strips.generator == "centres":
        strip = centre_mesh_of(cfg, provisional)
    else:
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


def strip_tables(
    cfg: RunConfig,
    tables: GridTables,
    bed,
    strip: StripMesh,
    manning: float | np.ndarray,
    base=None,
    changed: np.ndarray | None = None,
    keep_raw: bool = False,
) -> StripTables:
    """The strip's polygon mesh with its tables from the DEM window under it, and its ghosts on the lattice.
    ``manning`` is the squares' grid, read at the squares under the strip as well, or one value.

    ``base`` (the :class:`~wadi2d.strips.tables.PieceTables` a build of this strip kept with ``keep_raw``) and
    ``changed``, (n, 4) map boxes of (xmin, ymin, xmax, ymax) outside which no pixel differs from that build's, build
    again only the pieces whose window reaches a box (W91: the pit fills)."""
    grid = tables.grid
    geo = strip.geometry
    pad = 2.0 * grid.dx
    if cfg.tables.face_conveyance == "local_radius":  # the window reaches past every face's ends (W49)
        reach = cfg.tables.local_radius_beta * cfg.tables.face_depth_max
        span = getattr(bed, "span", None)
        # W85: no further than a bed in memory is long. The pieces clip their windows to this one and a face's line
        # clips its samples to it, so past the bed's edge they read the same repeats of it as before; a raster bed
        # has no span and is read as before
        pad += reach if span is None else min(reach, span * bed.pixel)
    x_lo, x_hi = float(geo.x.min()) - pad, float(geo.x.max()) + pad
    y_lo, y_hi = float(geo.y.min()) - pad, float(geo.y.max()) + pad
    k = round(grid.dx / bed.pixel)
    col0 = int(np.floor((x_lo - grid.x0) / bed.pixel))
    row0 = int(np.floor((grid.y0 - y_hi) / bed.pixel))
    ncols = int(np.ceil((x_hi - x_lo) / bed.pixel)) + 1
    nrows = int(np.ceil((y_hi - y_lo) / bed.pixel)) + 1
    ground = Ground(bed, grid.x0, grid.y0)
    edits = apply_objects(grid, cfg.terrain.objects, bed.pixel, cfg.terrain, ground)
    # the window is read a piece at a time with the edits on each, the pieces on threads with a bed each (W81):
    # whole, it asked for 66.5 GiB on Block 2
    beds = ThreadBeds(bed)
    pix = BedPixels(
        bed, edits.edit, row0, col0, nrows, ncols, grid.x0 + col0 * bed.pixel, grid.y0 - row0 * bed.pixel, grid.dx / k, beds
    )  # fmt: skip
    ghosts = ghosts_for(geo, grid, tables)
    lines = crest_polylines(cfg.terrain.objects, grid.dx, cfg.terrain, ground, edits.shapes)
    crest, cw, wall = faces_from_objects(geo, ghosts, lines)
    n = strip_manning(geo, grid, manning, cfg.terrain.manning)
    dn_floor = None
    if strip.gorge is not None and (strip.gorge != 0).any():
        # a face between two cells of the gorge rows keeps its own centre distance: the rows are narrower than the
        # floor the lattice's size gives a skewed face, and orthogonal by construction (W52)
        left, right = geo.face_cell[:, 0], geo.face_cell[:, 1]
        rows_both = (strip.gorge[left] != 0) & (right >= 0) & (strip.gorge[np.maximum(right, 0)] != 0)
        dn_floor = np.where(rows_both, DN_MIN * cfg.strips.gorge_cell_min_m, DN_MIN * grid.dx)
    boxes = None
    if base is not None and changed is not None:
        b, p = np.asarray(changed, np.float64).reshape(-1, 4), pix.pixel
        boxes = np.stack(
            (np.floor((pix.y0 - b[:, 3]) / p) - 1, np.floor((b[:, 0] - pix.x0) / p) - 1,
             np.ceil((pix.y0 - b[:, 1]) / p) + 1, np.ceil((b[:, 2] - pix.x0) / p) + 1),
            axis=1,
        ).astype(np.int64)  # fmt: skip
    try:
        mesh, kept = build_poly_tables(
            geo, pix, cfg.tables, grid.dx, n, wall=wall if wall.any() else None, given_cw=cw, ghosts=ghosts, crest=crest,
            dn_floor=dn_floor, base=base if boxes is not None else None, boxes=boxes, keep_raw=keep_raw,
        )  # fmt: skip
    finally:
        beds.close()
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
