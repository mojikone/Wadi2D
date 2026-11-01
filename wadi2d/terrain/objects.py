"""Terrain objects: vector edits applied when the tables are built. Adding a kind is one class in the registry.

Face objects write into :class:`CrestFaces`; a crest raises a face, a spillway sets its discharge law, a wall
closes it. Order inside the result: crest lines (the higher wins where two meet), then spillways, then walls.
Crest lines and walls that end beside another one are joined on the lattice first, so a dyke that stops on a dam
on paper also stops on it in the grid. A spillway drawn on a dam line shares the dam's faces: its own staircase
could fall one cell off the dam's and pour into the back of it, so it takes the crest faces beside it and walks
its own lattice only where none are near. Burn lines edit pixels through the ``edit`` hook of ``build_tables``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import shapely
from rasterio import features
from rasterio.transform import Affine

from wadi2d.config.constants import CRITICAL_WEIR_COEFF
from wadi2d.config.schema import Terrain, TerrainObject
from wadi2d.grid.tiles import TileGrid
from wadi2d.storm.registry import Registry
from wadi2d.tables.builder import CrestFaces
from wadi2d.terrain.crest import NORTH, Staircase, elevations_along, join_ends, line_lengths, staircase

PixelEdit = Callable[[np.ndarray, int, int], None]

STAIR_FIELDS = ("axis", "j", "i", "side", "s", "factor")


@dataclass
class FaceSet:
    """The face grids under construction, the joined barrier lines, and which faces crest lines own."""

    grid: TileGrid
    crest: CrestFaces
    cfg: Terrain
    stairs: dict[int, Staircase] = field(default_factory=dict)
    lines: list[Staircase] = field(default_factory=list)

    def crest_faces(self) -> Staircase | None:
        if not self.lines:
            return None
        return Staircase(*(np.concatenate([getattr(s, n) for s in self.lines]) for n in STAIR_FIELDS))


class Applied(Protocol):
    """One kind of terrain object. ``faces`` runs in ``phase`` order; ``pixels`` returns a pixel edit or None."""

    phase: int
    barrier: bool

    def faces(self, obj: TerrainObject, target: FaceSet) -> None: ...

    def pixels(self, obj: TerrainObject, grid: TileGrid, pixel: float, cfg: Terrain) -> PixelEdit | None: ...


TERRAIN_OBJECTS: Registry[Applied] = Registry("terrain object")


def _set(target: FaceSet, st: Staircase, z: np.ndarray, factor: np.ndarray, c: float, keep_max: bool) -> None:
    grid = target.crest
    for axis, zz, ln, cc in ((NORTH, grid.yz, grid.ylen, grid.yc), (1 - NORTH, grid.xz, grid.xlen, grid.xc)):
        on = st.axis == axis
        j, i = st.j[on], st.i[on]
        new = z[on]
        if keep_max:
            old = zz[j, i]
            new = np.where(np.isnan(old), new, np.maximum(old, new))
        zz[j, i] = new
        ln[j, i] = factor[on]
        cc[j, i] = c


@TERRAIN_OBJECTS.register("crest_line")
class CrestLine:
    """High ground as a line: faces closed up to the crest, overtopped at critical flow."""

    phase = 0
    barrier = True

    def faces(self, obj: TerrainObject, target: FaceSet) -> None:
        st = target.stairs[id(obj)]
        z = elevations_along(obj.coordinates, obj.z, obj.z_constant, st.s)
        _set(target, st, z, st.factor, CRITICAL_WEIR_COEFF, keep_max=True)
        target.lines.append(st)

    def pixels(self, _obj, _grid, _pixel, _cfg) -> PixelEdit | None:
        return None


def _near_crest(target: FaceSet, obj: TerrainObject) -> Staircase | None:
    """The crest-line faces beside a spillway line, or None."""
    all_faces = target.crest_faces()
    if all_faces is None:
        return None
    grid = target.grid
    jc, ic = all_faces.j.astype(np.float64), all_faces.i.astype(np.float64)
    north = all_faces.axis == NORTH
    x = grid.x0 + (ic + np.where(north, 0.5, 0.0)) * grid.dx
    y = grid.y0 - (jc + np.where(north, 0.0, 0.5)) * grid.dx
    line = shapely.LineString(obj.coordinates)
    pts = shapely.points(x, y)
    near = shapely.distance(line, pts) <= target.cfg.spillway_snap_cells * grid.dx
    if not near.any():
        return None
    out = Staircase(*(getattr(all_faces, n)[near] for n in STAIR_FIELDS))
    out.s = np.asarray(shapely.line_locate_point(line, pts[near]))
    return out


@TERRAIN_OBJECTS.register("spillway")
class Spillway:
    """A crest with the user's law Q = C L H^1.5, its faces stretched so their widths add up to L."""

    phase = 1
    barrier = False

    def faces(self, obj: TerrainObject, target: FaceSet) -> None:
        st = _near_crest(target, obj)
        if st is None:
            st = staircase(target.grid, obj.coordinates)
        if st.size == 0:
            raise ValueError("spillway lies outside the grid")
        length = obj.length if obj.length is not None else float(line_lengths(obj.coordinates)[-1])
        z = elevations_along(obj.coordinates, obj.z, obj.z_constant, st.s)
        factor = np.full(st.size, length / (st.size * target.grid.dx))
        _set(target, st, z, factor, obj.coefficient, keep_max=False)

    def pixels(self, _obj, _grid, _pixel, _cfg) -> PixelEdit | None:
        return None


@TERRAIN_OBJECTS.register("wall")
class Wall:
    """Closed faces: nothing passes, at any level."""

    phase = 2
    barrier = True

    def faces(self, obj: TerrainObject, target: FaceSet) -> None:
        st = target.stairs[id(obj)]
        north = st.axis == NORTH
        target.crest.ywall[st.j[north], st.i[north]] = True
        target.crest.xwall[st.j[~north], st.i[~north]] = True

    def pixels(self, _obj, _grid, _pixel, _cfg) -> PixelEdit | None:
        return None


@TERRAIN_OBJECTS.register("burn_line")
class BurnLine:
    """A channel cut into the bed: pixels under the line drop to its invert, or by ``depth`` below ground."""

    phase = 0
    barrier = False

    def faces(self, _obj: TerrainObject, _target: FaceSet) -> None:
        return None

    def pixels(self, obj: TerrainObject, grid: TileGrid, pixel: float, cfg: Terrain) -> PixelEdit | None:
        width = obj.width if obj.width > 0.0 else cfg.burn_pixels * pixel
        line = shapely.LineString(obj.coordinates)
        strip = line.buffer(0.5 * width, cap_style="flat")
        xmin, ymin, xmax, ymax = strip.bounds
        absolute = obj.z is not None or obj.z_constant is not None

        def edit(z: np.ndarray, row0: int, col0: int) -> None:
            west = grid.x0 + col0 * pixel
            north = grid.y0 - row0 * pixel
            ny, nx = z.shape
            if xmax < west or xmin > west + nx * pixel or ymin > north or ymax < north - ny * pixel:
                return
            transform = Affine(pixel, 0.0, west, 0.0, -pixel, north)
            hit = features.rasterize(
                [(strip, 1)], out_shape=z.shape, transform=transform, all_touched=True, dtype="uint8"
            ).astype(bool)
            if not hit.any():
                return
            if not absolute:
                z[hit] -= obj.depth
                return
            r, c = np.nonzero(hit)
            s = shapely.line_locate_point(
                line, shapely.points(west + (c + 0.5) * pixel, north - (r + 0.5) * pixel)
            )
            z[hit] = np.minimum(z[hit], elevations_along(obj.coordinates, obj.z, obj.z_constant, s))

        return edit


@dataclass
class TerrainEdits:
    """What ``build_tables`` needs from the objects."""

    crest: CrestFaces
    edit: PixelEdit | None


def apply_objects(
    grid: TileGrid, objects: Iterable[TerrainObject], pixel: float, cfg: Terrain | None = None
) -> TerrainEdits:
    """Turn the job's objects into edited faces and a pixel edit."""
    cfg = cfg or Terrain()
    crest = CrestFaces.empty(grid.shape)
    crest.xwall = np.zeros(grid.shape, bool)
    crest.ywall = np.zeros(grid.shape, bool)
    built = [(TERRAIN_OBJECTS.build(o.kind), o) for o in objects]
    stairs = {id(o): staircase(grid, o.coordinates) for kind, o in built if kind.barrier}
    join_ends(list(stairs.values()), cfg.join_cells, grid)
    target = FaceSet(grid, crest, cfg, stairs)
    edits: list[PixelEdit] = []
    for kind, obj in sorted(built, key=lambda item: item[0].phase):
        kind.faces(obj, target)
        edit = kind.pixels(obj, grid, pixel, cfg)
        if edit is not None:
            edits.append(edit)
    if not edits:
        return TerrainEdits(crest, None)

    def edit_all(z: np.ndarray, row0: int, col0: int) -> None:
        for edit in edits:
            edit(z, row0, col0)

    return TerrainEdits(crest, edit_all)
